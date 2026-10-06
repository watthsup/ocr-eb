You are a Principal Full-Stack AI Engineer specializing in Intelligent Document Processing (IDP). Your objective is to design, implement, and benchmark an end-to-end document extraction pipeline paired with a modern React web application for a Group Insurance POC for Generali.

A competing vendor has already completed a POC claiming 100% extraction accuracy across a test suite of 7 documents. Your goal is to beat or match this benchmark with an enterprise-grade, highly resilient system that accommodates imperfect mobile photos, multi-tier nested benefits, and intuitive human review.

---

### 1. Business Context & Input Constraints

* **Domain:** Group Insurance Underwriting, Quotation, and Policy Administration.
* **Input Data Reality (IMPORTANT):**
  * The initial test files in `./example_data/` consist **entirely of mobile photos, screen captures, and photo-based scans** (`.jpg`, `.jpeg`, `.png`, and image-only `.pdf`) due to strict customer privacy restrictions preventing the export of native digital records.
  * *Artifacts to handle:* Keystone distortion, uneven lighting, shadows, camera glare, and variable resolution.
  * *Strategy:* Establish a solid, resilient system architecture first. The ingestion layer must tolerate image noise gracefully. Testing against native production documents will follow in a secure environment.
* **Document Types (3 Distinct Classes):**
  1. **Census Data:** Employee rosters, job levels, salaries, dependent counts, coverage categories.
  2. **Claims History:** Historical loss runs, incurred/paid amounts, incident/reporting dates, claim types.
  3. **Competitor Benefits (Benefit Schedules):** Plan comparison sheets, coverage limits, deductibles, co-pays.
* **Target Schema:** ~100 expected target fields across all three document categories defined by Business Analysts (BAs).
* **Hierarchical Granularity Challenge:** Competitor benefit schedules require multi-tier relational extraction:
  `Policy Level` -> `Plan Tier Level (e.g., Plan 001, Plan 002, Plan Executive)` -> `Benefit Category (IPD, OPD, Dental)` -> `Line Items (Room & Board, Surgery, Deductible, Co-insurance %)`.
* **Standardized Review Output:**
  * Refer to `./example_user_friendly_output/` for the exact business-facing review format (e.g., standardized Excel workbook/PDF summary) expected by underwriters. The system must support exporting parsed data into this target template.

---

### 2. Architecture & Technical Stack

* **Backend & API:**
  * **Runtime:** Python 3.12 with **FastAPI**.
  * **Orchestration:** LangChain (linear, deterministic DAG flow without unnecessary agent loops or shared state).
  * **OCR / Vision Engine:** **Azure AI Document Intelligence** (`prebuilt-layout` model) to handle both mobile photos and scanned PDFs with layout, reading order, and table boundary preservation.
  * **Tabular Parser:** Python (`pandas`, `openpyxl`) for handling native spreadsheets when provided.
  * **Structured Extraction:** LLM orchestration with **Pydantic v2** structured output / function calling for strict schema validation.
* **Frontend Web Application:**
  * **Framework:** **React** (Vite + TypeScript preferred).
  * **Styling & UI:** Modern, clean UI components (e.g., Tailwind CSS, Lucide icons, clean card/table layouts).
  * **API Client:** Axios or native `fetch` handling upload streams and polling/WebSocket/SSE for real-time status.

---

### 3. Backend Pipeline Workflow

#### Step 1: Ingestion & Document Preprocessing
* Ingest `.jpg`, `.png`, `.pdf`, and `.xlsx` files via API upload.
* For images and scanned PDFs, send raw payloads to Azure AI Document Intelligence (`prebuilt-layout`). Extract markdown text, structural key-value pairs, and table coordinates.
* For native Excel files, parse sheets directly using `pandas`/`openpyxl`.

#### Step 2: Single-Hop Document Classification
* Inspect page 1/early headers using a lightweight classification chain.
* Categorize the file into `CENSUS`, `CLAIMS`, or `BENEFIT_SCHEDULE`.
* Route the parsed payload to the document-specific extraction chain.

#### Step 3: Granular Hierarchical Extraction
* Extract content into strictly typed Pydantic v2 models:
  * **Census & Claims:** Flatten tabular entities into standardized record lists with normalized dates (`YYYY-MM-DD`), numeric currencies, and standardized employee IDs.
  * **Benefit Schedules:** Extract multi-tier nested models:
    ```python
    PolicyDetails -> List[PlanTier] -> List[BenefitCategory] -> List[BenefitItem]
    ```
    Disaggregate column-wise plan variations (e.g., Plan 001 vs. Plan 002) into discrete plan objects.

#### Step 4: Normalization & Template Formatting
* Normalize extracted fields to match BA business terms.
* Build an export service that compiles the extracted JSON into the business-ready format matching the templates in `example_data/example_user_friendly_output/`

---

### 4. Frontend Application Requirements (React)

Create an intuitive, executive-ready React single-page application consisting of:

#### 1. Upload & Processing Panel
* Drag-and-drop zone supporting images (`.jpg`, `.jpeg`, `.png`), `.pdf`, and `.xlsx`.
* Real-time multi-stage progress tracker:
  `Uploaded` -> `OCR & Layout Analysis (Azure)` -> `Classifying Document` -> `Extracting Fields` -> `Ready for Review`.

#### 2. Extraction Results Dashboard
Once processing completes, present a dashboard with two dedicated view modes and an export action:

* **View 1: Extracted Key-Value Inspector:**
  * Displays the target BA fields relevant to the classified document type.
  * Each row shows:
    * **Field Name** (Business label).
    * **Extracted Value** (Editable or read-only input).
    * **Status Badge** (`Extracted`, `Not Found / Empty`, or `Needs Review`).
    * **Confidence Score** indicator.
  * Search bar and quick-filter toggle (e.g., "Show only empty fields").

* **View 2: Hierarchical Matrix & Structural Inspector:**
  * **For Benefit Schedules:** Side-by-side comparison matrix displaying Plan 001 vs. Plan 002 vs. Plan 003 across benefit categories (Room & Board, Surgical, OPD limits, Co-pay).
  * **For Census & Claims:** Interactive data grid with column sorting, search, and pagination.
  * Collapsible raw JSON viewer for technical inspection.

* **Export & Review Action:**
  * Prominent **"Export Review Template"** / **"Download Business Output"** button.
  * Triggers the backend export service to generate and download the formatted review file based on the reference layout in `example_data/example_user_friendly_output/`.

---

### 5. Implementation Deliverables

Provide clean, modular, and runnable code organized as refer to another OCR project at: >>/Users/annop/Desktop/Workspace/ocr-id-card

---

### 6. Execution Rules & Quality Criteria
* Use real Azure Document Intelligence SDK calls (`azure-ai-documentintelligence`); provide a graceful fallback/mock mechanism only if credentials are unset.
* Ensure extraction prompts contain explicit instructions for untangling multi-column nested benefit tables.
* Ensure the React UI handles loading states, error boundaries, and large table rendering smoothly.