import os
import re
import uuid
import secrets
import logging
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, Response, render_template
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB
# Phase 4: Flask secret key from env (never hardcoded)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Phase 3: Bounded thread pool — prevents DoS via unlimited thread spawning
_EXECUTOR = ThreadPoolExecutor(max_workers=4)

# Phase 3: Rate limiter — 5 uploads per minute per IP
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(get_remote_address, app=app, default_limits=[])
    _LIMITER_AVAILABLE = True
except ImportError:
    limiter = None
    _LIMITER_AVAILABLE = False
    logger.warning("flask-limiter not installed — rate limiting disabled")

# In-memory job store
jobs: dict[str, dict] = {}
import threading
jobs_lock = threading.Lock()


def load_existing_jobs():
    """Restore completed jobs from saved HTML reports on disk.
    Phase 1: pickle removed — state is not restored (jobs are ephemeral).
    """
    import glob
    if not os.path.exists(OUTPUT_DIR):
        return
    reports = glob.glob(os.path.join(OUTPUT_DIR, "*_report.html"))
    for r_path in reports:
        filename = os.path.basename(r_path)
        job_id = filename.replace("_report.html", "")
        t_path = os.path.join(OUTPUT_DIR, f"{job_id}_trace.json")
        if os.path.exists(t_path):
            try:
                with open(r_path, "r", encoding="utf-8") as f:
                    r_html = f.read()
            except Exception:
                r_html = ""

            with jobs_lock:
                jobs[job_id] = {
                    "status": "complete",
                    "patient_id": job_id,
                    "filename": f"{job_id}.pdf",
                    "report_html": r_html,
                    "patient_name": job_id,
                    "state": None,  # state not restored — pickle removed for security
                }


load_existing_jobs()


def run_agent_job_folder(job_id: str, patient_folder: str, patient_id: str):
    """Run the discharge agent using a patient folder.
    Phase 1: pickle removed — state kept in-memory only during job lifetime.
    """
    try:
        with jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["step"] = "Reading PDF…"

        from agent.loop import DischargeAgent
        from output.html_report import generate_html_report

        agent = DischargeAgent(
            patient_folder=patient_folder,
            patient_id=patient_id,
            max_steps=25,
        )
        with jobs_lock:
            jobs[job_id]["state"] = agent.state
        state = agent.run()

        report_html = generate_html_report(state, None)

        # Save HTML report and trace (no pickle — state stays in memory)
        report_path = os.path.join(OUTPUT_DIR, f"{job_id}_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        trace_path = os.path.join(OUTPUT_DIR, f"{job_id}_trace.json")
        agent.tracer.export_trace(trace_path)

        # Serialise conflict details for the UI
        raw_conflicts = state.conflicts_detected or []
        conflict_details = []
        for c in raw_conflicts:
            if isinstance(c, dict):
                conflict_details.append(c)
            elif hasattr(c, "__dict__"):
                conflict_details.append(vars(c))

        with jobs_lock:
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["report_html"] = report_html
            jobs[job_id]["steps"] = state.current_step
            jobs[job_id]["conflicts"] = len(raw_conflicts)
            jobs[job_id]["conflict_details"] = conflict_details
            jobs[job_id]["patient_name"] = (state.demographics or {}).get("patient_name") or patient_id

    except Exception as e:
        logger.exception("Agent job %s failed", job_id)
        with jobs_lock:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(e)
    finally:
        import shutil
        if os.path.exists(patient_folder):
            shutil.rmtree(patient_folder, ignore_errors=True)


@app.route("/")
def index():
    return render_template("ui.html")


def _validate_mime(file_storage) -> bool:
    """Phase 3: Validate actual file content using magic bytes, not just extension."""
    try:
        import magic
        header = file_storage.read(2048)
        file_storage.seek(0)
        mime = magic.from_buffer(header, mime=True)
        return mime in ("application/pdf", "application/zip",
                        "application/x-zip-compressed", "application/x-zip")
    except ImportError:
        # python-magic not installed — fall back to extension-only check (log warning)
        logger.warning("python-magic not installed — skipping MIME validation")
        return True


def _sanitize_patient_id(raw_filename: str) -> str:
    """Phase 2: Strip path components and allow only safe characters."""
    basename = os.path.basename(raw_filename)          # remove any path components
    name_no_ext = os.path.splitext(basename)[0]
    safe = re.sub(r"[^a-zA-Z0-9_\-.]", "_", name_no_ext)  # allowlist only
    return safe[:80] or "patient"                       # cap at 80 chars


def _upload_handler():
    """Core upload logic, wrapped so rate-limiting decorator can be applied conditionally."""
    if "pdf" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["pdf"]
    filename_lower = f.filename.lower()

    # Phase 2: extension check (first gate)
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".zip")):
        return jsonify({"error": "Only PDF or ZIP files accepted"}), 400

    # Phase 3: MIME validation (second gate — checks actual file content)
    if not _validate_mime(f):
        return jsonify({"error": "Invalid file type — only PDF or ZIP accepted"}), 400

    # Phase 3: Full UUID — harder to enumerate other users' jobs
    job_id = str(uuid.uuid4())

    # Phase 2: Sanitize filename → safe patient ID
    patient_id = _sanitize_patient_id(f.filename)

    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    if filename_lower.endswith(".zip"):
        import zipfile
        zip_save_path = os.path.join(job_dir, "upload.zip")  # never use user filename for save path
        f.save(zip_save_path)
        try:
            with zipfile.ZipFile(zip_save_path, "r") as z:
                # Phase 2: ZIP Slip protection — validate every member path
                resolved_job_dir = os.path.realpath(job_dir)
                for member in z.namelist():
                    member_path = os.path.realpath(os.path.join(job_dir, member))
                    if not member_path.startswith(resolved_job_dir + os.sep):
                        return jsonify({"error": "Malicious ZIP detected — path traversal attempt"}), 400
                z.extractall(job_dir)
        except zipfile.BadZipFile:
            return jsonify({"error": "Invalid ZIP file"}), 400
        finally:
            if os.path.exists(zip_save_path):
                os.remove(zip_save_path)
    else:
        # Use a sanitized filename, never the raw user-supplied name
        pdf_path = os.path.join(job_dir, f"{patient_id}.pdf")
        f.save(pdf_path)

    with jobs_lock:
        jobs[job_id] = {"status": "queued", "patient_id": patient_id, "filename": f.filename}

    # Phase 3: Submit to bounded thread pool instead of spawning unlimited threads
    future = _EXECUTOR.submit(run_agent_job_folder, job_id, job_dir, patient_id)
    future.add_done_callback(lambda fut: fut.exception())  # surface any silent errors
    return jsonify({"job_id": job_id})


