# Agentic RFP Evaluation System

An end-to-end Streamlit application for evaluating supplier RFP submissions using a hybrid **agentic + deterministic** architecture:
- **LLM layer** performs qualitative criterion-level evaluation (score, evidence, justification).
- **Python layer** performs strict validation, math scoring, benchmarking, tie-break ranking, and persistence.

---

## 1) Features

- Upload supplier PDFs and capture metadata (`supplier_name`, `submission_date`, `experience_rating`).
- Extract text from PDF documents using `pypdf`.
- Run AI evaluation with provider/model selection:
  - OpenAI
  - Google Gemini (`google-genai` SDK)
  - Local Ollama models
- Enforce strict Pydantic validation/normalization gate before scoring.
- Compute deterministic Phase 4 metrics:
  - Absolute Weighted Score
  - Criterion Benchmarks
  - Criterion Gap
  - Relative Performance %
  - Peer Performance Index (PPI)
- Rank suppliers using mandatory stable tie-break order.
- Persist final run results in SQLite (`supplier_results.result_json` stores full output).
- View historical runs using sidebar **Past Runs** loader.
- Download run results as JSON directly from Streamlit.

---

## 2) Project Structure

```text
.
├── database.py                     # SQLite schema + CRUD
├── ingestion.py                    # PDF text extraction
├── phase3_evaluation.py            # Prompting, provider calls, Pydantic gate
├── phase4_scoring.py               # Deterministic scoring and ranking
├── streamlit_app.py                # Main UI + orchestration + past-runs viewer
├── requirements.txt                # Python dependencies
├── verify_phase1.py                # Phase 1 verification
├── verify_phase3.py                # Phase 3 gate verification
├── verify_phase4.py                # Phase 4 math/ranking verification
├── verify_phase5.py                # Phase 5 persistence verification
└── verify_past_runs_viewer.py      # Past-run loading verification
```

---

## 3) Windows Setup (VS Code / PyCharm)

### Prerequisites
- Python 3.10+ recommended
- `pip` installed
- (Optional) Ollama installed locally for offline/local inference

### Steps

1. Open terminal in project root.
2. Create virtual environment:

```powershell
python -m venv venv
```

3. Activate virtual environment (Windows):

```powershell
venv\Scripts\activate
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

5. Run Streamlit app:

```powershell
streamlit run streamlit_app.py
```

If `streamlit` is not found:

```powershell
python -m streamlit run streamlit_app.py
```

---

## 4) Provider Setup for Evaluation Gate

In the UI, choose a provider and model before clicking **Run Evaluation**.

### A) OpenAI
- Provider: `openai`
- Model examples: `gpt-4o-mini`, `gpt-4.1-mini`
- API key is entered directly in the UI password field (**mandatory**).

### B) Google Gemini (`google-genai`)
- Provider: `gemini`
- Model examples: `gemini-2.0-flash`, `gemini-1.5-pro`
- API key is entered directly in the UI password field (**mandatory**).
- Integration implemented via `google.genai.Client(...).models.generate_content(...)` with JSON response MIME type.

### C) Ollama (local)
- Provider: `ollama`
- Model examples: `llama3.1`, `mistral`, `qwen2.5`
- No API key required.
- Base URL field is available in UI (default: `http://localhost:11434`).
- Integration uses Ollama HTTP API endpoint: `POST /api/generate`.

---

## 5) Agentic Architecture Breakdown

This system intentionally separates **LLM reasoning** from **deterministic decisioning**.

### 5.1 LLM Reasoning Layer (Non-deterministic)

**Owned by:** `phase3_evaluation.py`

Responsibilities:
- Build criterion-aware prompt from extracted supplier text + active criteria.
- Call selected LLM provider (OpenAI, Gemini, or Ollama).
- Request structured JSON containing:
  - `criterion_id`
  - `score`
  - `justification`
  - `evidence`

### 5.2 Validation Gate (Deterministic Safety Layer)

