import os
import uuid
import threading
from flask import Flask, request, jsonify, send_file
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# In-memory job store
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def load_existing_jobs():
    import glob
    if not os.path.exists(OUTPUT_DIR):
        return
    reports = glob.glob(os.path.join(OUTPUT_DIR, "*_report.html"))
    for r_path in reports:
        filename = os.path.basename(r_path)
        job_id = filename.replace("_report.html", "")
        t_path = os.path.join(OUTPUT_DIR, f"{job_id}_trace.json")
        if os.path.exists(t_path):
            with jobs_lock:
                jobs[job_id] = {
                    "status": "complete",
                    "patient_id": job_id,
                    "filename": f"{job_id}.pdf",
                    "report_path": r_path,
                    "patient_name": job_id
                }


load_existing_jobs()


def run_agent_job(job_id: str, pdf_path: str, patient_id: str):
    """Run the discharge agent in a background thread."""
    try:
        with jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["step"] = "Reading PDF…"

        from agent.loop import DischargeAgent
        from output.html_report import generate_html_report

        agent = DischargeAgent(
            patient_folder=os.path.dirname(pdf_path),
            patient_id=patient_id,
            max_steps=25,
        )
        with jobs_lock:
            jobs[job_id]["state"] = agent.state
        state = agent.run()

        report_path = f"{OUTPUT_DIR}/{job_id}_report.html"
        generate_html_report(state, report_path)
        agent.tracer.export_trace(f"{OUTPUT_DIR}/{job_id}_trace.json")

        with jobs_lock:
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["report_path"] = report_path
            jobs[job_id]["steps"] = state.current_step
            jobs[job_id]["conflicts"] = len(state.conflicts_detected or [])
            jobs[job_id]["patient_name"] = (state.demographics or {}).get("patient_name") or patient_id

    except Exception as e:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)


