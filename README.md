# Group Insurance IDP — POC (Census · Claims · Benefit Schedule)

End-to-end Intelligent Document Processing for group-insurance underwriting: mobile photos / scanned PDFs / spreadsheets
→ **Azure Document Intelligence** (prebuilt-layout) → **triage** (classify + decide which pages to hydrate) → **sharded
structured LLM extraction** driven by a **BA-owned CSV field catalog** → normalisation & validation → human review UI →
business-ready **Excel export**.

```
[Upload 1..N files]                       app/api/v1/endpoints/documents.py
   │  images (one per page) · PDF · XLSX/CSV
   ▼
┌───────────── LangGraph DAG (app/graph/pipeline_graph.py) ───────────────────────────────┐
│ ingest ─► triage ─► plan_shards ─► extract_shard ×N (parallel, Send) ─► merge ─► normalize │
│   │          │           │                │                              │                 │
│ Azure DI   1 LLM call   deterministic   1 LLM call / shard        recall guard (audit +   │
│ + cache    on digests   (plan-column    (dynamic Pydantic enum    gap-fill) → coercion,   │
│ pandas xlsx             sections)        from CSV codes)           derived fields, status │
└──────────────────────────────────────────────────────────────────────────────────────────┘
   ▼
 Job store → GET /documents/{id} · PATCH fields · GET /export (.xlsx) · GET /ocr
```

## Why it is built this way

| Concern | Decision |
|---|---|
| **What to extract** | `example_data/expected_fields/expected_field_list.csv` is the single source of truth. Field codes, EN/TH names, the *Other keyword* synonym column, type, granularity and allowed values are loaded at runtime (`app/services/field_catalog.py`) into: the prompt context block, a `Literal[...]` enum inside the structured-output schema, type coercion rules, and the export layout. BAs add/rename fields → zero code change. Hot-swap via `POST /api/v1/catalog`. |
| **Domain knowledge** | Lives in the CSV keyword column, not in prompts. Prompts (`app/prompts/*.md`) carry only generic rules: how to read multi-column tables, continuation pages, companion limit fields, normalisation, evidence. |
| **Long documents / context rot** | Not per-page map-reduce (continuation pages have no header). A triage call tags every page (role, relevance, plan columns, `continues_page`); boilerplate pages (T&C, disease lists, dismemberment scales) are dropped; benefit tables are sharded **by plan-column section** with the shared case-level pages (plan definitions, FCL) copied into every shard; shards run in parallel and merge by plan. Claims/census rows are independent → page chunks with the header page carried over. Census tables use one column-mapping call + deterministic row parsing. |
| **Recall** | After merging, a deterministic audit compares every numeric table row against the extracted evidence; unmapped rows go to one targeted gap-fill call (or into the catch-all field derived from the CSV's "multi-row" granularity). |
| **Review** | Every catalog field appears in the result (status `extracted` / `needs_review` / `not_found`) with evidence (label as printed), page and verification status (grounded in OCR source text); edits via PATCH flow into the export. |
| **Resilience** | OCR results are cached by content hash (`.cache/ocr`) so prompt iteration never re-pays OCR; mock mode when credentials are unset; images are EXIF-rotated and downscaled before OCR. |

## Run

```bash
python3.12 -m venv .venv && source .venv/bin/activate     # 3.12+ (tested on 3.13)
pip install -r requirements.txt
cp .env.example .env                                     # fill Azure DI + OpenAI keys (or leave empty for mock mode)
uvicorn app.main:app --reload --port 8000                # API + Swagger at /docs

cd frontend && npm install && npm run dev                # React UI at http://localhost:3000 (proxies /api)
```

### Docker (Shared with `ocr-id-card` via `ocr-poc` network)
```bash
# Ensure the shared network exists
docker network create ocr-poc 2>/dev/null || true

# Production mode
docker compose up -d --build

# Live development mode (auto-reload & hot module replacement)
docker compose -f docker-compose.dev.yml up --build
```

### Benchmark harness (no server needed)
```bash
python -m scripts.run_examples example_data/benefits_document/1 --case benefit_1        # 18 photos = 1 document
python -m scripts.run_examples example_data/benefits_document/2 --case benefit_2
python -m scripts.run_examples example_data/to_be_insured_employee --case census_1
python -m pytest -q
```
Outputs land in `outputs/<case>.json` and `outputs/<case>.xlsx`.

## API
See `docs/API_CONTRACT.md`. Key endpoints: `POST /api/v1/documents` (multipart `files`, optional `doc_type`, `case_name`) →
`GET /api/v1/documents/{job_id}` (stages + result) → `PATCH …/fields` → `GET …/export` → `GET …/ocr`; `GET|POST /api/v1/catalog`.

## Layout
```
app/
  core/config.py                 settings (.env)
  clients/ocr_client.py          Azure DI + content-hash cache + mock
  clients/llm_client.py          OpenAI / Azure Foundry structured outputs (async)
  models/schemas.py              pipeline + API models; dynamic extraction model builder
  services/field_catalog.py      CSV → FieldSpec catalog → prompt block / codes / coercion metadata
  services/ingestion_service.py  images/PDF/xlsx → pages (natural sort, preprocessing)
  services/triage_service.py     page digests → classification + page roles + table structure
  services/extraction_service.py shard planning, context hydration, LLM calls, merge, recall guard, census column mapping
  services/normalization_service.py  coercion, validation, derived fields, status
  services/export_service.py     Excel review template
  services/pipeline_service.py   job store + LangGraph runner (stage progress)
  graph/pipeline_graph.py        the DAG
  prompts/*.md                   generic prompts with <<FIELD_CATALOG>> / <<OVERFLOW_FIELD>> placeholders
frontend/                        Vite + React + TS review UI
scripts/run_examples.py          benchmark harness
tests/                           unit tests (no network)
```
