"""Generate a self-report PDF presentation of the smoke-test session.

Run: python3 build_report.py
Output: report.pdf in the repo root.
"""

from __future__ import annotations

import datetime as dt
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

try:
    from bidi.algorithm import get_display
except ImportError:
    def get_display(text):
        return text


PAGE_W, PAGE_H = landscape(A4)
ACCENT = HexColor("#0f62fe")
DARK = HexColor("#1f2933")
MUTED = HexColor("#52606d")
BG = HexColor("#f7f8fa")
CARD = HexColor("#ffffff")
GREEN = HexColor("#0e8a3f")

pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DV-B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DV-M", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"))


def he(text: str) -> str:
    """Bidi-shape Hebrew text so it renders right-to-left in reportlab."""
    return get_display(text)


def page_chrome(c: canvas.Canvas, page_no: int, total: int) -> None:
    c.setFillColor(BG)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H - 0.4 * cm, PAGE_W, 0.4 * cm, fill=1, stroke=0)
    c.setFont("DV", 9)
    c.setFillColor(MUTED)
    c.drawString(1.5 * cm, 0.8 * cm, "Traffic Fine Appeals · Smoke-test report")
    c.drawRightString(PAGE_W - 1.5 * cm, 0.8 * cm, f"{page_no} / {total}")


def slide_title(c: canvas.Canvas) -> None:
    c.setFillColor(DARK)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    c.setFillColor(ACCENT)
    c.rect(0, PAGE_H - 1.2 * cm, PAGE_W, 1.2 * cm, fill=1, stroke=0)

    c.setFont("DV-B", 36)
    c.setFillColor(white)
    c.drawString(2.5 * cm, PAGE_H - 6 * cm, "Traffic Fine Appeals")
    c.setFont("DV", 22)
    c.setFillColor(HexColor("#9aa5b1"))
    c.drawString(2.5 * cm, PAGE_H - 7.8 * cm, "MVP smoke-test report")

    c.setFont("DV", 13)
    c.setFillColor(HexColor("#cbd2d9"))
    today = dt.date.today().isoformat()
    c.drawString(2.5 * cm, PAGE_H - 11 * cm, f"Date: {today}")
    c.drawString(2.5 * cm, PAGE_H - 11.7 * cm, "Branch: claude/traffic-fine-appeals-bHjTK")
    c.drawString(2.5 * cm, PAGE_H - 12.4 * cm, "Stack: aiogram 3 · Claude Sonnet 4.6 · reportlab")


def slide_heading(c: canvas.Canvas, title: str, subtitle: str = "") -> float:
    c.setFont("DV-B", 24)
    c.setFillColor(DARK)
    c.drawString(1.5 * cm, PAGE_H - 2.2 * cm, title)
    if subtitle:
        c.setFont("DV", 13)
        c.setFillColor(MUTED)
        c.drawString(1.5 * cm, PAGE_H - 3.0 * cm, subtitle)
    return PAGE_H - 4.0 * cm


def card(c: canvas.Canvas, x: float, y: float, w: float, h: float, title: str, lines: list[tuple[str, str]]):
    c.setFillColor(CARD)
    c.setStrokeColor(HexColor("#e4e7eb"))
    c.roundRect(x, y, w, h, 6, fill=1, stroke=1)
    c.setFont("DV-B", 11)
    c.setFillColor(MUTED)
    c.drawString(x + 0.6 * cm, y + h - 0.9 * cm, title.upper())
    cy = y + h - 1.7 * cm
    for label, value in lines:
        c.setFont("DV", 10)
        c.setFillColor(MUTED)
        c.drawString(x + 0.6 * cm, cy, label)
        c.setFont("DV-B", 12)
        c.setFillColor(DARK)
        c.drawRightString(x + w - 0.6 * cm, cy, value)
        cy -= 0.7 * cm


def bullets(c: canvas.Canvas, x: float, y: float, items: list[str], font_size: int = 12, line_height: float = 0.75):
    for item in items:
        c.setFont("DV-B", font_size)
        c.setFillColor(ACCENT)
        c.drawString(x, y, "•")
        c.setFont("DV", font_size)
        c.setFillColor(DARK)
        c.drawString(x + 0.5 * cm, y, item)
        y -= line_height * cm
    return y


