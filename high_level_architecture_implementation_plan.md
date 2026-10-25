# Architecture Blueprint: Agentic RFP Evaluation System

---
## 🎯 CURRENT IMPLEMENTATION STATUS
* [x] Planning & Architecture Setup
* [ ] PHASE 1: Foundation & Data Layer (ACTIVE - FOCUS HERE)**
* **[ ] PHASE 2: Ingestion & Extraction 
* [ ] PHASE 3: The AI Evaluator & Validation Gate
* [ ] PHASE 4: Scoring, Benchmarking & Ranking
* [ ] PHASE 5: Orchestration & Presentation
---

## 1. End-to-End Data Flow

To ensure the end goal is clearly met, data must flow strictly in this order:

1. **[Input]** User uploads PDFs & types Metadata (Name, Date, Experience) via Streamlit.
2. **[Initialize]** System generates a unique `RFP_RUN_ID` and fetches active criteria from SQLite.
3. **[Extract]** PyMuPDF reads the PDFs and extracts raw string text.
4. **[AI Evaluate]** Extracted Text + Criteria are sent to the LLM. 
5. **[Raw Output]** LLM returns raw JSON containing scores, justifications, and evidence.
6. **[Validate]** Pydantic intercepts the JSON. If the LLM hallucianted scores > max, Pydantic normalizes them.
7. **[Score & Rank]** Python Math Engine calculates Absolute Scores, Benchmarks, PPI, and runs the Tie-Break logic across all suppliers in the batch.
8. **[Persist]** Final, fully calculated results are saved back to SQLite `supplier_results` table.
9. **[Present]** Streamlit reads the DB and displays the Leaderboard, Detailed Scorecards, and enables JSON download.

---

## 2. Implementation Roadmap (Step-by-Step)

### 👉 PHASE 1: Foundation & Data Layer (COMPLETED)
**Goal:** Establish the data models, database schema, and seed the rules engine.
* **Tasks for Codex:**
  1. Set up a Python file (e.g., `db_setup.py` or `database.py`).
  2. Implement SQLite connection logic.
  3. Create tables: `evaluation_criteria`, `rfp_runs`, `supplier_results` (Schema below).
  4. Write a function to pre-populate `evaluation_criteria` with 5 sample criteria (Technical, Implementation, Commercial, Security, Support) ensuring weights total 1.0 (100%).
  5. Write helper CRUD functions: `get_active_criteria()`, `create_rfp_run()`.
  6. **Testing:** Write a quick script to verify tables are created and `get_active_criteria()` returns the seeded data correctly.

### PHASE 2: Ingestion & Extraction (CURRENT ACTIVE PHASE)
**Goal:** Build the entry point for documents and metadata.
* **Tasks:**
  * Build basic Streamlit forms for PDF upload and metadata input.
  * Implement PyMuPDF (or `pypdf`) text extraction function.
  * **Testing:** Upload a test PDF and print the extracted text to the console.

### PHASE 3: The AI Evaluator & Validation Gate (PENDING)
**Goal:** LLM integration and strict Pydantic validation.
* **Tasks:**
  * Create Pydantic models for expected LLM output.
  * Write the Prompt Builder and LLM API call function (forcing JSON).
  * Write the Validation function to normalize out-of-bounds scores or missing criteria.
  * **Testing:** Pass dummy text to the LLM, force it to return bad data, and ensure Pydantic catches and fixes it.

### PHASE 4: Scoring, Benchmarking & Ranking (PENDING)
**Goal:** Pure deterministic math and sorting.
* **Tasks:**
  * Implement functions for Absolute Weighted Score, Criterion Benchmark, and PPI.
  * Implement the strict 4-step Tie-Break sorting logic.
  * **Testing:** Pass a mocked, validated JSON dictionary through the math functions and assert the ranks are mathematically correct.

### PHASE 5: Orchestration & Presentation (PENDING)
**Goal:** Tie it all together in Streamlit.
* **Tasks:**
  * Write the main orchestrator loop connecting Phase 2 -> 3 -> 4.
  * Save final run to DB.
  * Build Streamlit Leaderboard and Drill-down UI.
  * **Testing:** Run a complete end-to-end evaluation with the 4 synthetic PDFs and check UI accuracy.

---

## 3. Database Schema (SQLite) (For Phase 1)

**Table 1: `evaluation_criteria`**
* `criterion_id` (INTEGER, Primary Key)
* `name` (TEXT)
* `description` (TEXT)
* `weight` (REAL) - *Note: Active weights must sum to 1.0*
* `max_score` (INTEGER)
* `is_active` (BOOLEAN)

**Table 2: `rfp_runs`**
* `rfp_run_id` (TEXT, Primary Key)
* `created_at` (TIMESTAMP)
* `status` (TEXT)

**Table 3: `supplier_results`**
* `id` (INTEGER, Primary Key, Auto-increment)
* `rfp_run_id` (TEXT, Foreign Key)
* `supplier_name` (TEXT)
* `submission_date` (DATE)
* `experience_rating` (INTEGER)
* `absolute_score` (REAL)
* `ppi` (REAL)
* `final_rank` (INTEGER)
* `result_json` (TEXT)

---

## 4. Mathematical Formulas & Tie-Break Logic (For Phase 4)

* **Absolute Weighted Score:** `Sum of ((criterion_score / max_score) * criterion_weight)`
* **Criterion Benchmark:** `MAX(valid_score)` for a criterion across all suppliers.
* **Relative Performance %:** `(supplier_score / benchmark_score) * 100` (Handle division by zero safely).
* **Peer Performance Index (PPI):** `Weighted average of Relative Performance %`

**Mandatory Tie-Break Logic (Stable Sort Order):**
1. Highest PPI (Descending)
2. Earlier Submission Date (Ascending)
3. Higher Historical Experience Rating (Descending)
4. Supplier Name (Ascending A-Z)