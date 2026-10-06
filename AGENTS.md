# Technical Specification — Group Insurance IDP (POC)

Read in this order:
1. `README.md` — what it is, how to run, layout.
2. `docs/DESIGN_NOTES.md` — the reasoning: CSV-driven schema, prompt structure, why triage + plan-section sharding instead of per-page map-reduce, recall guard, row grounding.
3. `docs/API_CONTRACT.md` — the JSON contract the React UI is built against.

## Invariants to keep
- **Domain knowledge lives in `example_data/expected_fields/expected_field_list.csv`** (column *Other keyword*), never in prompts. Fix an extraction miss by adding a keyword to the CSV row, not by editing `app/prompts/*.md`.
- Prompts contain only generic, structural rules and two placeholders: `<<FIELD_CATALOG>>` and `<<OVERFLOW_FIELD>>`.
- The model never computes aggregates; derived fields (`CEN_NO`, `CEN_AGE`, `CLM_PERIOD_NO`, `PLAN_NO`, total checks) are done in `normalization_service._derive`.
- The model picks the table row (`source_row` tag); code copies the printed cells (`extraction_service.ground_rows`).
- **LLMs must never score their own confidence.** All status determinations (`extracted` vs `needs_review`) and merge decisions are driven strictly by deterministic code rules: type coercion errors, shard conflicts, cross-plan outliers, sum mismatches, and OCR source-text verification.
- Every catalog field appears in the result exactly once per group / once per case, with a status — the UI and the export rely on that.
- OCR is cached by content hash in `.cache/ocr`; delete a file there to force a re-analysis.

## Pipeline (LangGraph, `app/graph/pipeline_graph.py`)
`ingest → triage → plan_shards → [extract_shard ×N] → merge → normalize`

## Tests
`python -m pytest -q` — unit tests need no network. `python -m scripts.run_examples <folder>` runs the real pipeline (needs `.env`).
