# Discharge Summary Agent

A robust, multi-step agentic AI system for generating structured, clinically safe discharge summaries from patient PDF records. Powered by **Google Gemini (`gemini-2.5-flash`)**.

---

## 🛠️ Tech Stack

- **Core Language**: Python 3.10+
- **Agent Framework & LLM**: Google Gemini API via `google-generativeai` (utilizing `gemini-2.5-flash` for agent planning and medical extraction)
- **Web Dashboard**: Flask (Python backend) with high-fidelity custom HTML5/CSS3 dark-themed front-end (glassmorphism UI, real-time agent execution tracking)
- **OCR & Document Parsing**: Tesseract OCR (`pytesseract`), Poppler (`pdf2image`), `pdfplumber`, and `PyPDF2`
- **Safety & Robustness**: Pydantic (schema/data structure validation) and Tenacity (resilient LLM API call retries)

---

## 🖥️ Dashboard UI Screenshots

Here are some screenshots of the interactive web dashboard:

### 1. Document Analysis & Execution Trace
Shows the real-time planner running through its multi-step agentic loop and reporting reasoning logs.
![Document Analysis](screenshots/dashboard_analysis.png)

### 2. Main Dashboard & Patient Info
Visual overview of demographics, extracted diagnoses, and metrics including steps taken, conflicts found, and procedures completed.
![Main Dashboard](screenshots/dashboard_main.png)

### 3. Key Investigations
Extracts, structures, and maps lab results and vital statistics into clear tabular formats.
![Key Investigations](screenshots/dashboard_investigations.png)

### 4. Medications, Procedures & Discharge Info
Captures all prescriptions, route, frequency, and duration alongside critical follow-up plans.
![Medications and Procedures](screenshots/dashboard_meds_procedures.png)

### 5. Clinical Safety & Conflicts Panel
Highlights cross-document inconsistencies (LAMA status, diagnosis mismatches) and medication reconciliation flags for direct clinician review.
![Clinical Safety](screenshots/dashboard_conflicts.png)

---


## 🚀 How to Run

### 1. Install System Dependencies
Install OCR and PDF rendering tools:
```bash
sudo apt update && sudo apt install -y tesseract-ocr poppler-utils
```

### 2. Install Python Packages
```bash
pip install -r requirements.txt
```

### 3. Configure the Environment
Create a `.env` file at the root of the project:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

### 4. Run the Web Dashboard
```bash
python3 app.py
```
Open **`http://localhost:5000`** in your browser.

### 5. Run via CLI
```bash
python3 main.py --patient-folder patients/patient_2 --max-steps 25
```

---

## 🏥 Agent Loop Design

The agent uses a state-driven planning loop rather than a hardcoded pipeline. After executing each step, the planner (`agent/planner.py`) evaluates the current state and decides which tool to run next.

```mermaid
graph TD
    A[Start: Patient PDF] --> B[1. read_pdfs]
    B --> C[2. Extract demographics, diagnoses, meds, labs, procedures]
    C --> D[3. detect_conflicts]
    D --> E[4. check_drug_interactions]
    E --> F[5. reconcile_medications]
    F --> G[6. build_summary]
    G --> H[End: HTML Report & step_trace.json]
```

---

## 🛡️ Clinical Safety & Guardrails

### 1. No-Fabrication Guardrail
- **Refusal to Guess**: System instructions explicitly restrict the model from inventing any clinical fact. If information is not found, the model must return `null` or `[PENDING]`.
- **Clinician Review Mapping**: Any unextracted field is rendered as `—` (Not Documented) and flagged visually on the dashboard to force manual verification.

### 2. Failure Handling
- **Tenacious Retries**: All LLM calls are wrapped with exponential backoff retries (`tenacity`) to handle network timeouts.
- **Quota Fail-Safe**: If the API key hits quota limits (429 errors), the loop terminates early and alerts the user rather than silently producing incomplete reports.

### 3. Conflict & Inconsistency Handling
- **Cross-Document Auditing**: `tools/conflict_detector.py` checks for mismatched discharge dates, conflicting diagnoses, and discharge status (e.g. standard discharge vs. Left Against Medical Advice). Conflicts are escalated directly to the reviewer.

---

## 🔮 Limitations & Future Work

- **Rate Limits**: The Gemini free tier is subject to strict limits (20 requests/day). Upgrading to a pay-as-you-go key removes this bottleneck.
- **Context Chunking**: For exceptionally long hospital stays (+100 pages), pre-filtering pages using keyword matches (e.g., searching for "Discharge", "Medication List", "Course") will optimize token usage.