@app.route("/")
def index():
    return UPLOAD_PAGE


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["pdf"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files accepted"}), 400

    job_id = str(uuid.uuid4())[:8]
    patient_id = os.path.splitext(f.filename)[0].replace(" ", "_")
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    pdf_path = os.path.join(job_dir, f.filename)
    f.save(pdf_path)

    with jobs_lock:
        jobs[job_id] = {"status": "queued", "patient_id": patient_id, "filename": f.filename}
    t = threading.Thread(target=run_agent_job, args=(job_id, pdf_path, patient_id), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


def _get_stage_label(tool: str) -> str:
    labels = {
        "read_pdfs":             "Reading PDF",
        "extract_demographics":  "Extracting demographics",
        "extract_diagnoses":     "Extracting diagnoses",
        "extract_medications":   "Extracting medications",
        "extract_labs":          "Extracting lab results",
        "extract_procedures":    "Extracting procedures",
        "extract_discharge_info":"Extracting discharge info",
        "detect_conflicts":      "Detecting conflicts",
        "check_drug_interactions":"Checking drug interactions",
        "build_summary":         "Building summary",
    }
    return labels.get(tool, "Processing...")


@app.route("/status/<job_id>")
def status(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        state = job.get("state")
        if state:
            job["current_step"] = state.current_step
            if state.iteration_history:
                job["last_reasoning"] = state.iteration_history[-1]["reasoning"]
                job["last_tool"] = state.iteration_history[-1]["tool_chosen"]
            else:
                job["last_reasoning"] = "Starting clinical analysis..."
                job["last_tool"] = "read_pdfs"

        return jsonify({
            "status": job.get("status"),
            "patient_id": job.get("patient_id"),
            "filename": job.get("filename"),
            "current_step": job.get("current_step", 0),
            "last_reasoning": job.get("last_reasoning", "Initializing agent planner..."),
            "last_tool": job.get("last_tool", ""),
            "error": job.get("error"),
            "total_steps": 25,
            "progress_pct": round((job.get("current_step", 0) / 25) * 100),
            "stage_label": _get_stage_label(job.get("last_tool", ""))
        })


@app.route("/report/<job_id>")
def report(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "complete":
            return "Report not ready", 404
        report_path = job["report_path"]
    return send_file(report_path)


UPLOAD_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Discharge Summary Agent</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#080b14;--surface:#0f1322;--surface2:#161b2e;--border:#1e2540;
  --text:#e8eaf6;--muted:#6b7299;--primary:#6c63ff;--primary-light:#a78bfa;
  --success:#00d4a8;--warning:#ffb347;--danger:#ff5c7a;
  --font:'Inter',sans-serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;display:flex;flex-direction:column;align-items:center}

/* Nav */
nav{width:100%;padding:18px 48px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--border);background:rgba(8,11,20,.8);backdrop-filter:blur(12px);position:sticky;top:0;z-index:10}
.logo{font-size:1.05rem;font-weight:700;background:linear-gradient(135deg,var(--primary-light),#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.nav-tag{font-size:.75rem;color:var(--muted);background:var(--surface2);border:1px solid var(--border);padding:4px 12px;border-radius:20px}

/* Hero */
.hero{text-align:center;padding:80px 24px 48px;max-width:680px}
.hero h1{font-size:3rem;font-weight:800;line-height:1.15;background:linear-gradient(135deg,#e8eaf6 30%,var(--primary-light) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:18px}
.hero p{font-size:1.1rem;color:var(--muted);line-height:1.7;max-width:520px;margin:0 auto 40px}
.chips{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-bottom:48px}
.chip{background:var(--surface2);border:1px solid var(--border);border-radius:20px;padding:6px 16px;font-size:.78rem;color:var(--muted)}
.chip span{color:var(--primary-light);margin-right:5px}

/* Upload zone */
.upload-wrap{width:100%;max-width:600px;padding:0 24px 80px}
.drop-zone{border:2px dashed var(--border);border-radius:20px;padding:56px 32px;text-align:center;cursor:pointer;transition:all .25s;background:var(--surface);position:relative}
.drop-zone:hover,.drop-zone.drag-over{border-color:var(--primary);background:rgba(108,99,255,.07)}
.drop-icon{font-size:3rem;margin-bottom:16px}
.drop-zone h3{font-size:1.1rem;font-weight:600;margin-bottom:8px}
.drop-zone p{font-size:.85rem;color:var(--muted)}
.drop-zone input[type=file]{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%}
.file-badge{display:none;align-items:center;gap:10px;background:rgba(108,99,255,.12);border:1px solid rgba(108,99,255,.3);border-radius:10px;padding:12px 16px;margin-top:20px}
.file-badge .name{font-size:.85rem;font-weight:500;flex:1;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.btn-analyze{width:100%;margin-top:16px;padding:16px;border-radius:14px;border:none;background:linear-gradient(135deg,var(--primary),#a78bfa);color:#fff;font-size:1rem;font-weight:700;cursor:pointer;font-family:var(--font);transition:all .2s;display:none}
.btn-analyze:hover{transform:translateY(-2px);box-shadow:0 8px 32px rgba(108,99,255,.4)}

/* Processing */
.processing{display:none;text-align:center;padding:48px 0}
.spinner{width:56px;height:56px;border:3px solid var(--border);border-top-color:var(--primary);border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 24px}
@keyframes spin{to{transform:rotate(360deg)}}
.processing h3{font-size:1.2rem;font-weight:600;margin-bottom:8px}
.processing p{color:var(--muted);font-size:.88rem}
.step-list{margin-top:24px;text-align:left;max-width:320px;margin-left:auto;margin-right:auto}
.step-item{display:flex;align-items:center;gap:10px;padding:8px 0;font-size:.83rem;color:var(--muted);border-bottom:1px solid var(--border)}
.step-item.done{color:var(--success)}
.step-item .dot{width:8px;height:8px;border-radius:50%;background:var(--border);flex-shrink:0}
.step-item.done .dot{background:var(--success)}
.step-item.active .dot{background:var(--primary);box-shadow:0 0 8px var(--primary);animation:pulse 1s infinite}
.step-item.active{color:var(--text)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}

/* Footer */
footer{border-top:1px solid var(--border);width:100%;text-align:center;padding:24px;color:var(--muted);font-size:.78rem}
</style>
</head>
<body>

<nav>
  <div class="logo">🏥 Discharge Summary Agent</div>
</nav>

<div class="hero">
  <h1>AI-Powered Discharge Summary</h1>
  <p>Upload a patient medical PDF and get a structured clinical discharge summary with conflict detection, drug interaction checks, and medication reconciliation.</p>
  <div class="chips">
    <div class="chip"><span>⚡</span>Gemini LLM Extraction</div>
    <div class="chip"><span>⚠️</span>Conflict Detection</div>
    <div class="chip"><span>💊</span>Drug Interactions</div>
    <div class="chip"><span>🔁</span>Med Reconciliation</div>
    <div class="chip"><span>📋</span>Structured Report</div>
  </div>
</div>

<div class="upload-wrap">

  <!-- Upload state -->
  <div id="upload-state">
    <div class="drop-zone" id="dropZone">
      <input type="file" id="fileInput" accept=".pdf">
      <div class="drop-icon">📄</div>
      <h3>Drop your medical PDF here</h3>
      <p>or click to browse &nbsp;·&nbsp; Max 50 MB</p>
    </div>
    <div class="file-badge" id="fileBadge">
      <span>📎</span>
      <span class="name" id="fileName"></span>
    </div>
    <button class="btn-analyze" id="btnAnalyze" onclick="analyze()">
      ⚡ Generate Discharge Summary
    </button>
  </div>

  <!-- Processing state -->
  <div class="processing" id="processingState">
    <div class="spinner"></div>
    <h3>Analysing your document…</h3>
    <p>The agent is extracting clinical data using Google Gemini AI</p>

    <!-- Real-time Terminal Logger -->
    <div style="margin-top:20px; background:#070a13; padding:15px; border:1px solid #1c223c; border-radius:10px; text-align:left; font-family:monospace; font-size:.8rem; min-height:80px; display:flex; flex-direction:column; justify-content:center;">
      <div style="color:var(--primary-light); font-weight:bold; margin-bottom:5px;">&gt; Agent Reasoning:</div>
      <div id="statusText" style="color:#a5b4fc; line-height:1.4;">Initializing agent planner...</div>
    </div>

    <div class="step-list" style="margin-top:28px;">
      <div class="step-item" id="s1"><div class="dot"></div>Reading PDF pages</div>
      <div class="step-item" id="s2"><div class="dot"></div>Extracting demographics</div>
      <div class="step-item" id="s3"><div class="dot"></div>Extracting diagnoses</div>
      <div class="step-item" id="s4"><div class="dot"></div>Extracting medications</div>
      <div class="step-item" id="s5"><div class="dot"></div>Extracting lab results</div>
      <div class="step-item" id="s6"><div class="dot"></div>Extracting procedures</div>
      <div class="step-item" id="s7"><div class="dot"></div>Detecting conflicts</div>
      <div class="step-item" id="s8"><div class="dot"></div>Checking drug interactions</div>
      <div class="step-item" id="s9"><div class="dot"></div>Reconciling medications</div>
      <div class="step-item" id="s10"><div class="dot"></div>Building summary report</div>
    </div>
  </div>

</div>

<footer>Discharge Summary Agent &nbsp;·&nbsp; Dscribe Take-Home Task &nbsp;·&nbsp; For clinician review only</footer>

<script>
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const fileBadge = document.getElementById('fileBadge');
const fileName = document.getElementById('fileName');
const btnAnalyze = document.getElementById('btnAnalyze');
let selectedFile = null;

dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f && f.name.endsWith('.pdf')) setFile(f);
});
fileInput.addEventListener('change', () => { if (fileInput.files[0]) setFile(fileInput.files[0]); });

function setFile(f) {
  selectedFile = f;
  fileName.textContent = f.name;
  fileBadge.style.display = 'flex';
  btnAnalyze.style.display = 'block';
}

let pollTimer;

function markStep(idx, state) {
  const el = document.getElementById('s' + (idx+1));
  if (!el) return;
  el.classList.remove('active','done');
  if (state === 'active' || state === 'done') {
    el.classList.add(state);
  }
}

async function analyze() {
  if (!selectedFile) return;
  document.getElementById('upload-state').style.display = 'none';
  document.getElementById('processingState').style.display = 'block';

  const fd = new FormData();
  fd.append('pdf', selectedFile);

  const res = await fetch('/upload', { method:'POST', body:fd });
  const { job_id, error } = await res.json();
  if (error) { alert(error); return; }

  // Map backend tool names to step indices
  const toolToStep = {
    'read_pdfs': 0,
    'extract_demographics': 1,
    'extract_diagnoses': 2,
    'extract_medications': 3,
    'extract_labs': 4,
    'extract_procedures': 5,
    'extract_discharge_info': 5, // map discharge info to same step group
    'detect_conflicts': 6,
    'check_drug_interactions': 7,
    'reconcile_medications': 8,
    'build_summary': 9
  };

  pollTimer = setInterval(async () => {
    try {
      const s = await (await fetch('/status/' + job_id)).json();
      
      if (s.last_reasoning) {
        document.getElementById('statusText').textContent = s.last_reasoning;
      }

      const activeIdx = toolToStep[s.last_tool];
      if (activeIdx !== undefined) {
        for (let i = 0; i < 10; i++) {
          if (i < activeIdx) { markStep(i, 'done'); }
          else if (i === activeIdx) { markStep(i, 'active'); }
          else { markStep(i, 'pending'); }
        }
      }

      if (s.status === 'complete') {
        clearInterval(pollTimer);
        for (let i=0;i<10;i++) markStep(i,'done');
        setTimeout(() => { window.location.href = '/report/' + job_id; }, 600);
      } else if (s.status === 'error') {
        clearInterval(pollTimer);
        alert('Error: ' + s.error);
      }
    } catch (err) {
      console.error('Polling error:', err);
    }
  }, 1000);
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    print("\n🏥  Discharge Summary Agent — Web UI")
    print("📡  http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
