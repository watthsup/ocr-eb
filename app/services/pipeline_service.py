"""Job store + runner: executes the LangGraph pipeline in the background and mirrors node progress onto job stages."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from app.graph.pipeline_graph import Services, build_graph
from app.models.schemas import ExtractionResult, FieldOverride, Job, PageContent
from app.services.export_service import ExportService
from app.services.ingestion_service import UploadedFile
from app.services.normalization_service import coerce

logger = logging.getLogger(__name__)

# node name -> (stage that just finished, stage that starts next)
NODE_STAGES = {
    "ingest": ("ocr", "classifying"),
    "triage": ("classifying", "extracting"),
    "merge": ("extracting", "normalizing"),
    "normalize": ("normalizing", "ready"),
}


class PipelineService:
    def __init__(self, services: Optional[Services] = None):
        self.services = services or Services()
        self.graph = build_graph(self.services)
        self.export = ExportService()
        self.jobs: Dict[str, Job] = {}
        self.pages: Dict[str, List[PageContent]] = {}

    # ---------------- job API ----------------
    def create_job(self, filenames: List[str], case_name: str = "") -> Job:
        job = Job(job_id=uuid.uuid4().hex[:12], case_name=case_name or (filenames[0] if filenames else ""), filenames=filenames)
        job.set_stage("uploaded", "done", 0)
        self.jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def start(self, job: Job, files: List[UploadedFile], doc_type_hint: Optional[str]) -> asyncio.Task:
        return asyncio.create_task(self.run_job(job, files, doc_type_hint))

    async def run_job(self, job: Job, files: List[UploadedFile], doc_type_hint: Optional[str]) -> Job:
        job.status = "processing"
        job.set_stage("ocr", "running")
        t_start = time.perf_counter()
        stage_start = {"ocr": t_start}
        try:
            state: Dict[str, Any] = {"files": files, "doc_type_hint": doc_type_hint, "timings_ms": {}, "notes": [], "shard_results": []}
            async for update in self.graph.astream(state, stream_mode="updates"):
                for node, payload in update.items():
                    if node == "ingest" and payload and payload.get("pages") is not None:
                        self.pages[job.job_id] = payload["pages"]
                    if node == "plan_shards" and payload and payload.get("extraction") is not None:
                        # census tabular path skips merge
                        self._advance(job, "extracting", "normalizing", stage_start)
                    if node in NODE_STAGES:
                        done, nxt = NODE_STAGES[node]
                        self._advance(job, done, nxt, stage_start)
                    if node == "normalize" and payload and payload.get("result") is not None:
                        job.result = payload["result"]
            if job.result is None:
                raise RuntimeError("Pipeline finished without a result")
            job.set_stage("ready", "done", (time.perf_counter() - t_start) * 1000)
            job.status = "completed"
        except Exception as exc:
            logger.exception("Job %s failed: %s", job.job_id, exc)
            job.status = "failed"
            job.error = str(exc)
            for st in job.stages:
                if st.status == "running":
                    st.status = "failed"
        return job

    @staticmethod
    def _advance(job: Job, done: str, nxt: str, stage_start: Dict[str, float]) -> None:
        now = time.perf_counter()
        current = next((s for s in job.stages if s.key == done), None)
        if current and current.status in ("running", "pending"):
            job.set_stage(done, "done", (now - stage_start.get(done, now)) * 1000)
        following = next((s for s in job.stages if s.key == nxt), None)
        if following and following.status == "pending":
            job.set_stage(nxt, "running")
            stage_start[nxt] = now

    # ---------------- direct (CLI / tests) ----------------
    async def run_direct(self, files: List[UploadedFile], doc_type_hint: Optional[str] = None, case_name: str = "") -> Job:
        job = self.create_job([f.filename for f in files], case_name)
        return await self.run_job(job, files, doc_type_hint)

    # ---------------- human review ----------------
    def apply_overrides(self, job: Job, overrides: List[FieldOverride]) -> Job:
        if job.result is None:
            raise ValueError("Job has no result")
        catalog = self.services.extraction.catalog
        result: ExtractionResult = job.result
        for ov in overrides:
            fields = result.case_fields if ov.group_key in (None, "", "Case") else next(
                (g.fields for g in result.groups if g.group_key == ov.group_key), None)
            if fields is None:
                raise KeyError(f"Unknown group '{ov.group_key}'")
            target = next((f for f in fields if f.field_code == ov.field_code), None)
            if target is None:
                raise KeyError(f"Unknown field '{ov.field_code}'")
            spec = catalog.get(ov.field_code)
            value, issues = coerce(spec, None if ov.value in (None, "") else str(ov.value)) if spec else (ov.value, [])
            target.value, target.raw_value, target.issues, target.edited = value, (str(ov.value) if ov.value not in (None, "") else None), issues, True
            target.verification = "edited"
            target.status = "not_found" if value is None else ("needs_review" if issues else "extracted")
            target.evidence = target.evidence or "edited by reviewer"
        all_fields = result.case_fields + [f for g in result.groups for f in g.fields]
        result.summary.total = len(all_fields)
        result.summary.extracted = sum(f.status == "extracted" for f in all_fields)
        result.summary.needs_review = sum(f.status == "needs_review" for f in all_fields)
        result.summary.not_found = sum(f.status == "not_found" for f in all_fields)
        return job


_pipeline: Optional[PipelineService] = None


def get_pipeline_service() -> PipelineService:
    global _pipeline
    if _pipeline is None:
        _pipeline = PipelineService()
    return _pipeline
