"""LLM-backed appeal letter generation with template fallback.

Switching logic lives in `config.Settings.use_claude`:

* If `LLM_MODE=claude` -> Claude only (raises if API call fails).
* If `LLM_MODE=template` -> never calls Claude.
* If `LLM_MODE=auto` (default) -> Claude when key present, else templates.
"""

from __future__ import annotations

import logging

from config import settings
from parser import Fine
from templates import Analysis, analyse, render_letter

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are an Israeli legal-assistant drafting formal appeal letters in Hebrew "
    "to municipal and Ministry of Transport authorities. Output ONLY the Hebrew "
    "letter body — no greetings to the user, no English, no markdown. Use "
    "neutral, respectful legal register. Always include: addressee, subject "
    "line with report number, applicant identification placeholders, the "
    "grounds for appeal grounded in the provided facts, and a closing."
)


def build_appeal(fine: Fine, applicant_name: str = "____________") -> tuple[Analysis, str]:
    analysis = analyse(fine)
    if settings.use_claude:
        try:
            letter = _claude_letter(fine, analysis, applicant_name)
            return analysis, letter
        except Exception as exc:
            logger.warning("Claude call failed, falling back to template: %s", exc)
            if settings.llm_mode == "claude":
                raise
    return analysis, render_letter(fine, analysis, applicant_name)


def _claude_letter(fine: Fine, analysis: Analysis, applicant_name: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user_prompt = (
        "Draft a Hebrew appeal letter for this fine. Ground the appeal in the "
        "listed reasons. Keep placeholders like {מספר רכב} where data is "
        "unknown.\n\n"
        f"Applicant name: {applicant_name}\n"
        f"Fine ID: {fine.fine_id}\n"
        f"Issued: {fine.issued_at.isoformat()} ({fine.days_old} days ago)\n"
        f"Authority: {fine.source}\n"
        f"Location: {fine.location}\n"
        f"Violation: {fine.violation}\n"
        f"Amount: {fine.amount_ils} ILS\n"
        f"Status: {fine.status}\n"
        f"Notes: {fine.notes or '-'}\n"
        f"Appeal window open: {fine.appeal_window_open}\n"
        f"Grounds:\n- " + "\n- ".join(analysis.grounds)
    )

    message = client.messages.create(
        model=settings.claude_model,
        max_tokens=900,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in message.content if block.type == "text").strip()
