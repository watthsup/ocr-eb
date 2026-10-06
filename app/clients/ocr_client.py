"""Azure Document Intelligence (prebuilt-layout) client with content-hash cache and mock fallback."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import List, Optional

from app.core.config import settings
from app.models.schemas import PageContent

logger = logging.getLogger(__name__)

THAI_RE = re.compile(r"[฀-๿]")


def estimate_tokens(text: str) -> int:
    """Cheap tokenizer-free estimate calibrated on o200k: Thai ≈ 1 token / 1.4 chars; Latin/markup ≈ 1 / 3.5 chars."""
    thai = len(THAI_RE.findall(text))
    other = len(text) - thai
    return int(thai / 1.4 + other / 3.5) + 1


class AzureOCRClient:
    """Wraps `azure-ai-documentintelligence`. One call per file (PDFs are multi-page)."""

    def __init__(self, endpoint: Optional[str] = None, key: Optional[str] = None, model_id: Optional[str] = None):
        self.endpoint = endpoint or settings.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
        self.key = key or settings.AZURE_DOCUMENT_INTELLIGENCE_KEY
        self.model_id = model_id or settings.AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID
        self._client = None
        self.cache_dir = settings.OCR_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return settings.ocr_enabled

    def _get_client(self):
        if self._client is None:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential

            self._client = DocumentIntelligenceClient(endpoint=self.endpoint, credential=AzureKeyCredential(self.key))
        return self._client

    # ---------------- cache ----------------
    def _cache_path(self, payload: bytes) -> str:
        digest = hashlib.sha256(payload).hexdigest()[:24]
        return os.path.join(self.cache_dir, f"{self.model_id}-{digest}.json")

    # ---------------- main ----------------
    def analyze(self, payload: bytes, source_file: str) -> List[PageContent]:
        """Returns one PageContent per physical page with markdown + 2-D tables."""
        cache_path = self._cache_path(payload)
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            logger.info("OCR cache hit for %s (%d pages)", source_file, len(raw))
            return [PageContent(**p, source_file=source_file) for p in raw]

        if not self.enabled:
            logger.warning("Azure Document Intelligence not configured — returning MOCK OCR for %s", source_file)
            md = f"[MOCK OCR] Azure Document Intelligence credentials are not set. File: {source_file}"
            return [PageContent(page_no=1, source_file=source_file, markdown=md, token_estimate=estimate_tokens(md))]

        from azure.ai.documentintelligence.models import AnalyzeOutputOption, DocumentContentFormat  # noqa: F401

        client = self._get_client()
        logger.info("Azure DI analyze (%s) for %s (%.1f KB)", self.model_id, source_file, len(payload) / 1024)
        poller = client.begin_analyze_document(
            model_id=self.model_id,
            body=payload,
            content_type="application/octet-stream",
            output_content_format=DocumentContentFormat.MARKDOWN,
        )
        result = poller.result()
        pages = self._to_pages(result, source_file)
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump([p.model_dump(exclude={"source_file"}) for p in pages], fh, ensure_ascii=False)
        return pages

    @staticmethod
    def _to_pages(result, source_file: str) -> List[PageContent]:
        content: str = result.content or ""
        pages: List[PageContent] = []
        # Slice markdown content by page spans
        for p in result.pages or []:
            text_parts = []
            for span in p.spans or []:
                text_parts.append(content[span.offset: span.offset + span.length])
            md = "\n".join(text_parts).strip()
            pages.append(PageContent(page_no=p.page_number, source_file=source_file, markdown=md, token_estimate=estimate_tokens(md)))
        if not pages:
            pages.append(PageContent(page_no=1, source_file=source_file, markdown=content, token_estimate=estimate_tokens(content)))

        # Attach 2-D table grids to their page
        by_page = {p.page_no: p for p in pages}
        for table in result.tables or []:
            page_no = 1
            if table.bounding_regions:
                page_no = table.bounding_regions[0].page_number
            grid = [["" for _ in range(table.column_count)] for _ in range(table.row_count)]
            for cell in table.cells or []:
                if cell.row_index < table.row_count and cell.column_index < table.column_count:
                    grid[cell.row_index][cell.column_index] = (cell.content or "").replace("\n", " ").strip()
            target = by_page.get(page_no) or pages[0]
            target.tables.append(grid)
        return pages
