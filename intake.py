"""Extract structured fine details from user input.

Three input modes:
  1. Photo of paper ticket / SMS screenshot → Claude Vision (claude-sonnet-4-6).
  2. Pasted text (SMS body, email body) → Claude text completion.
  3. Manual entry (user types each field) — handled in bot.py directly.

The intake stage returns a parser.Fine plus a confidence score, which the
bot shows back to the user for confirmation before generating the appeal.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import re
from dataclasses import dataclass

from config import settings
from parser import Fine

logger = logging.getLogger(__name__)


@dataclass
class IntakeResult:
    fine: Fine
    confidence: str         # "high" | "medium" | "low"
    raw_extracted: dict     # what Claude returned, before normalization
    warning: str = ""


SYSTEM_PROMPT = (
    "You extract structured fine details from Israeli traffic / parking "
    "ticket photos, SMS messages, or pasted text. Return ONLY valid JSON "
    "matching this schema (no markdown, no commentary):\n"
    "{\n"
    '  "fine_id": "string — the report/ticket number (מספר דוח)",\n'
    '  "issued_at": "YYYY-MM-DD",\n'
    '  "location": "Hebrew or English address as printed",\n'
    '  "violation": "Hebrew description of the violation",\n'
    '  "amount_ils": integer,\n'
    '  "source": "Hebrew name of the issuing authority",\n'
    '  "confidence": "high|medium|low"\n'
    "}\n"
    "If a field is unreadable or absent, leave it null or omit it. The "
    "issuing authority is usually one of: עיריית תל אביב-יפו, עיריית "
    "ירושלים, עיריית חיפה, משטרת ישראל, רשות האכיפה והגבייה."
)


def from_text(text: str) -> IntakeResult:
    """Parse a pasted SMS/email/text into a Fine."""
    if not settings.anthropic_api_key:
        return _regex_fallback(text)
    try:
        data = _claude_text(text)
        return _to_intake(data)
    except Exception as exc:
        logger.warning("Claude text intake failed, using regex fallback: %s", exc)
        return _regex_fallback(text)


def from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> IntakeResult:
    """Parse a photo of a paper ticket or SMS screenshot via Claude Vision."""
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "Для распознавания фото нужен ANTHROPIC_API_KEY в .env. "
            "Без него используйте текстовый ввод или ручное заполнение."
        )
    data = _claude_image(image_bytes, mime_type)
    return _to_intake(data)


def manual(
    fine_id: str,
    issued_at: str,
    location: str,
    violation: str,
    amount_ils: int,
    source: str = "משטרת ישראל",
) -> IntakeResult:
    """Construct a Fine directly from user-entered fields (no AI)."""
    return _to_intake({
        "fine_id": fine_id,
        "issued_at": issued_at,
        "location": location,
        "violation": violation,
        "amount_ils": amount_ils,
        "source": source,
        "confidence": "high",
    })


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _claude_text(text: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Extract from this text:\n\n{text}"}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    return _parse_json(raw)


def _claude_image(image_bytes: bytes, mime_type: str) -> dict:
    from anthropic import Anthropic
    client = Anthropic(api_key=settings.anthropic_api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")
    msg = client.messages.create(
        model=settings.claude_model,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": b64}},
                {"type": "text", "text": "Extract fine details from this image."},
            ],
        }],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    # Tolerate fenced code blocks.
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)
    return json.loads(raw)


def _regex_fallback(text: str) -> IntakeResult:
    """Best-effort extraction when Claude is unavailable. Israeli SMS format
    is reasonably uniform: digits for the report number and amount, dd/mm/yyyy
    or yyyy-mm-dd for the date, Hebrew text for everything else.
    """
    fine_id_match = re.search(r"(?:דוח|דו\"ח|report|#)\s*[:\-]?\s*(\d{6,})", text, re.I)
    amount_match = re.search(r"(\d{2,5})\s*(?:ש[\"״]ח|₪|ILS|NIS)", text)
    date_match = re.search(r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})", text)

    data = {
        "fine_id": fine_id_match.group(1) if fine_id_match else "",
        "issued_at": _normalize_date(date_match.group(1)) if date_match else dt.date.today().isoformat(),
        "amount_ils": int(amount_match.group(1)) if amount_match else 0,
        "violation": text.strip()[:200],
        "location": "",
        "source": "משטרת ישראל",
        "confidence": "low",
    }
    result = _to_intake(data)
    result.warning = "Распознано через regex (Claude недоступен). Проверьте детали."
    return result


def _normalize_date(value: str) -> str:
    value = value.replace(".", "/").replace("-", "/")
    parts = value.split("/")
    if len(parts) == 3:
        d, m, y = parts
        if len(y) == 2:
            y = "20" + y
        try:
            return dt.date(int(y), int(m), int(d)).isoformat()
        except ValueError:
            pass
    return dt.date.today().isoformat()


def _to_intake(data: dict) -> IntakeResult:
    confidence = (data.get("confidence") or "medium").lower()
    try:
        issued = dt.date.fromisoformat((data.get("issued_at") or "").strip())
    except ValueError:
        issued = dt.date.today()
        confidence = "low"
    fine = Fine(
        fine_id=str(data.get("fine_id") or "").strip(),
        issued_at=issued,
        location=str(data.get("location") or "").strip(),
        violation=str(data.get("violation") or "").strip(),
        amount_ils=int(data.get("amount_ils") or 0),
        status="לא שולם",
        source=str(data.get("source") or "משטרת ישראל").strip(),
    )
    return IntakeResult(fine=fine, confidence=confidence, raw_extracted=data)
