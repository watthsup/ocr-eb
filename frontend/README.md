# Generali Group IDP — Frontend

React + TypeScript single-page app for the Group Insurance Intelligent Document Processing POC
(census rosters, claims history, competitor benefit schedules). Built with Vite, vanilla CSS and
`lucide-react`; talks to the FastAPI backend described in `../docs/API_CONTRACT.md`.

## Run

```bash
# 1. start the backend (repo root) on :8000
uvicorn app.main:app --reload --port 8000

# 2. start the frontend (this folder) on :3000
npm install
npm run dev
```

Vite proxies `/api/*` and `/health` to `http://localhost:8000`, so no CORS setup is needed.

Other scripts:

| command           | what it does                                  |
| ----------------- | --------------------------------------------- |
| `npm run build`   | type-check (`tsc --noEmit`) then `vite build` |
| `npm run preview` | serve the production bundle from `dist/`      |

## What's inside

```
src/
  api/client.ts          typed fetch wrappers + TS types mirroring API_CONTRACT.md
  utils/naturalSort.ts   natural filename ordering (page_1, page_2, page_10) + grid comparator
  utils/format.ts        bytes / ms / value / percent formatting, input coercion
  components/
    Header.tsx           brand, /health pill (20 s poll), catalog field-count chip
    UploadPanel.tsx      multi-file drag & drop, doc-type hint, case name, submit
    ProgressTracker.tsx  vertical stepper from job.stages + elapsed time + error banner
    ResultsDashboard.tsx summary, tabs (Fields / Matrix / Pages / JSON), export button
    SummaryBar.tsx       doc-type badge, stat tiles, classification collapsible
    FieldsView.tsx       key-value inspector: search, group filter, toggles, inline edit, paging
    EditableValue.tsx    inline editor -> PATCH /fields on blur / Enter
    MatrixView.tsx       plan / policy-year comparison matrix, census sortable grid
    PagesView.tsx        per-page classification + lazy raw OCR markdown, shards
    JsonView.tsx         pretty JSON with copy / download
    Badges.tsx           status / doc-type badges, confidence meter, page chip
    ErrorBoundary.tsx, Skeleton.tsx, EmptyState.tsx, Collapsible.tsx
  App.tsx                job submission, 1.5 s polling, layout
  index.css              Generali design tokens + component classes
```

## Behaviour notes

- Several image files are uploaded as **one logical document**; the list is shown in natural
  filename order, matching the backend's page ordering.
- Job status is polled every 1.5 s while `queued` / `processing`; after 4 consecutive poll
  failures the job is marked failed locally with the error shown in the stepper.
- Editing a value in the Fields tab sends `PATCH /api/v1/documents/{id}/fields` and replaces the
  job with the response. Empty input sends `null`; for `Number` fields a numeric string is sent
  as a number; everything else is sent as the trimmed string.
- "Export Review Template" links straight to `GET /api/v1/documents/{id}/export`.
