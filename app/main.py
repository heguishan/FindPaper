"""FastAPI entrypoint for the FindPaper local web app."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.job_runner import job_manager, resolve_output_dir
from app.topic_extraction import extract_topic_from_pdf


app = FastAPI(title="FindPaper", version="0.1.0")
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serves the local web interface."""
    return (static_dir / "index.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
async def create_job(
    topic: str = Form(""),
    target_count: int = Form(10),
    output_dir: str = Form(""),
    paper_pdf: Optional[UploadFile] = File(None),
) -> JSONResponse:
    """Creates a paper discovery job.

    Args:
        topic: User-entered topic or keywords.
        target_count: Desired number of PDFs.
        output_dir: Output directory path.
        paper_pdf: Optional uploaded PDF used for Abstract keyword extraction.

    Returns:
        JSON payload with the created job ID.
    """
    clean_topic = topic.strip()
    if target_count < 1:
        raise HTTPException(status_code=400, detail="论文数量必须大于 0。")
    if target_count > 100:
        raise HTTPException(status_code=400, detail="单次最多请求 100 篇论文。")

    if paper_pdf and paper_pdf.filename:
        if not paper_pdf.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="上传文件必须是 PDF。")
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(await paper_pdf.read())
                tmp_path = Path(tmp_file.name)
            clean_topic = extract_topic_from_pdf(tmp_path)
        except ValueError as exc:
            if not clean_topic:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            try:
                tmp_path.unlink(missing_ok=True)  # type: ignore[name-defined]
            except Exception:
                pass

    if not clean_topic:
        raise HTTPException(status_code=400, detail="请输入主题/关键词，或上传包含 Abstract 的论文 PDF。")

    try:
        resolved_output_dir = resolve_output_dir(output_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = job_manager.create_job(clean_topic, target_count, resolved_output_dir)
    return JSONResponse({"job_id": job.job_id, "topic": job.topic})


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> JSONResponse:
    """Returns current job state."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")
    return JSONResponse(
        {
            "job_id": job.job_id,
            "topic": job.topic,
            "status": job.status,
            "message": job.message,
            "downloaded_count": job.downloaded_count,
            "failed_count": job.failed_count,
            "high_quality_count": job.high_quality_count,
            "result": job.result,
        }
    )


@app.get("/api/jobs/{job_id}/report")
async def get_report(job_id: str) -> JSONResponse:
    """Returns final job report metadata."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")
    if job.status not in {"completed", "failed"}:
        raise HTTPException(status_code=409, detail="任务尚未完成。")
    return JSONResponse(job.result)


@app.get("/api/jobs/{job_id}/events")
async def stream_events(job_id: str) -> StreamingResponse:
    """Streams job events as Server-Sent Events."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在。")

    async def event_generator():
        sent = 0
        while True:
            while sent < len(job.events):
                payload = json.dumps(job.events[sent], ensure_ascii=False)
                yield f"data: {payload}\n\n"
                sent += 1
            if job.status in {"completed", "failed"}:
                break
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/config")
async def get_config() -> JSONResponse:
    """Returns UI defaults."""
    return JSONResponse({"default_output_dir": str(settings.default_output_dir)})

