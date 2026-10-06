"""Step 1 — Ingestion: files (images / PDF / spreadsheets) -> ordered list of PageContent.

* Several images uploaded together are ONE logical document (one page per image, natural filename order).
* PDFs go to Azure DI in a single call (multi-page). Images are preprocessed (EXIF rotate, downscale) and sent in parallel.
* Spreadsheets are parsed natively with pandas (one page per sheet) — no OCR needed.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from app.clients.ocr_client import AzureOCRClient, estimate_tokens
from app.core.config import settings
from app.models.schemas import PageContent

logger = logging.getLogger(__name__)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic"}
PDF_EXT = {".pdf"}
SHEET_EXT = {".xlsx", ".xlsm", ".xls", ".csv"}
MAX_MARKDOWN_ROWS = 60  # spreadsheet rows rendered into markdown for the LLM (full grid kept in `tables`)


@dataclass
class UploadedFile:
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"

    @property
    def ext(self) -> str:
        m = re.search(r"\.[A-Za-z0-9]+$", self.filename)
        return m.group(0).lower() if m else ""


def natural_key(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def prepare_image(data: bytes) -> bytes:
    """EXIF-rotate and downscale mobile photos; re-encode as JPEG when we changed anything."""
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            changed = False
            max_edge = settings.OCR_MAX_IMAGE_EDGE_PX
            if max(img.size) > max_edge:
                ratio = max_edge / max(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)))
                changed = True
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
                changed = True
            if not changed and len(data) < 4 * 1024 * 1024:
                return data
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=92, optimize=True)
            return out.getvalue()
    except Exception as exc:  # corrupted image -> let Azure decide
        logger.warning("Image preprocessing skipped: %s", exc)
        return data


def _df_to_markdown(df, sheet: str) -> str:
    cols = [str(c) for c in df.columns]
    lines = [f"## Sheet: {sheet} ({len(df)} rows x {len(cols)} cols)", "| " + " | ".join(cols) + " |",
             "|" + "---|" * len(cols)]
    for _, row in df.head(MAX_MARKDOWN_ROWS).iterrows():
        lines.append("| " + " | ".join("" if str(v) == "nan" else str(v) for v in row.tolist()) + " |")
    if len(df) > MAX_MARKDOWN_ROWS:
        lines.append(f"| ... {len(df) - MAX_MARKDOWN_ROWS} more rows omitted from this preview (full table available) ... |")
    return "\n".join(lines)


def parse_spreadsheet(file: UploadedFile) -> List[PageContent]:
    import pandas as pd

    pages: List[PageContent] = []
    if file.ext == ".csv":
        frames = {"Sheet1": pd.read_csv(io.BytesIO(file.content), header=None, dtype=str)}
    else:
        frames = pd.read_excel(io.BytesIO(file.content), sheet_name=None, header=None, dtype=str)
    for sheet, df in frames.items():
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            continue
        grid = [["" if str(v) == "nan" else str(v).strip() for v in row] for row in df.values.tolist()]
        md = _df_to_markdown(df, sheet)
        pages.append(PageContent(page_no=len(pages) + 1, source_file=f"{file.filename}#{sheet}", markdown=md,
                                 tables=[grid], token_estimate=estimate_tokens(md)))
    return pages


class IngestionService:
    def __init__(self, ocr_client: Optional[AzureOCRClient] = None):
        self.ocr_client = ocr_client or AzureOCRClient()

    async def ingest(self, files: List[UploadedFile]) -> List[PageContent]:
        files = sorted(files, key=lambda f: natural_key(f.filename))
        sem = asyncio.Semaphore(4)

        async def one(file: UploadedFile) -> List[PageContent]:
            if file.ext in SHEET_EXT:
                return await asyncio.to_thread(parse_spreadsheet, file)
            payload = file.content
            if file.ext in IMAGE_EXT or file.content_type.startswith("image/"):
                payload = await asyncio.to_thread(prepare_image, payload)
            async with sem:
                return await asyncio.to_thread(self.ocr_client.analyze, payload, file.filename)

        results = await asyncio.gather(*[one(f) for f in files])
        pages: List[PageContent] = []
        for chunk in results:
            for p in chunk:
                p.page_no = len(pages) + 1
                pages.append(p)
        logger.info("Ingested %d file(s) -> %d page(s), ≈%d tokens", len(files), len(pages), sum(p.token_estimate for p in pages))
        return pages