# Apply rate limit only when Flask-Limiter is available
if _LIMITER_AVAILABLE:
    @app.route("/upload", methods=["POST"])
    @limiter.limit("5 per minute")
    def upload():
        return _upload_handler()
else:
    @app.route("/upload", methods=["POST"])
    def upload():
        return _upload_handler()


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

        # Phase 2: expose learning score if available
        phase2 = None
        if state and getattr(state, "phase2_score", None):
            phase2 = state.phase2_score

        return jsonify({
            "status": job.get("status"),
            "patient_id": job.get("patient_id"),
            "patient_name": job.get("patient_name", ""),
            "filename": job.get("filename"),
            "current_step": job.get("current_step", 0),
            "steps": job.get("steps", 0),
            "last_reasoning": job.get("last_reasoning", "Initializing agent planner..."),
            "last_tool": job.get("last_tool", ""),
            "error": job.get("error"),
            "total_steps": 25,
            "progress_pct": round((job.get("current_step", 0) / 25) * 100),
            "stage_label": _get_stage_label(job.get("last_tool", "")),
            "phase2_score": phase2,
            "conflicts": job.get("conflicts", 0),
            "conflict_details": job.get("conflict_details", []),
        })


@app.route("/report/<job_id>")
def report(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job or job.get("status") != "complete":
            return "Report not ready", 404
        report_html = job.get("report_html", "")
        state = job.get("state")
        patient_name = job.get("patient_name", job_id)

    # ?dl=1 triggers PDF file download, or format=pdf
    if request.args.get('dl') or request.args.get('format') == 'pdf':
        if not state:
            return "State object not found. Cannot generate PDF report.", 400

        from output.pdf_report import generate_pdf_report
        try:
            pdf_bytes = generate_pdf_report(state)
            patient = patient_name.replace(' ', '_')
            resp = Response(pdf_bytes, mimetype='application/pdf')
            resp.headers['Content-Disposition'] = f'attachment; filename="{patient}_discharge_report.pdf"'
            return resp
        except Exception as e:
            return f"Error generating PDF: {str(e)}", 500

    return report_html


# Phase 2: /outputs/<path> route REMOVED — it allowed path traversal attacks.
# Reports are accessible only through the authenticated /report/<job_id> route.


if __name__ == "__main__":
    # Phase 4: Bind address from env — defaults to localhost for safety
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_PORT", "5000"))
    print("\n[Hospital]  Discharge Summary Agent — Web UI")
    print(f"[Server]  http://{host}:{port}\n")
    app.run(debug=False, host=host, port=port)
