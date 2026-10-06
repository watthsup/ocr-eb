"""Document processing endpoints: submit, poll, edit, export, raw OCR."""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.core.config import settings
from app.models.schemas import FieldOverrideRequest, Job, JobCreated
from app.services.ingestion_service import IMAGE_EXT, PDF_EXT, SHEET_EXT, UploadedFile
from app.services.pipeline_service import PipelineService, get_pipeline_service

logger = logging.getLogger(__name__)
router = APIRouter()
ALLOWED_EXT = IMAGE_EXT | PDF_EXT | SHEET_EXT
DOC_TYPES = {"BENEFIT_SCHEDULE", "CLAIMS", "CENSUS"}


@router.post("", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
async def submit_document(
    files: List[UploadFile] = File(..., description="1..N files forming ONE logical document"),
    doc_type: Optional[str] = Form(None),
    case_name: Optional[str] = Form(None),
    pipeline: PipelineService = Depends(get_pipeline_service),
):
    if not files:
        raise HTTPException(400, "At least one file is required")
    if len(files) > settings.MAX_FILES_PER_DOCUMENT:
        raise HTTPException(400, f"Too many files (max {settings.MAX_FILES_PER_DOCUMENT})")
    hint = (doc_type or "").strip().upper() or None
    if hint and hint not in DOC_TYPES:
        raise HTTPException(400, f"doc_type must be one of {sorted(DOC_TYPES)}")

    uploads: List[UploadedFile] = []
    total = 0
    for f in files:
        content = await f.read()
        total += len(content)
        uf = UploadedFile(filename=f.filename or "upload", content=content, content_type=f.content_type or "application/octet-stream")
        if uf.ext not in ALLOWED_EXT:
            raise HTTPException(400, f"Unsupported file type '{uf.ext}' ({uf.filename})")
        uploads.append(uf)
    if total > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, f"Upload exceeds {settings.MAX_UPLOAD_SIZE_MB} MB")

    job = pipeline.create_job([u.filename for u in uploads], case_name or "")
    pipeline.start(job, uploads, hint)
    return JobCreated(job_id=job.job_id)


def _job_or_404(job_id: str, pipeline: PipelineService) -> Job:
    job = pipeline.get(job_id)
    if job is None:
        raise HTTPException(404, f"Job '{job_id}' not found")
    return job


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str, pipeline: PipelineService = Depends(get_pipeline_service)):
    return _job_or_404(job_id, pipeline)


@router.patch("/{job_id}/fields", response_model=Job)
async def patch_fields(job_id: str, body: FieldOverrideRequest, pipeline: PipelineService = Depends(get_pipeline_service)):
    job = _job_or_404(job_id, pipeline)
    if job.result is None:
        raise HTTPException(409, "Job has no result yet")
    try:
        return pipeline.apply_overrides(job, body.overrides)
    except KeyError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{job_id}/export")
async def export_job(job_id: str, pipeline: PipelineService = Depends(get_pipeline_service)):
    job = _job_or_404(job_id, pipeline)
    if job.result is None:
        raise HTTPException(409, "Job has no result yet")
    data = pipeline.export.build_workbook(job)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in (job.case_name or job.job_id))[:60].strip() or job.job_id
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}_review.xlsx"'},
    )


@router.get("/{job_id}/ocr")
async def get_ocr(job_id: str, pipeline: PipelineService = Depends(get_pipeline_service)):
    _job_or_404(job_id, pipeline)
    pages = pipeline.pages.get(job_id, [])
    return {"pages": [{"page_no": p.page_no, "source_file": p.source_file, "markdown": p.markdown, "table_count": len(p.tables)} for p in pages]}

