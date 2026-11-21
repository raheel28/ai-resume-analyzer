"""FastAPI entry point. Run with: uvicorn app.main:app --reload"""

from __future__ import annotations

import json
import os
import time
import re
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.ai.match_review import review_match
from app.ai.review import review_resume
from app.ats.checks import find_bullets
from app.ats.score import analyse
from app.edit.apply import (add_skills_to_lines, apply_to_lines, edit_docx_in_place,
                            validate_changes, validate_skills)
from app.edit.render import build_model, fit_one_page, render_docx, render_pdf
from app import metrics
from app.ratelimit import RateLimiter, client_ip, friendly_wait
from app.llm.client import LLMError, LLMNotConfigured, get_client
from app.jd.match import JDError, keyword_match, read_jd
from app.parsing.extract import ExtractedDocument, UnsupportedFileError, extract
from app.parsing.sections import split_sections

MAX_BYTES = 5 * 1024 * 1024

app = FastAPI(title="AI Resume Analyzer", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Applied-Count", "X-Not-Found-Count",
                    "X-Skills-Added", "X-Pages"],
)

# AI calls spend the Gemini quota, so they get a tight per-IP limit.
AI_LIMIT = RateLimiter(os.getenv("AI_RATE_LIMIT", "10/hour"))
BASIC_LIMIT = RateLimiter(os.getenv("BASIC_RATE_LIMIT", "60/minute"))


def _limited(limiter: RateLimiter, what: str):
    def dependency(request: Request) -> None:
        ip = client_ip(dict(request.headers), request.client.host if request.client else None)
        wait = limiter.check(ip)
        if wait is not None:
            raise HTTPException(
                429,
                f"Too many {what} from your connection. Try again in {friendly_wait(wait)}.",
                headers={"Retry-After": str(int(wait))},
            )
    return Depends(dependency)


ai_limit = _limited(AI_LIMIT, "AI reviews")
basic_limit = _limited(BASIC_LIMIT, "requests")

MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


async def _read_resume(file: UploadFile) -> ExtractedDocument:
    return (await _read_resume_with_bytes(file))[1]


async def _read_resume_with_bytes(file: UploadFile) -> tuple[bytes, ExtractedDocument]:
    data = await file.read()
    if not data:
        raise HTTPException(400, "The file is empty")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File is larger than 5 MB")
    try:
        return data, extract(file.filename or "", data)
    except UnsupportedFileError as exc:
        raise HTTPException(415, str(exc)) from exc
    except Exception as exc:  # corrupt PDFs raise a variety of errors
        raise HTTPException(422, "Couldn't read this file. Is it a valid PDF or DOCX?") from exc


@app.get("/api/health")
def health() -> dict:
    try:
        get_client()
        ai = True
    except LLMNotConfigured:
        ai = False
    return {"status": "ok", "ai_enabled": ai}


@app.post("/api/analyze", dependencies=[basic_limit])
async def analyze(file: UploadFile = File(...)) -> dict:
    """Rule-based ATS check. Fast, free, deterministic."""
    doc = await _read_resume(file)
    report = analyse(doc)
    report["file"] = {"name": file.filename, "type": doc.file_type,
                      "pages": doc.page_count, "words": doc.word_count}
    return report


@app.post("/api/ai-review", dependencies=[ai_limit])
async def ai_review(file: UploadFile = File(...), target_role: str = Form("")) -> dict:
    """LLM rubric rating + guarded bullet rewrites. Slower and costs API calls,
    so the frontend calls it separately after /api/analyze."""
    doc = await _read_resume(file)
    if doc.word_count < 50:
        raise HTTPException(422, "Not enough text in the resume for an AI review")
    try:
        client = get_client()
    except LLMNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc

    bullets = find_bullets(split_sections(doc.lines))
    started = time.monotonic()
    try:
        # The SDK call is blocking; keep it off the event loop.
        result = await run_in_threadpool(review_resume, client, doc.text, bullets,
                                         target_role[:100] or None)
    except LLMError as exc:
        metrics.record(metrics.ai_event("ai-review", client, started, error=str(exc)))
        raise HTTPException(502, f"AI review failed: {exc}") from exc
    metrics.record(metrics.ai_event("ai-review", client, started, result))
    return result

async def _read_jd(jd_text: str, jd_file: UploadFile | None) -> str:
    data = await jd_file.read() if jd_file is not None else None
    try:
        return read_jd(jd_text, jd_file.filename if jd_file else None, data)
    except JDError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/match", dependencies=[basic_limit])