**Owned by:** Pydantic models + normalization logic in `phase3_evaluation.py`

Responsibilities:
- Validate schema strictly (required fields, types, non-empty strings).
- Drop malformed/hallucinated criterion rows.
- Clip out-of-range scores into valid bounds `[0, max_score]`.
- Backfill missing criteria with safe defaults.
- Output normalized evaluation JSON consumed by Phase 4.

### 5.3 Deterministic Scoring & Ranking Layer

**Owned by:** `phase4_scoring.py`

Responsibilities:
- Compute scores using fixed formulas only.
- Compute cohort benchmarks.
- Compute criterion gap and relative performance.
- Compute PPI.
- Apply mandatory stable tie-break ordering.

### 5.4 Persistence + Presentation Layer

**Owned by:** `database.py` + `streamlit_app.py`

Responsibilities:
- Save each supplier’s final ranked record to SQLite.
- Store complete result payload in `supplier_results.result_json`.
- Render current run leaderboard and detailed scorecards.
- Load historical runs from DB and reconstruct dashboard views.

---

## 6) Mathematical Formulas

Let each criterion be indexed by \(i\), with:
- \(s_i\): supplier score for criterion \(i\)
- \(m_i\): max score for criterion \(i\)
- \(w_i\): criterion weight for criterion \(i\)
- \(b_i\): benchmark score for criterion \(i\) across all suppliers

### 6.1 Absolute Weighted Score

\[
\text{AbsoluteWeightedScore} = \sum_i \left(\frac{s_i}{m_i} \times w_i\right)
\]

### 6.2 Criterion Benchmark

\[
b_i = \max(\text{valid supplier scores for criterion } i)
\]

### 6.3 Criterion Gap

\[
\text{CriterionGap}_i = b_i - s_i
\]

### 6.4 Relative Performance %

\[
\text{RelativePerformance}_i =
\begin{cases}
\left(\frac{s_i}{b_i}\right) \times 100, & b_i > 0 \\
0, & b_i = 0
\end{cases}
\]

### 6.5 Peer Performance Index (PPI)

\[
\text{PPI} = \sum_i \left(\text{RelativePerformance}_i \times w_i\right)
\]

### 6.6 Mandatory Tie-Break Order (Stable)

Sort by:
1. **PPI** (descending)
2. **Submission Date** (ascending; earlier is better)
3. **Experience Rating** (descending)
4. **Supplier Name** (ascending A–Z)

Final rank is assigned sequentially after sorting.

---

## 7) End-to-End Flow

1. User uploads PDFs + metadata in Streamlit.
2. PDF text extraction runs in-memory.
3. LLM evaluates criteria and returns JSON.
4. Pydantic gate validates/normalizes JSON.
5. Deterministic math engine scores and ranks suppliers.
6. Final outputs persist in SQLite (`supplier_results`, including full `result_json`).
7. UI renders final leaderboard + detailed scorecards.
8. User can download run JSON and later load runs from **Past Runs** viewer.

---

## 8) Screenshots

- UI Form (upload + metadata + provider/model/API key):
  - `[Insert Screenshot Here]`

- Detailed Scorecards (absolute score, PPI, criterion gaps, evidence/justification):
  - `[Insert Screenshot Here]`

- Past Runs Viewer (sidebar run selector + historical leaderboard/scorecards):
  - `[Insert Screenshot Here]`

---

## 9) Verification Scripts

Run these from project root (with venv activated):

```powershell
python verify_phase1.py
python verify_phase3.py
python verify_phase4.py
python verify_phase5.py
python verify_past_runs_viewer.py
```

---

## 10) Notes & Troubleshooting

- For OpenAI/Gemini in UI, API key input is mandatory.
- For Ollama, ensure local server is running and model is available (`ollama pull <model>`).
- `result_json` stores complete saved outputs used for historical run reconstruction.
- If dependency errors occur, re-check activated venv and re-run:

```powershell
pip install -r requirements.txt
```