def slide_architecture(c: canvas.Canvas) -> None:
    page_chrome(c, 2, TOTAL_PAGES)
    y = slide_heading(c, "Что построено", "Чистый старт в корне репозитория · ~520 строк Python")

    modules = [
        ("config.py", "Загрузка env: TG_BOT_TOKEN, ANTHROPIC_API_KEY, LLM_MODE, PARSER_MODE"),
        ("parser.py", "lookup(plate) → LookupResult · 2 режима: mock / live (gov.il)"),
        ("templates.py", "Анализ оснований + рендер писем на иврите (3 сценария)"),
        ("llm.py", "build_appeal() · Claude или шаблоны, авто-переключение"),
        ("bot.py", "aiogram 3: /start → номер → отчёт + .txt с письмами"),
        ("requirements.txt", "aiogram, anthropic, requests, python-dotenv"),
    ]

    c.setFont("DV-M", 11)
    for name, desc in modules:
        c.setFillColor(ACCENT)
        c.setFont("DV-M", 12)
        c.drawString(1.5 * cm, y, name)
        c.setFont("DV", 11)
        c.setFillColor(DARK)
        c.drawString(6.0 * cm, y, desc)
        y -= 0.8 * cm

    y -= 0.5 * cm
    c.setStrokeColor(HexColor("#e4e7eb"))
    c.line(1.5 * cm, y, PAGE_W - 1.5 * cm, y)
    y -= 0.8 * cm

    c.setFont("DV-B", 13)
    c.setFillColor(DARK)
    c.drawString(1.5 * cm, y, "Pipeline:")
    y -= 0.7 * cm

    steps = [
        "Telegram → bot.py получает номер машины (8 цифр)",
        "parser.lookup(plate) → 3 штрафа из mock-источника",
        "templates.analyse(fine) → классификация + основания для апелляции",
        "llm.build_appeal(fine) → Claude API ИЛИ template fallback",
        "bot отправляет PDF/TXT с письмом на иврите для копи-пасты",
    ]
    bullets(c, 1.8 * cm, y, steps, font_size=11, line_height=0.7)


def slide_parser_test(c: canvas.Canvas) -> None:
    page_chrome(c, 3, TOTAL_PAGES)
    y = slide_heading(c, "Тест #1 · Парсер", "PARSER_MODE=mock · lookup('12345678')")

    card(c, 1.5 * cm, y - 4 * cm, 8 * cm, 4 * cm, "Результат", [
        ("Plate", "12345678"),
        ("Fines found", "3"),
        ("Total amount", "1 500 ₪"),
        ("Error", "—"),
    ])

    card(c, 10.5 * cm, y - 4 * cm, 17 * cm, 4 * cm, "Покрытие", [
        ("Парковка (Тель-Авив)", "250 ₪ · 12 дн."),
        ("Скорость (трасса 4)", "750 ₪ · 4 дн."),
        ("Bus-lane (Иерусалим)", "500 ₪ · 47 дн. (срок истёк)"),
    ])

    y -= 5.5 * cm
    c.setFont("DV-B", 13)
    c.setFillColor(DARK)
    c.drawString(1.5 * cm, y, "Что проверено:")
    y -= 0.8 * cm
    bullets(c, 1.8 * cm, y, [
        "normalize_plate() корректно отфильтровывает не-цифры",
        "Возвращает LookupResult с .total_amount и .fines",
        "Каждый Fine имеет .days_old и .appeal_window_open (30-дневное правило)",
        "Mock-режим работает без сети и без капчи",
    ], font_size=11)


