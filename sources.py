"""Configuration of Israeli fine sources (municipalities + national police).

Each Source describes one website that can be queried with (plate, id, fine_number).
Add a new city by appending a Source to ALL_SOURCES.

Semantic locators (Hebrew labels) are tried in order; the first match wins.
Run discover.py against any URL to verify the actual labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Source:
    key: str                # short identifier, e.g. "jerusalem"
    name_ru: str            # display name in Russian
    name_he: str            # display name in Hebrew (for the appeal letter)
    url: str
    fine_labels: tuple[str, ...]   = ()
    plate_labels: tuple[str, ...]  = ()
    id_labels: tuple[str, ...]     = ()
    submit_texts: tuple[str, ...]  = ()
    # If the site uses reCAPTCHA v2, put its sitekey here. Empty → no captcha.
    site_key: str = ""
    enabled: bool = True


ALL_SOURCES: list[Source] = [
    Source(
        key="jerusalem",
        name_ru="Иерусалим",
        name_he="עיריית ירושלים",
        url="https://jerinfogen.jerusalem.muni.il/findreport/default.aspx",
        fine_labels=("מספר דוח", "מספר הדוח"),
        plate_labels=("מספר רכב", "מס' רכב"),
        id_labels=("תעודת זהות", "ת.ז", "ת״ז"),
        submit_texts=("חיפוש", "אישור", "המשך"),
    ),
    Source(
        key="tel_aviv",
        name_ru="Тель-Авив-Яффо",
        name_he="עיריית תל אביב-יפו",
        url="https://tlvpay.tel-aviv.gov.il/he/service/1/1",
        fine_labels=("מספר דוח", "מספר תיק", "מספר הדוח"),
        plate_labels=("מספר רכב", "מס' רכב"),
        id_labels=("מספר זהות", "תעודת זהות", "ת.ז"),
        submit_texts=("המשך", "חיפוש", "אישור"),
    ),
    Source(
        key="haifa",
        name_ru="Хайфа",
        name_he="עיריית חיפה",
        url="https://www.haifa.muni.il/services/parking/check-reports/",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("חיפוש", "המשך"),
    ),
    Source(
        key="beer_sheva",
        name_ru="Беэр-Шева",
        name_he="עיריית באר שבע",
        url="https://www.beer-sheva.muni.il/Residents/Parking/Pages/parking-reports.aspx",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("חיפוש", "המשך"),
    ),
    Source(
        key="rishon",
        name_ru="Ришон-ле-Цион",
        name_he="עיריית ראשון לציון",
        url="https://www.rishonlezion.muni.il/Residents/Parking/Pages/default.aspx",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("חיפוש", "המשך"),
    ),
    Source(
        key="netanya",
        name_ru="Нетания",
        name_he="עיריית נתניה",
        url="https://www.netanya.muni.il/Residents/Pages/parking.aspx",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("חיפוש", "המשך"),
    ),
    Source(
        key="petah_tikva",
        name_ru="Петах-Тиква",
        name_he="עיריית פתח תקווה",
        url="https://www.petach-tikva.muni.il/Residents/transport/Pages/parking_tickets.aspx",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("חיפוש", "המשך"),
    ),
    Source(
        key="holon",
        name_ru="Холон",
        name_he="עיריית חולון",
        url="https://www.holon.muni.il/Residents/Pages/parking-reports.aspx",
        fine_labels=("מספר דוח",),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("חיפוש", "המשך"),
    ),
    Source(
        key="police",
        name_ru="Полиция (общенац.)",
        name_he="משטרת ישראל",
        url="https://www.gov.il/he/service/police_fine_payment",
        fine_labels=("מספר דוח", "מספר ברקוד"),
        plate_labels=("מספר רכב",),
        id_labels=("תעודת זהות",),
        submit_texts=("המשך", "חיפוש"),
    ),
]


def enabled_sources() -> list[Source]:
    return [s for s in ALL_SOURCES if s.enabled]


def get_source(key: str) -> Source | None:
    for s in ALL_SOURCES:
        if s.key == key:
            return s
    return None
