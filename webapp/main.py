"""FastAPI web app for the fines-appeal service.

Reuses the same modules as the Telegram bot:
  intake.from_image / from_text / manual  → parse user input
  templates.analyse                       → grounds / score / deadline
  llm.build_appeal                        → Hebrew letter (Claude or template)
  pdf_appeal.render_appeal_pdf            → A4 RTL PDF

Endpoints:
  GET  /                  → single-page UI (static/index.html)
  POST /api/extract       → multipart form OR JSON, returns parsed Fine
  POST /api/appeal        → JSON with Fine fields, returns PDF download
"""

from __future__ import annotations

import datetime as dt
import io
import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from intake import from_image, from_text, manual
from llm import build_appeal
from parser import Fine
from pdf_appeal import render_appeal_pdf
from templates import analyse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Traffic Fine Appeals")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class FineIn(BaseModel):
    fine_id: str = ""
    issued_at: str = ""
    location: str = ""
    violation: str = ""
    amount_ils: int = 0
    source: str = "משטרת ישראל"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/extract")
async def extract(
    text: str | None = Form(default=None),
    image: UploadFile | None = File(default=None),
):
    if image is not None:
        data = await image.read()
        mime = image.content_type or "image/jpeg"
        try:
            result = from_image(data, mime)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
    elif text:
        result = from_text(text)
    else:
        raise HTTPException(status_code=400, detail="Need image or text")
    return {
        "confidence": result.confidence,
        "warning": result.warning,
        "fine": {
            "fine_id": result.fine.fine_id,
            "issued_at": result.fine.issued_at.isoformat(),
            "location": result.fine.location,
            "violation": result.fine.violation,
            "amount_ils": result.fine.amount_ils,
            "source": result.fine.source,
        },
    }


@app.post("/api/appeal")
def appeal(body: FineIn):
    try:
        issued = dt.date.fromisoformat(body.issued_at) if body.issued_at else dt.date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad issued_at format, expected YYYY-MM-DD")

    fine = Fine(
        fine_id=body.fine_id,
        issued_at=issued,
        location=body.location,
        violation=body.violation,
        amount_ils=body.amount_ils,
        status="לא שולם",
        source=body.source,
    )
    _, letter = build_appeal(fine)
    pdf_bytes = render_appeal_pdf(fine, letter)

    # HTTP headers must be Latin-1; the analysis fields use Cyrillic/Hebrew,
    # so the UI fetches them separately via /api/analyse before the PDF call.
    safe_filename = "".join(c for c in (fine.fine_id or "unknown") if c.isalnum() or c in "-_") or "unknown"
    headers = {"Content-Disposition": f'attachment; filename="appeal_{safe_filename}.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.post("/api/analyse")
def analyse_only(body: FineIn):
    """Cheap pre-flight: returns the structured analysis without generating
    the PDF. Used by the UI to render the results panel before the user
    commits to the (paid) PDF download."""
    try:
        issued = dt.date.fromisoformat(body.issued_at) if body.issued_at else dt.date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Bad issued_at format")
    fine = Fine(
        fine_id=body.fine_id,
        issued_at=issued,
        location=body.location,
        violation=body.violation,
        amount_ils=body.amount_ils,
        status="לא שולם",
        source=body.source,
    )
    a = analyse(fine)
    return {
        "appealable": a.appealable,
        "category": a.category,
        "grounds": a.grounds,
        "recommended_actions": a.recommended_actions,
        "evidence_to_request": a.evidence_to_request,
        "success_probability": a.success_probability,
        "success_score": a.success_score,
        "estimated_savings_ils": a.estimated_savings_ils,
        "deadline": a.deadline,
        "risk_note": a.risk_note,
    }


@app.get("/healthz")
def healthz():
    return {"ok": True}
