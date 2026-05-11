"""Hebrew appeal letter templates + rule-based analyser.

Produces both a Hebrew letter (fallback when Claude is unavailable) and a
structured Analysis with grounds, recommended actions, success probability,
deadline, and evidence to request — used by the bot to compose a detailed
client report.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from parser import Fine


@dataclass
class Analysis:
    appealable: bool
    grounds: list[str] = field(default_factory=list)
    risk_note: str = ""
    success_probability: str = ""        # "низкая" | "средняя" | "высокая"
    success_score: int = 0               # 0..100
    deadline: str = ""                   # human-readable
    recommended_actions: list[str] = field(default_factory=list)
    evidence_to_request: list[str] = field(default_factory=list)
    estimated_savings_ils: int = 0
    category: str = ""                   # "parking" | "speed" | "bus_lane" | "other"


PARKING_KEYWORDS = ("חניה", "חנייה")
SPEED_KEYWORDS = ("מהירות",)
BUS_LANE_KEYWORDS = ("נתיב תחבורה", "נת\"צ", "נת״צ")


def analyse(fine: Fine) -> Analysis:
    category = _classify(fine)
    grounds: list[str] = []
    actions: list[str] = []
    evidence: list[str] = []
    score = 40                                   # neutral baseline

    if category == "parking":
        grounds.append("Парковочный штраф — проверить наличие чёткого знака на месте.")
        actions.append("Сфотографируйте место парковки с явно видимым (или отсутствующим) знаком.")
        evidence.append("Фотография знака с привязкой к адресу")
        evidence.append("Снимок инспектора из дела (запросить через רשות)")
        score += 15
        if "ללא תמונה" in fine.notes or not fine.photo_url:
            grounds.append("В деле нет фото — затрудняет доказательство нарушения.")
            score += 20
    elif category == "speed":
        grounds.append("Скоростной штраф — запросить калибровку радара и фото.")
        actions.append("Запросить копию תעודת כיול (сертификат калибровки) радара.")
        actions.append("Запросить фото момента нарушения и метаданные времени/места.")
        evidence.append("תעודת כיול радара")
        evidence.append("Фото машины с привязкой к радару")
        evidence.append("Запись о прохождении ТО рекордера")
        score += 5
    elif category == "bus_lane":
        grounds.append("Полоса общ. транспорта — проверить разрешённые часы и категорию ТС.")
        actions.append("Проверьте часы работы полосы на месте (фото знака).")
        actions.append("Проверьте назначение полосы — некоторые открыты для такси/электрокаров.")
        evidence.append("Фото знака часов работы полосы")
        score += 10
    else:
        grounds.append("Стандартное обжалование на основании сомнений в фактических обстоятельствах.")
        score -= 5

    if fine.appeal_window_open:
        days_left = max(0, 30 - fine.days_old)
        risk_note = f"Срок апелляции (30 дней) ещё открыт — осталось {days_left} дн."
        deadline = (dt.date.today() + dt.timedelta(days=days_left)).isoformat()
        actions.insert(0, f"Подать апелляцию до {deadline} (через {days_left} дн.).")
    else:
        risk_note = (
            "Стандартный срок (30 дней) пропущен — нужно ходатайство о восстановлении срока "
            "(בקשה להארכת מועד) с объяснением задержки."
        )
        deadline = "просрочен — подавать ходатайство о восстановлении срока"
        grounds.append("Подать ходатайство о восстановлении срока обжалования.")
        actions.insert(0, "Приложить к апелляции בקשה להארכת מועד с причиной задержки.")
        score -= 25

    score = max(5, min(95, score))
    if score >= 65:
        probability = "высокая"
    elif score >= 40:
        probability = "средняя"
    else:
        probability = "низкая"

    return Analysis(
        appealable=True,
        grounds=grounds,
        risk_note=risk_note,
        success_probability=probability,
        success_score=score,
        deadline=deadline,
        recommended_actions=actions,
        evidence_to_request=evidence,
        estimated_savings_ils=int(fine.amount_ils * score / 100),
        category=category,
    )


def _classify(fine: Fine) -> str:
    text = fine.violation
    if any(k in text for k in PARKING_KEYWORDS):
        return "parking"
    if any(k in text for k in SPEED_KEYWORDS):
        return "speed"
    if any(k in text for k in BUS_LANE_KEYWORDS):
        return "bus_lane"
    return "other"


def render_letter(fine: Fine, analysis: Analysis, applicant_name: str = "____________") -> str:
    if analysis.category == "parking":
        body = (
            f"הנני מבקש לבטל את הדוח שבנדון בגין {fine.violation} ברחוב {fine.location}, "
            f"שכן במקום בו חניתי לא היה תמרור ברור האוסר חניה, ולפי הצילום בתיק לא ניתן "
            f"להוכיח את העבירה הנטענת."
        )
    elif analysis.category == "speed":
        body = (
            f"הנני מבקש לבטל את הדוח שבנדון בגין {fine.violation} ב-{fine.location}. "
            f"אני מבקש לעיין בתעודת הכיול של מכשיר המדידה, בתמונת העבירה ובפרטי "
            f"השוטר/הבוחן. ללא ראיות אלה אין לבסס את האשמה."
        )
    elif analysis.category == "bus_lane":
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
