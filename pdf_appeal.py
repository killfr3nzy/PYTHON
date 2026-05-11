"""Render a Hebrew appeal letter as an A4 PDF.

reportlab + python-bidi handle the RTL shaping: each text line is bidi-shaped
before being written via `drawRightString`. The DejaVu Sans TrueType font
contains the Hebrew glyphs.

Returns the PDF as bytes so the bot can send it directly via Telegram
without touching the filesystem.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from bidi.algorithm import get_display
from reportlab.lib.colors import HexColor, black, grey
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from parser import Fine

PAGE_W, PAGE_H = A4
MARGIN_X = 2.0 * cm
MARGIN_TOP = 2.0 * cm
MARGIN_BOTTOM = 2.0 * cm
LINE_HEIGHT = 0.55 * cm
BODY_FONT_SIZE = 11
WRAP_CHARS = 85

_FONTS_REGISTERED = False


def _register_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DV-B", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
    _FONTS_REGISTERED = True


def render_appeal_pdf(fine: Fine, letter: str, applicant_name: str = "____________") -> bytes:
    """Build the PDF and return it as bytes."""
    _register_fonts()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Appeal {fine.fine_id}")
    c.setAuthor("Traffic Fine Appeals Bot")

    state = {"y": PAGE_H - MARGIN_TOP, "page": 1}

    _draw_header(c, fine, applicant_name, state)
    _draw_letter_body(c, letter, state)
    _draw_footer(c, state["page"])
    c.save()
    return buf.getvalue()


def _draw_header(c, fine: Fine, applicant_name: str, state: dict) -> None:
    # Logo-bar
    c.setFillColor(HexColor("#0f62fe"))
    c.rect(0, PAGE_H - 0.8 * cm, PAGE_W, 0.8 * cm, fill=1, stroke=0)
    c.setFont("DV-B", 11)
    c.setFillColor(HexColor("#ffffff"))
    c.drawString(MARGIN_X, PAGE_H - 0.55 * cm, "Traffic Fine Appeal")
    c.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 0.55 * cm, _shape(f"דוח מספר {fine.fine_id}"))

    y = PAGE_H - MARGIN_TOP
    c.setFillColor(black)

    # Block: case data
    c.setFont("DV", 9)
    c.setFillColor(HexColor("#52606d"))
    facts = [
        ("Орган / רשות:", fine.source),
        ("Номер штрафа / מספר דוח:", fine.fine_id),
        ("Дата / תאריך:", fine.issued_at.isoformat()),
        ("Локация / מקום:", fine.location),
        ("Нарушение / עבירה:", fine.violation),
        ("Сумма / סכום:", f'{fine.amount_ils} ש"ח'),
        ("Заявитель / מבקש:", applicant_name),
    ]
    for label, value in facts:
        c.setFont("DV", 9)
        c.setFillColor(HexColor("#52606d"))
        c.drawString(MARGIN_X, y, label)
        c.setFont("DV-B", 10)
        c.setFillColor(black)
        c.drawRightString(PAGE_W - MARGIN_X, y, _shape(str(value)))
        y -= 0.5 * cm

    y -= 0.3 * cm
    c.setStrokeColor(HexColor("#cbd2d9"))
    c.line(MARGIN_X, y, PAGE_W - MARGIN_X, y)
    state["y"] = y - 0.8 * cm


def _draw_letter_body(c, letter: str, state: dict) -> None:
    c.setFont("DV", BODY_FONT_SIZE)
    c.setFillColor(black)

    for paragraph in letter.split("\n"):
        if not paragraph.strip():
            state["y"] -= LINE_HEIGHT
            _maybe_new_page(c, state)
            continue
        for line in _wrap_he(paragraph, WRAP_CHARS):
            c.drawRightString(PAGE_W - MARGIN_X, state["y"], _shape(line))
            state["y"] -= LINE_HEIGHT
            _maybe_new_page(c, state)


def _draw_footer(c, page_no: int) -> None:
    c.setFont("DV", 8)
    c.setFillColor(grey)
    c.drawString(MARGIN_X, 1.0 * cm,
                 "Сгенерировано автоматически. Для подачи — скопируйте текст в форму подачи апелляции или приложите этот PDF.")
    c.drawRightString(PAGE_W - MARGIN_X, 1.0 * cm, f"Page {page_no}")


def _maybe_new_page(c, state: dict) -> None:
    if state["y"] > MARGIN_BOTTOM:
        return
    _draw_footer(c, state["page"])
    c.showPage()
    state["page"] += 1
    state["y"] = PAGE_H - MARGIN_TOP
    c.setFont("DV", BODY_FONT_SIZE)
    c.setFillColor(black)


def _shape(text: str) -> str:
    return get_display(text)


def _wrap_he(text: str, width: int) -> list[str]:
    """Word-wrap Hebrew/Russian text. Avoids breaking mid-word."""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 <= width:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
