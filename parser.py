"""Fetches traffic and municipal fines for an Israeli license plate.

Two modes (config.PARSER_MODE):

* `mock`  - returns a deterministic sample dataset. Use for demos, local
            development, and when the live endpoints are blocked by captcha.
* `live`  - hits the Israeli government services. The eservices.mot.gov.il
            endpoint requires solving a captcha; integrate a service such as
            2captcha or Anti-Captcha before using this mode in production.

The live implementation is intentionally minimal: it issues the lookup request
and surfaces a clear error if captcha or auth blocks the response. Wire your
captcha solver into `_solve_captcha` to enable end-to-end automation.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, asdict
from typing import Iterable

import requests

from config import settings


MOT_LOOKUP_URL = "https://eservices.mot.gov.il/RashotApi/api/Reports/CheckReportsByVehicleNumber"


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


def lookup(plate: str) -> LookupResult:
    plate = _normalize_plate(plate)
    if not plate:
        return LookupResult(plate=plate, error="Некорректный номер машины")

    if settings.parser_mode == "live":
        return _lookup_live(plate)
    return _lookup_mock(plate)


def _normalize_plate(plate: str) -> str:
    return "".join(ch for ch in plate if ch.isdigit())


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


def _lookup_live(plate: str) -> LookupResult:
    captcha_token = _solve_captcha()
    if not captcha_token:
        return LookupResult(
            plate=plate,
            error="Не удалось решить капчу. Подключите 2captcha/Anti-Captcha.",
        )
    try:
        response = requests.post(
            MOT_LOOKUP_URL,
            json={"vehicleNumber": plate, "captchaToken": captcha_token},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        return LookupResult(plate=plate, error=f"Ошибка запроса к gov.il: {exc}")

    payload = response.json()
    return LookupResult(plate=plate, fines=list(_parse_mot_payload(payload)))


def _solve_captcha() -> str | None:
    # TODO: integrate 2captcha / Anti-Captcha. Keep this stub explicit so the
    # caller sees a clear error in `live` mode until the integration is wired.
    return None


def _parse_mot_payload(payload: dict) -> Iterable[Fine]:
    for item in payload.get("reports", []):
        try:
            issued_at = dt.date.fromisoformat(item["date"][:10])
        except (KeyError, ValueError):
            continue
        yield Fine(
            fine_id=str(item.get("reportNumber", "")),
            issued_at=issued_at,
            location=item.get("location", ""),
            violation=item.get("violation", ""),
            amount_ils=int(item.get("amount", 0)),
            status=item.get("status", ""),
            source="משרד התחבורה",
            photo_url=item.get("photoUrl"),
        )
