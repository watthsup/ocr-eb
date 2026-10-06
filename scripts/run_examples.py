"""Benchmark harness — run the pipeline on a folder (or files) without the web server.

    python -m scripts.run_examples example_data/benefits_document/1 --doc-type BENEFIT_SCHEDULE --case "Benefit 1"
    python -m scripts.run_examples example_data/to_be_insured_employee/641137_0.jpg --doc-type CENSUS

Writes outputs/<case>.json and outputs/<case>.xlsx and prints a compact review matrix.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import mimetypes
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ingestion_service import IMAGE_EXT, PDF_EXT, SHEET_EXT, UploadedFile, natural_key  # noqa: E402
from app.services.pipeline_service import PipelineService  # noqa: E402

ALLOWED = IMAGE_EXT | PDF_EXT | SHEET_EXT


def collect(paths):
    files = []
    for p in paths:
        path = Path(p)
        candidates = sorted(path.iterdir(), key=lambda x: natural_key(x.name)) if path.is_dir() else [path]
        for c in candidates:
            if c.suffix.lower() in ALLOWED and not c.name.startswith("."):
                files.append(UploadedFile(filename=c.name, content=c.read_bytes(), content_type=mimetypes.guess_type(c.name)[0] or "application/octet-stream"))
    return files


def print_matrix(result, max_rows=60):
    groups = result.groups
    print(f"\n{result.document_type} — {len(groups)} {result.group_noun}(s) · pages {result.page_count} · LLM calls {result.llm_calls}")
    print("Classification:", result.classification.reasoning)
    print("Hydrated pages:", [p.page for p in result.classification.pages if p.is_relevant], "| shards:", [(s.shard_id, s.page_nos, s.shared_page_nos) for s in result.shards])
    print("Summary:", result.summary.model_dump(), "| timings:", result.timings_ms)
    for f in result.case_fields:
        print(f"  [case] {f.field_code:<24} {str(f.value):<14} {f.status:<12} {f.evidence or ''}")
    if result.document_type == "CENSUS":
        for g in groups[:15]:
            print("  ", g.group_key, {f.field_code: f.value for f in g.fields if f.value is not None})
        return
    keys = [g.group_key for g in groups]
    print(f"\n  {'field':<26}" + "".join(f"{k[:11]:>12}" for k in keys))
    codes = [s["field_code"] for s in result.catalog if s["scope"] == "group"]
    shown = 0
    for code in codes:
        vals = [next((f for f in g.fields if f.field_code == code), None) for g in groups]
        if all(v is None or v.value is None for v in vals):
            continue
        cells = "".join(f"{(str(v.value)[:11] if v and v.value is not None else '—') + ('*' if v and v.status == 'needs_review' else ''):>12}" for v in vals)
        print(f"  {code:<26}{cells}")
        shown += 1
        if shown >= max_rows:
            break
    print("  (* = needs review)")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--doc-type", default=None, help="BENEFIT_SCHEDULE | CLAIMS | CENSUS (hint)")
    ap.add_argument("--case", default=None)
    ap.add_argument("--out", default="outputs")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    files = collect(args.paths)
    if not files:
        raise SystemExit("No supported files found")
    case = args.case or Path(args.paths[0]).stem or "case"
    pipeline = PipelineService()
    job = await pipeline.run_direct(files, args.doc_type, case_name=case)
    os.makedirs(args.out, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in case)
    with open(os.path.join(args.out, f"{safe}.json"), "w", encoding="utf-8") as fh:
        fh.write(job.model_dump_json(indent=2))
    if job.status != "completed":
        print("FAILED:", job.error)
        raise SystemExit(1)
    with open(os.path.join(args.out, f"{safe}.xlsx"), "wb") as fh:
        fh.write(pipeline.export.build_workbook(job))
    print_matrix(job.result)
    print(f"\nSaved {args.out}/{safe}.json and {args.out}/{safe}.xlsx")


if __name__ == "__main__":
    asyncio.run(main())
