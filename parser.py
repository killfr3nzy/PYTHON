"""Fetches traffic and municipal fines.

Real-world flow (per gov.il / municipal portals):
  Jerusalem and Tel Aviv DO NOT expose a "list fines by plate" API.
  To unlock the full list you must provide three things:
      1. Vehicle plate number
      2. Israeli ID (תעודת זהות)
      3. At least one known fine number (from SMS / paper ticket)

Once those are submitted, Jerusalem's portal returns every other fine
tied to that (ID, plate) pair. Tel Aviv works similarly via tlvpay.

Modes (config.PARSER_MODE):
  * `mock` — deterministic sample data for demos and tests.
  * `live` — Playwright drives the configured municipal portal.

Captcha tokens are obtained via captcha.create_solver(). Selectors
live in LIVE_SELECTORS; tune them with `playwright codegen <url>`.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Iterable

from captcha import CaptchaError, create_solver
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class Fine:
    fine_id: str
    issued_at: dt.date
    location: str
    violation: str
    amount_ils: int
    status: str
    source: str
    photo_url: str | None = None
    notes: str = ""

    @property
    def days_old(self) -> int:
        return (dt.date.today() - self.issued_at).days

    @property
    def appeal_window_open(self) -> bool:
        return self.days_old <= 30

    def to_dict(self) -> dict:
        data = asdict(self)
        data["issued_at"] = self.issued_at.isoformat()
        return data


@dataclass
class LookupResult:
    plate: str
    fines: list[Fine] = field(default_factory=list)
    error: str | None = None

    @property
    def total_amount(self) -> int:
        return sum(f.amount_ils for f in self.fines)


def lookup(plate: str, israeli_id: str | None = None, fine_number: str | None = None) -> LookupResult:
    plate = _normalize_digits(plate)
    if not plate:
        return LookupResult(plate=plate, error="Некорректный номер машины")

    if settings.parser_mode == "live":
        israeli_id = _normalize_digits(israeli_id or "")
        fine_number = _normalize_digits(fine_number or "")
        if not israeli_id:
            return LookupResult(plate=plate, error="Для live-режима нужен ID (תעודת זהות)")
        if not fine_number:
            return LookupResult(
                plate=plate,
                error="Нужен номер любого известного штрафа — без него gov.il не отдаёт список.",
            )
        return _lookup_live(plate, israeli_id, fine_number)

    return _lookup_mock(plate)


def _normalize_digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _lookup_mock(plate: str) -> LookupResult:
    today = dt.date.today()
    samples: list[Fine] = [
        Fine(
            fine_id=f"MOT-{plate[-4:]}-001",
            issued_at=today - dt.timedelta(days=12),
            location="רחוב אלנבי 45, תל אביב",
            violation="חניה במקום אסור",
            amount_ils=250,
            status="לא שולם",
            source="עיריית תל אביב",
            photo_url=None,
            notes="ללא תמונה במערכת",
        ),
        Fine(
            fine_id=f"MOT-{plate[-4:]}-002",
            issued_at=today - dt.timedelta(days=4),
            location="כביש 4, צומת רעננה דרום",
            violation="מהירות מופרזת (78 בדרך 60)",
            amount_ils=750,
            status="לא שולם",
            source="משטרת ישראל",
            photo_url="https://example.gov.il/photo/abc",
        ),
        Fine(
            fine_id=f"MOT-{plate[-4:]}-003",
            issued_at=today - dt.timedelta(days=47),
            location="רחוב יפו 102, ירושלים",
            violation="נסיעה בנתיב תחבורה ציבורית",
            amount_ils=500,
            status="לא שולם",
            source="עיריית ירושלים",
            notes="עבר מועד הערעור הרגיל",
        ),
    ]
    return LookupResult(plate=plate, fines=samples)


# ---------------------------------------------------------------------------
# Live mode (Playwright)
# ---------------------------------------------------------------------------

# Default target: Jerusalem municipal parking-report search.
# Source: https://jerinfogen.jerusalem.muni.il/findreport/default.aspx
LIVE_SELECTORS = {
    # CSS selectors — adjust with `python -m playwright codegen <MOT_LOOKUP_URL>`.
    "fine_number_input": "input[name='ReportNumber'], input#txtReportNumber",
    "plate_input": "input[name='VehicleNumber'], input#txtVehicleNumber",
    "id_input": "input[name='IdNumber'], input#txtIdNumber",
    "submit_button": "input[type='submit'], button[type='submit']",
    "result_row": "table#gvReports tr.row, tr.fine-row",
    "result_cells": "td",
    "captcha_response": "textarea#g-recaptcha-response",
}


def _lookup_live(plate: str, israeli_id: str, fine_number: str) -> LookupResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return LookupResult(plate=plate, error="Playwright не установлен. См. requirements.txt")

    token: str | None = None
    if settings.mot_site_key:
        solver = create_solver()
        try:
            token = solver.solve_recaptcha_v2(settings.mot_site_key, settings.mot_lookup_url)
        except CaptchaError as exc:
            return LookupResult(plate=plate, error=f"Капча: {exc}")
    else:
        logger.info("MOT_SITE_KEY is empty — skipping captcha solver")

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=settings.playwright_headless)
            context = browser.new_context(locale="he-IL")
            page = context.new_page()
            page.goto(settings.mot_lookup_url, wait_until="networkidle")

            page.fill(LIVE_SELECTORS["fine_number_input"], fine_number)
            page.fill(LIVE_SELECTORS["plate_input"], plate)
            page.fill(LIVE_SELECTORS["id_input"], israeli_id)

            if token:
                page.evaluate(
                    "(args) => { const sel = args.selector; const tok = args.token; "
                    "const el = document.querySelector(sel) "
                    "  || document.querySelector('textarea#g-recaptcha-response'); "
                    "if (el) { el.style.display=''; el.value = tok; } }",
                    {"selector": LIVE_SELECTORS["captcha_response"], "token": token},
                )

            page.click(LIVE_SELECTORS["submit_button"])
            page.wait_for_load_state("networkidle", timeout=20_000)

            fines = list(_extract_fines_from_page(page))
            browser.close()
            return LookupResult(plate=plate, fines=fines)
    except Exception as exc:
        logger.exception("live lookup failed")
        return LookupResult(plate=plate, error=f"Playwright: {exc}")


def _extract_fines_from_page(page) -> Iterable[Fine]:
    rows = page.query_selector_all(LIVE_SELECTORS["result_row"])
    for row in rows:
        cells = [c.inner_text().strip() for c in row.query_selector_all(LIVE_SELECTORS["result_cells"])]
        if len(cells) < 4:
            continue
        try:
            yield Fine(
                fine_id=cells[0],
                issued_at=_parse_he_date(cells[1]),
                location=cells[2],
                violation=cells[3],
                amount_ils=_parse_amount(cells[4] if len(cells) > 4 else "0"),
                status=cells[5] if len(cells) > 5 else "",
                source="עיריית ירושלים",
            )
        except (ValueError, IndexError) as exc:
            logger.warning("skipped unparseable row %r: %s", cells, exc)


def _parse_he_date(value: str) -> dt.date:
    if "/" in value:
        d, m, y = value.split("/")
        return dt.date(int(y), int(m), int(d))
    return dt.date.fromisoformat(value[:10])


def _parse_amount(value: str) -> int:
    digits = re.sub(r"[^\d]", "", value)
    return int(digits) if digits else 0
