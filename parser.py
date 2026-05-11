"""Multi-source fine lookup.

Modes (config.PARSER_MODE):
  * `mock` — deterministic sample data, no network.
  * `live` — Playwright drives each enabled municipal portal in turn,
             accumulating fines into a single result.

Sources live in `sources.py`. Each Source is queried independently — a
failure in one city does not prevent the others from running, and the
per-source error is recorded in `LookupResult.warnings`.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Iterable

from captcha import CaptchaError, create_solver
from config import settings
from sources import Source, enabled_sources

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
    warnings: list[str] = field(default_factory=list)

    @property
    def total_amount(self) -> int:
        return sum(f.amount_ils for f in self.fines)

    @property
    def by_source(self) -> dict[str, list[Fine]]:
        groups: dict[str, list[Fine]] = {}
        for f in self.fines:
            groups.setdefault(f.source, []).append(f)
        return groups


def lookup(plate: str, israeli_id: str | None = None, fine_number: str | None = None) -> LookupResult:
    plate = _normalize_digits(plate)
    if not plate:
        return LookupResult(plate=plate, error="Некорректный номер машины")

    if settings.parser_mode == "live":
        israeli_id = _normalize_digits(israeli_id or "")
        fine_number = _normalize_digits(fine_number or "")
        if not fine_number:
            return LookupResult(
                plate=plate,
                error="Нужен номер штрафа — муниципальные сайты не отдают список без него.",
            )
        return _lookup_live_all(plate, israeli_id, fine_number)

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
            source="עיריית תל אביב-יפו",
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
# Live mode (Playwright, multi-source)
# ---------------------------------------------------------------------------

PER_SOURCE_TIMEOUT_MS = 25_000


def _lookup_live_all(plate: str, israeli_id: str, fine_number: str) -> LookupResult:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return LookupResult(plate=plate, error="Playwright не установлен. См. requirements.txt")

    aggregated: list[Fine] = []
    warnings: list[str] = []
    sources = enabled_sources()

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=settings.playwright_headless)
            except Exception as exc:
                return LookupResult(
                    plate=plate,
                    error=f"Не удалось запустить Chromium: {exc}",
                )
            try:
                for source in sources:
                    logger.info("Querying %s (%s)", source.name_ru, source.url)
                    try:
                        found = _lookup_one_source(browser, source, plate, israeli_id, fine_number)
                        aggregated.extend(found)
                        if not found:
                            warnings.append(f"{source.name_ru}: штрафов не найдено")
                    except Exception as exc:
                        msg = f"{source.name_ru}: {exc}"
                        logger.warning(msg)
                        warnings.append(msg)
            finally:
                browser.close()
    except Exception as exc:
        return LookupResult(plate=plate, error=f"Playwright runtime error: {exc}")

    return LookupResult(plate=plate, fines=aggregated, warnings=warnings)


def _lookup_one_source(
    browser,
    source: Source,
    plate: str,
    israeli_id: str,
    fine_number: str,
) -> list[Fine]:
    if source.requires_id and not israeli_id:
        raise RuntimeError("этот источник требует ID, но он не был передан")

    # Per-source site_key (sources.py), with env fallback (MOT_SITE_KEY) for
    # local overrides during testing.
    site_key = source.site_key or settings.mot_site_key
    token: str | None = None
    if site_key and source.captcha_kind != "none":
        solver = create_solver()
        try:
            if source.captcha_kind == "recaptcha_v3":
                token = solver.solve_recaptcha_v3(site_key, source.url, source.captcha_action)
            elif source.captcha_kind == "recaptcha_v2_invisible":
                token = solver.solve_recaptcha_v2(site_key, source.url, invisible=True)
            else:
                token = solver.solve_recaptcha_v2(site_key, source.url)
        except CaptchaError as exc:
            raise RuntimeError(f"captcha: {exc}") from exc

    context = browser.new_context(locale="he-IL")
    page = context.new_page()
    page.set_default_timeout(PER_SOURCE_TIMEOUT_MS)
    try:
        page.goto(source.url, wait_until="networkidle")

        if source.fine_labels:
            _fill_first_match(page, source.fine_labels, fine_number)
        if source.plate_labels:
            _fill_first_match(page, source.plate_labels, plate)
        if source.id_labels and israeli_id:
            _fill_first_match(page, source.id_labels, israeli_id)

        if token:
            page.evaluate(
                "(tok) => { "
                "  const sel = 'textarea#g-recaptcha-response, input[name=\"g-recaptcha-response\"]'; "
                "  document.querySelectorAll(sel).forEach((el) => { el.style.display=''; el.value = tok; }); "
                "}",
                token,
            )

        _click_first_match(page, source.submit_texts)
        page.wait_for_load_state("networkidle", timeout=PER_SOURCE_TIMEOUT_MS)

        return list(_extract_fines_from_page(page, source))
    finally:
        context.close()


def _fill_first_match(page, labels: Iterable[str], value: str) -> None:
    for label in labels:
        loc = page.get_by_label(label, exact=False)
        if loc.count() > 0:
            loc.first.fill(value)
            return
        loc = page.get_by_placeholder(label, exact=False)
        if loc.count() > 0:
            loc.first.fill(value)
            return
    raise RuntimeError(f"не нашёл поле по меткам {list(labels)}")


def _click_first_match(page, texts: Iterable[str]) -> None:
    for text in texts:
        loc = page.get_by_role("button", name=text)
        if loc.count() > 0:
            loc.first.click()
            return
        loc = page.get_by_text(text, exact=True)
        if loc.count() > 0:
            loc.first.click()
            return
    raise RuntimeError("не нашёл кнопку отправки формы")


RESULT_ROW_SELECTORS = [
    "table tbody tr:has(td)",
    "[class*='result'] [class*='row']",
    "[data-testid*='fine']",
]


def _extract_fines_from_page(page, source: Source) -> Iterable[Fine]:
    rows = []
    for selector in RESULT_ROW_SELECTORS:
        rows = page.query_selector_all(selector)
        if rows:
            break
    for row in rows:
        cells = [c.inner_text().strip() for c in row.query_selector_all("td, div, span")]
        cells = [c for c in cells if c]
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
                source=source.name_he,
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
