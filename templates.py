"""Hebrew appeal letter templates and rule-based analyser.

Used both as a fallback when Claude is unavailable and as the source of
structured grounds-for-appeal that the Claude prompt is grounded in.
"""

from __future__ import annotations

from dataclasses import dataclass

from parser import Fine


@dataclass
class Analysis:
    appealable: bool
    grounds: list[str]
    risk_note: str


PARKING_KEYWORDS = ("חניה", "חנייה")
SPEED_KEYWORDS = ("מהירות",)
BUS_LANE_KEYWORDS = ("נתיב תחבורה", "נת\"צ")


def analyse(fine: Fine) -> Analysis:
    grounds: list[str] = []
    text = f"{fine.violation} {fine.notes}".lower()

    if any(k in fine.violation for k in PARKING_KEYWORDS):
        grounds.append("Парковочный штраф — проверить наличие чёткого знака на месте.")
        if "ללא תמונה" in fine.notes or not fine.photo_url:
            grounds.append("В деле нет фото — затрудняет доказательство нарушения.")

    if any(k in fine.violation for k in SPEED_KEYWORDS):
        grounds.append("Скоростной штраф — запросить калибровку радара и фото.")

    if any(k in fine.violation for k in BUS_LANE_KEYWORDS):
        grounds.append("Полоса общественного транспорта — проверить разрешённые часы и категорию ТС.")

    if fine.appeal_window_open:
        risk = "Срок апелляции (30 дней) ещё открыт — стандартная процедура."
        appealable = True
    else:
        risk = (
            "Стандартный срок апелляции пропущен. Подаётся ходатайство о восстановлении "
            "срока (בקשה להארכת מועד) с обоснованием."
        )
        appealable = True
        grounds.append("Подать ходатайство о восстановлении срока обжалования.")

    if not grounds:
        grounds.append("Стандартное обжалование на основании сомнений в фактических обстоятельствах.")

    return Analysis(appealable=appealable, grounds=grounds, risk_note=risk)


def render_letter(fine: Fine, analysis: Analysis, applicant_name: str = "____________") -> str:
    """Returns a ready-to-paste Hebrew appeal letter."""

    if any(k in fine.violation for k in PARKING_KEYWORDS):
        body = (
            f"הנני מבקש לבטל את הדוח שבנדון בגין {fine.violation} ברחוב {fine.location}, "
            f"שכן במקום בו חניתי לא היה תמרור ברור האוסר חניה, ולפי הצילום בתיק לא ניתן "
            f"להוכיח את העבירה הנטענת."
        )
    elif any(k in fine.violation for k in SPEED_KEYWORDS):
        body = (
            f"הנני מבקש לבטל את הדוח שבנדון בגין {fine.violation} ב-{fine.location}. "
            f"אני מבקש לעיין בתעודת הכיול של מכשיר המדידה, בתמונת העבירה ובפרטי "
            f"השוטר/הבוחן. ללא ראיות אלה אין לבסס את האשמה."
        )
    elif any(k in fine.violation for k in BUS_LANE_KEYWORDS):
        body = (
            f"הנני מבקש לבטל את הדוח שבנדון. נסיעתי בנתיב הייתה בשעות בהן הנתיב פתוח "
            f"לתנועה כללית/לרכבי {{סוג רכב}}, או לחלופין נכנסתי לנתיב לצורך פנייה ימינה "
            f"כפי שמתיר החוק."
        )
    else:
        body = (
            f"הנני מבקש לבטל את הדוח שבנדון בגין {fine.violation}. בנסיבות המקרה אין "
            f"בסיס עובדתי או משפטי להטלת הקנס, ואני מבקש לקבל לעיוני את כלל הראיות "
            f"בתיק לרבות תמונות, סרטונים ומסמכים."
        )

    extension = ""
    if not fine.appeal_window_open:
        extension = (
            "\n\nכמו כן, מבקש בזאת להאריך את המועד להגשת הערעור (בקשה להארכת מועד) "
            "מהטעם שלא קיבלתי את הדוח במועד / מטעמים מוצדקים אחרים שאפרט בעת הצורך."
        )

    return (
        f"לכבוד\n{fine.source}\n\n"
        f"הנדון: ערעור על דוח מספר {fine.fine_id}\n\n"
        f"שם המבקש: {applicant_name}\n"
        f"מספר רכב: {{מספר רכב}}\n"
        f"תאריך הדוח: {fine.issued_at.isoformat()}\n"
        f"מקום: {fine.location}\n"
        f"סכום: {fine.amount_ils} ש\"ח\n\n"
        f"{body}{extension}\n\n"
        f"בכבוד רב,\n{applicant_name}\n"
        f"חתימה: ______________   תאריך: ______________\n"
    )
