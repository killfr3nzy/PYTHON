"""Configuration of Israeli fine sources.

After surveying live municipal portals (discover_all.py), only Tel Aviv-Yafo
exposes a working form that returns fine details for (plate, fine_number).
Jerusalem is blocked by Akamai, the police service has a Cloudflare-style
challenge, and the remaining cities' URLs in our seed list are 404 / DNS
errors. They are kept here as `enabled=False` so future discovery rounds
can re-enable them once correct URLs are found.

Add a new city by appending a Source and switching `enabled=True`.
Run `python discover_all.py` to re-verify every entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    key: str                              # short identifier, e.g. "tel_aviv"
    name_ru: str                          # display name in Russian
    name_he: str                          # display name in Hebrew
    url: str
    fine_labels: tuple[str, ...]   = ()
    plate_labels: tuple[str, ...]  = ()
    id_labels: tuple[str, ...]     = ()
    submit_texts: tuple[str, ...]  = ()
    # Captcha. site_key is the public Google/Cloudflare site key from the
    # form's HTML; captcha_kind selects the solver method.
    site_key: str = ""
    captcha_kind: str = "none"            # "none" | "recaptcha_v2" | "recaptcha_v3" | "hcaptcha"
    captcha_action: str = ""              # for v3 only
    requires_id: bool = False             # form needs Israeli ID in addition to plate+fine
    enabled: bool = True


ALL_SOURCES: list[Source] = [
    Source(
        key="tel_aviv",
        name_ru="Тель-Авив-Яффо",
        name_he="עיריית תל אביב-יפו",
        url="https://tlvpay.tel-aviv.gov.il/he/service/1/1",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        submit_texts=("הצגת סכום",),
        site_key="6LfSsG8sAAAAAHp9p4lvFSadQiUG8hvL4czrybQR",
        captcha_kind="recaptcha_v2_invisible",
        requires_id=False,
        enabled=True,
    ),

    # Disabled: Akamai blocks all clients with 403 Access Denied.
    Source(
        key="jerusalem",
        name_ru="Иерусалим",
        name_he="עיריית ירושלים",
        url="https://jerinfogen.jerusalem.muni.il/findreport/default.aspx",
        enabled=False,
    ),

    # Disabled: Cloudflare-style "רק רגע..." anti-bot challenge.
    Source(
        key="police",
        name_ru="Полиция (общенац.)",
        name_he="משטרת ישראל",
        url="https://www.gov.il/he/service/police_fine_payment",
        enabled=False,
    ),

    # Disabled: URLs in the seed list return 404 or DNS errors. Need a new
    # discovery round to find the current portal for each.
    Source(key="haifa",       name_ru="Хайфа",          name_he="עיריית חיפה",
           url="https://www.haifa.muni.il/services/parking/check-reports/", enabled=False),
    Source(key="beer_sheva",  name_ru="Беэр-Шева",      name_he="עיריית באר שבע",
           url="https://www.beer-sheva.muni.il/Residents/Parking/Pages/parking-reports.aspx", enabled=False),
    Source(key="rishon",      name_ru="Ришон-ле-Цион",  name_he="עיריית ראשון לציון",
           url="https://www.rishonlezion.muni.il/Residents/Parking/Pages/default.aspx", enabled=False),
    Source(key="netanya",     name_ru="Нетания",        name_he="עיריית נתניה",
           url="https://www.netanya.muni.il/Residents/Pages/parking.aspx", enabled=False),
    Source(key="petah_tikva", name_ru="Петах-Тиква",    name_he="עיריית פתח תקווה",
           url="https://www.petach-tikva.muni.il/Residents/transport/Pages/parking_tickets.aspx", enabled=False),
    Source(key="holon",       name_ru="Холон",          name_he="עיריית חולון",
           url="https://www.holon.muni.il/Residents/Pages/parking-reports.aspx", enabled=False),
]


def enabled_sources() -> list[Source]:
    return [s for s in ALL_SOURCES if s.enabled]


def get_source(key: str) -> Source | None:
    for s in ALL_SOURCES:
        if s.key == key:
            return s
    return None


def any_requires_id() -> bool:
    return any(s.requires_id for s in enabled_sources())
