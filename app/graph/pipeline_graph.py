"""LangGraph DAG: ingest -> triage -> plan_shards -> [extract_shard x N in parallel] -> merge -> normalize.

Deterministic, no agent loops. The only dynamic part is the fan-out (`Send`) whose width is decided
by the shard planner from the triage result. Nodes are thin wrappers around the services so they stay
unit-testable without the graph.
"""

from __future__ import annotations

import logging
import operator
import time
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.models.schemas import ExtractionOut, ExtractionResult, PageContent, ShardSpec, TriageResult
from app.services.extraction_service import ExtractionService
from app.services.ingestion_service import IngestionService, UploadedFile
from app.services.normalization_service import NormalizationService
from app.services.triage_service import TriageService

logger = logging.getLogger(__name__)


def _merge_dicts(a: Dict[str, float], b: Dict[str, float]) -> Dict[str, float]:
    return {**(a or {}), **(b or {})}


class PipelineState(TypedDict, total=False):
    files: List[UploadedFile]
    doc_type_hint: Optional[str]
    pages: List[PageContent]
    triage: TriageResult
    doc_type: str
    shards: List[ShardSpec]
    shard_results: Annotated[List[ExtractionOut], operator.add]
    extraction: ExtractionOut
    result: ExtractionResult
    timings_ms: Annotated[Dict[str, float], _merge_dicts]
    notes: Annotated[List[str], operator.add]


class ShardState(TypedDict):
    doc_type: str
    shard: ShardSpec
    pages: List[PageContent]
    triage: TriageResult


class Services:
    def __init__(self, ingestion: Optional[IngestionService] = None, triage: Optional[TriageService] = None,
                 extraction: Optional[ExtractionService] = None, normalization: Optional[NormalizationService] = None):
        self.ingestion = ingestion or IngestionService()
        self.triage = triage or TriageService()
        self.extraction = extraction or ExtractionService(llm=self.triage.llm)
        self.normalization = normalization or NormalizationService(catalog=self.extraction.catalog)

    @property
    def llm(self):
        return self.triage.llm


def build_graph(services: Services):
    async def ingest(state: PipelineState) -> Dict[str, Any]:
        t0 = time.perf_counter()
        pages = await services.ingestion.ingest(state["files"])
        return {"pages": pages, "timings_ms": {"ocr": (time.perf_counter() - t0) * 1000}}

    async def triage(state: PipelineState) -> Dict[str, Any]:
        t0 = time.perf_counter()
        tri = await services.triage.triage(state["pages"], state.get("doc_type_hint"))
        return {"triage": tri, "doc_type": tri.document_type, "timings_ms": {"classifying": (time.perf_counter() - t0) * 1000}}

    async def plan_shards(state: PipelineState) -> Dict[str, Any]:
        t0 = time.perf_counter()
        doc_type, pages, tri = state["doc_type"], state["pages"], state["triage"]
        from app.core.config import settings

        if doc_type == "CENSUS" and settings.CENSUS_TABULAR_MODE and services.llm.enabled:
            try:
                tabular = await services.extraction.extract_census_tabular(pages, tri)
            except Exception as exc:  # fall back to generic LLM extraction
                logger.warning("Census tabular mode failed: %s", exc)
                tabular = None
            if tabular is not None:
                shard = ShardSpec(shard_id="S1", label="census column-mapping (deterministic rows)",
                                  page_nos=[pt.page for pt in tri.pages if pt.is_relevant])
                return {"shards": [shard], "extraction": tabular, "timings_ms": {"extracting": (time.perf_counter() - t0) * 1000}}
        shards = services.extraction.plan_shards(doc_type, pages, tri)
        logger.info("Planned %d shard(s): %s", len(shards), [(s.shard_id, s.page_nos, s.shared_page_nos) for s in shards])
        return {"shards": shards, "timings_ms": {"planning": (time.perf_counter() - t0) * 1000}}

    def fan_out(state: PipelineState):
        if state.get("extraction") is not None:
            return "normalize"
        if not services.llm.enabled:
            return "merge"
        return [Send("extract_shard", ShardState(doc_type=state["doc_type"], shard=s, pages=state["pages"], triage=state["triage"]))
                for s in state["shards"]]

    async def extract_shard(state: ShardState) -> Dict[str, Any]:
        t0 = time.perf_counter()
        out = await services.extraction.extract_shard(state["doc_type"], state["shard"], state["pages"], state["triage"])
        return {"shard_results": [out], "timings_ms": {f"extract_{state['shard'].shard_id}": (time.perf_counter() - t0) * 1000}}

    async def merge(state: PipelineState) -> Dict[str, Any]:
        results = state.get("shard_results") or []
        notes: List[str] = []
        if not results:
            notes.append("LLM not configured — no fields extracted (mock mode).")
        merged = services.extraction.merge(results) if results else ExtractionOut(case_fields=[], groups=[], notes=None)
        extract_ms = sum(v for k, v in (state.get("timings_ms") or {}).items() if k.startswith("extract_"))
        return {"extraction": merged, "notes": notes, "timings_ms": {"extracting": extract_ms}}

    async def normalize(state: PipelineState) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timings = dict(state.get("timings_ms") or {})
        result = services.normalization.normalize(
            state["doc_type"], state["extraction"], state["pages"], state["triage"], state.get("shards", []), timings, services.llm.calls
        )
        result.notes = (state.get("notes") or []) + result.notes
        result.timings_ms["normalizing"] = round((time.perf_counter() - t0) * 1000, 1)
        result.timings_ms["total"] = round(sum(v for k, v in result.timings_ms.items() if k in ("ocr", "classifying", "planning", "extracting", "normalizing")), 1)
        return {"result": result}

    g = StateGraph(PipelineState)
    g.add_node("ingest", ingest)
    g.add_node("triage", triage)
    g.add_node("plan_shards", plan_shards)
    g.add_node("extract_shard", extract_shard)
    g.add_node("merge", merge)
    g.add_node("normalize", normalize)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "triage")
    g.add_edge("triage", "plan_shards")
    g.add_conditional_edges("plan_shards", fan_out, ["extract_shard", "merge", "normalize"])
    g.add_edge("extract_shard", "merge")
    g.add_edge("merge", "normalize")
    g.add_edge("normalize", END)
    return g.compile()