def slide_template_test(c: canvas.Canvas) -> None:
    page_chrome(c, 4, TOTAL_PAGES)
    y = slide_heading(c, "Тест #2 · Шаблонный генератор", "LLM_MODE=template · fallback без API")

    c.setFillColor(CARD)
    c.setStrokeColor(HexColor("#e4e7eb"))
    c.roundRect(1.5 * cm, 1.5 * cm, PAGE_W - 3 * cm, y - 1.5 * cm, 6, fill=1, stroke=1)

    c.setFont("DV-B", 12)
    c.setFillColor(MUTED)
    c.drawString(1.9 * cm, y - 0.8 * cm, "ВЫХОД · штраф #1 · парковка, Тель-Авив, 250 ₪")

    sample = [
        "לכבוד",
        "עיריית תל אביב",
        "",
        "הנדון: ערעור על דוח מספר MOT-5678-001",
        "",
        "שם המבקש: ____________",
        "מספר רכב: {מספר רכב}",
        "תאריך הדוח: 2026-04-28",
        "מקום: רחוב אלנבי 45, תל אביב",
        "סכום: 250 ש\"ח",
        "",
        "הנני מבקש לבטל את הדוח שבנדון בגין חניה במקום אסור...",
        "",
        "בכבוד רב,",
        "____________",
    ]

    c.setFont("DV", 10)
    c.setFillColor(DARK)
    text_x = PAGE_W - 1.9 * cm
    ty = y - 1.6 * cm
    for line in sample:
        c.drawRightString(text_x, ty, he(line))
        ty -= 0.45 * cm

    ty -= 0.2 * cm
    c.setFont("DV-B", 11)
    c.setFillColor(MUTED)
    c.drawString(1.9 * cm, ty, "ОЦЕНКА")
    ty -= 0.6 * cm
    bullets(c, 2.1 * cm, ty, [
        "~15 строк · только базовая структура",
        "Один аргумент защиты, без юридической детализации",
        "Подходит как fallback, но не как продаваемый продукт",
    ], font_size=10, line_height=0.55)


def slide_claude_test(c: canvas.Canvas) -> None:
    page_chrome(c, 5, TOTAL_PAGES)
    y = slide_heading(c, "Тест #3 · Claude Sonnet 4.6", "LLM_MODE=claude · реальный вызов API")

    c.setFillColor(CARD)
    c.setStrokeColor(HexColor("#e4e7eb"))
    c.roundRect(1.5 * cm, 1.5 * cm, PAGE_W - 3 * cm, y - 1.5 * cm, 6, fill=1, stroke=1)

    c.setFont("DV-B", 12)
    c.setFillColor(MUTED)
    c.drawString(1.9 * cm, y - 0.8 * cm, "ВЫХОД · штраф #1 · парковка, Тель-Авив, 250 ₪")

    sample = [
        "לכבוד",
        "מחלקת תנועה ואכיפה חניה",
        "עיריית תל אביב-יפו",
        "",
        "נושא: ערר על דוח חניה מספר MOT-5678-001",
        "",
        "אני הח\"מ, ישראל ישראלי, ת\"ז {מספר ת.ז.}, בעל רכב {מספר רכב}...",
        "",
        "נימוקי הערר:",
        "1. ספק בדבר קיומה של תמרורית ברורה במקום",
        "   — בהתאם לתקנות התעבורה ולפסיקה...",
        "",
        "2. היעדר תיעוד צילומי בתיק העבירה",
        "   — הנטל להוכחת ביצוע מוטל על הרשות...",
        "",
        "סיכום וסעד המבוקש:",
        "מתבקשת הרשות לבטל את דוח החניה...",
    ]

    c.setFont("DV", 9.5)
    c.setFillColor(DARK)
    text_x = PAGE_W - 1.9 * cm
    ty = y - 1.6 * cm
    for line in sample:
        c.drawRightString(text_x, ty, he(line))
        ty -= 0.42 * cm

    ty -= 0.3 * cm
    c.setFont("DV-B", 11)
    c.setFillColor(GREEN)
    c.drawString(1.9 * cm, ty, "ОЦЕНКА")
    ty -= 0.6 * cm
    bullets(c, 2.1 * cm, ty, [
        "43 строки · 1859 символов · юридически структурировано",
        "Точный адресат, ссылки на правила движения, резерв права на суд",
        "Полноценный продаваемый артефакт",
    ], font_size=10, line_height=0.55)