async def match(file: UploadFile = File(...), jd_text: str = Form(""),
                jd_file: UploadFile | None = File(None)) -> dict:
    """Rule-based keyword match between resume and job description. Fast and deterministic."""
    jd = await _read_jd(jd_text, jd_file)
    doc = await _read_resume(file)
    result = keyword_match(doc.text, jd)
    result["file"] = {"name": file.filename, "type": doc.file_type, "words": doc.word_count}
    result["jd_preview"] = jd[:300]
    return result


@app.post("/api/ai-match", dependencies=[ai_limit])
async def ai_match(file: UploadFile = File(...), jd_text: str = Form(""),
                   jd_file: UploadFile | None = File(None)) -> dict:
    """AI fit review against the job description, with job-tailored guarded rewrites."""
    jd = await _read_jd(jd_text, jd_file)
    doc = await _read_resume(file)
    if doc.word_count < 50:
        raise HTTPException(422, "Not enough text in the resume for an AI review")
    try:
        client = get_client()
    except LLMNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc

    bullets = find_bullets(split_sections(doc.lines))
    kw = keyword_match(doc.text, jd)
    keyword_skills = [r["skill"] for r in kw["skills"]]
    started = time.monotonic()
    try:
        result = await run_in_threadpool(review_match, client, doc.text, bullets, jd, keyword_skills)
    except LLMError as exc:
        metrics.record(metrics.ai_event("ai-match", client, started, error=str(exc)))
        raise HTTPException(502, f"AI review failed: {exc}") from exc
    event = metrics.ai_event("ai-match", client, started, result)
    event["keyword_score"] = kw["score"]
    metrics.record(event)
    return result


@app.post("/api/apply", dependencies=[basic_limit])
async def apply_changes(
    file: UploadFile = File(...),
    changes: str = Form("[]"),         # JSON: [{"original": "...", "replacement": "..."}]
    add_skills: str = Form("[]"),      # JSON: ["Docker", "AWS"], skills the user confirmed they have
    format: str = Form("docx"),        # "docx" | "pdf"
    keep_layout: bool = Form(True),    # DOCX uploads only: edit the original file in place
) -> Response:
    """Apply accepted changes and return the updated resume as a download.
    With no changes, returns an ATS-clean rebuild of the resume."""
    if format not in MIME:
        raise HTTPException(400, "format must be 'docx' or 'pdf'")
    try:
        parsed = validate_changes(json.loads(changes or "[]"))
        skills = validate_skills(json.loads(add_skills or "[]"))
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "changes and add_skills must be valid JSON") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    data, doc = await _read_resume_with_bytes(file)
    in_place = doc.file_type == "docx" and format == "docx" and keep_layout
    pages = None  # unknown for in-place DOCX edits (Word decides the layout)

    if in_place and not parsed and not skills:
        raise HTTPException(422, "Nothing to change. Select some changes, or untick "
                                 "'Keep my original layout' to get an ATS-clean rebuild.")

    if in_place:
        out, result = edit_docx_in_place(data, parsed, skills)
    else:
        lines, result = apply_to_lines(doc.lines, parsed)
        lines, result.skills_added = add_skills_to_lines(lines, skills)
        model = build_model(lines, doc.links)
        # Pick the most comfortable layout that fits on ONE page; the DOCX uses the
        # same sizes (Calibri is narrower than Helvetica, so it fits too).
        layout, pages = fit_one_page(model)
        out = render_docx(model, layout) if format == "docx" else render_pdf(model, layout)

    if parsed and not result.applied and not result.skills_added:
        raise HTTPException(422, "None of the selected bullets could be found in the resume")

    stem = re.sub(r"[^\w.-]+", "_", Path(file.filename or "resume").stem)[:60] or "resume"
    suffix = "updated" if (parsed or skills) else "ats_clean"
    return Response(
        content=out,
        media_type=MIME[format],
        headers={
            "Content-Disposition": f'attachment; filename="{stem}_{suffix}.{format}"',
            "X-Applied-Count": str(len(result.applied)),
            "X-Not-Found-Count": str(len(result.not_found)),
            "X-Skills-Added": str(len(result.skills_added)),
            **({"X-Pages": str(pages)} if pages else {}),
        },
    )


# ---------------------------------------------------------------- frontend
# In the single-service deploy (root Dockerfile) the built React app is copied
# to STATIC_DIR and served from "/", so one URL serves both site and API.
# Mounted last, so every /api/... route above takes priority.
_static_dir = Path(os.getenv("STATIC_DIR", Path(__file__).resolve().parent.parent / "static"))
if _static_dir.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")