def slide_metrics(c: canvas.Canvas) -> None:
    page_chrome(c, 6, TOTAL_PAGES)
    y = slide_heading(c, "Метрики и юнит-экономика")

    card(c, 1.5 * cm, y - 5 * cm, 8.5 * cm, 5 * cm, "Claude API call", [
        ("Model", "claude-sonnet-4-6"),
        ("max_tokens", "2 000"),
        ("Input (smoke test)", "~250 tok"),
        ("Output (smoke test)", "~700 tok"),
        ("Latency (subj.)", "~6–10 сек"),
    ])

    card(c, 11.0 * cm, y - 5 * cm, 8.5 * cm, 5 * cm, "Стоимость 1 письма", [
        ("Input ($3/M)", "$0.00075"),
        ("Output ($15/M)", "$0.0105"),
        ("Итого 1 письмо", "~$0.011"),
        ("Отчёт = 3 письма", "~$0.034"),
        ("На $5 кредитов", "~150 отчётов"),
    ])

    card(c, 20.5 * cm, y - 5 * cm, 8.5 * cm, 5 * cm, "Цена клиенту", [
        ("1 отчёт", "49 ₪ (~$13)"),
        ("Подписка/мес", "99 ₪ (~$27)"),
        ("Себестоимость", "$0.034"),
        ("Маржа на отчёт", "~99%"),
        ("Break-even", "1 клиент"),
    ])

    y -= 6.5 * cm
    c.setFont("DV-B", 13)
    c.setFillColor(DARK)
    c.drawString(1.5 * cm, y, "Качественные находки:")
    y -= 0.8 * cm
    bullets(c, 1.8 * cm, y, [
        "max_tokens=900 обрезал письма на середине → поднят до 2000 (commit 9577090)",
        "Шаблонные письма на иврите валидны, но «дёшево выглядят» — годятся как fallback",
        "Claude корректно классифицирует и адаптирует язык под тип нарушения",
        "RTL и плейсхолдеры в иврите сохраняются корректно",
    ], font_size=11, line_height=0.7)


def slide_status(c: canvas.Canvas) -> None:
    page_chrome(c, 7, TOTAL_PAGES)
    y = slide_heading(c, "Статус и следующие шаги")

    c.setFont("DV-B", 14)
    c.setFillColor(GREEN)
    c.drawString(1.5 * cm, y, "✓ Готово")
    y -= 0.8 * cm
    bullets(c, 1.8 * cm, y, [
        "MVP-каркас: parser + analyser + LLM-генератор + Telegram-бот",
        "Smoke-test парсера (3 штрафа, 1500 ₪)",
        "Smoke-test шаблонов (3 типа нарушений)",
        "Smoke-test Claude API (валидный иврит, юр. структура)",
        "Commits ce0f60b + 9577090 запушены на claude/traffic-fine-appeals-bHjTK",
    ], font_size=11, line_height=0.65)

    y -= 4.5 * cm
    c.setFont("DV-B", 14)
    c.setFillColor(HexColor("#c2410c"))
    c.drawString(1.5 * cm, y, "→ Дальше")
    y -= 0.8 * cm
    bullets(c, 1.8 * cm, y, [
        "Live-парсер: интеграция 2captcha + Playwright для gov.il и муниципалитетов",
        "Платежи: Bit / PayBox webhook, отдача писем только после оплаты",
        "PDF-отчёт вместо .txt (через тот же reportlab)",
        "Маркетинг: посты в FB-группах «Авто Израиль» / «Русский Израиль» — first 5 free",
        "Подписка: APScheduler, автопроверка раз в 2 недели",
    ], font_size=11, line_height=0.65)


SLIDES = [slide_title, slide_architecture, slide_parser_test, slide_template_test, slide_claude_test, slide_metrics, slide_status]
TOTAL_PAGES = len(SLIDES)


def build(path: str = "report.pdf") -> None:
    c = canvas.Canvas(path, pagesize=landscape(A4))
    c.setTitle("Traffic Fine Appeals — Smoke-test report")
    for slide in SLIDES:
        slide(c)
        c.showPage()
    c.save()


if __name__ == "__main__":
    build()
    print("report.pdf generated")
