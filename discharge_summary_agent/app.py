import os
import uuid
import threading
from flask import Flask, request, jsonify, send_file, Response, render_template
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
    import pickle
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
            
            # Load state pickle if it exists
            state = None
            state_path = os.path.join(OUTPUT_DIR, f"{job_id}_state.pkl")
            if os.path.exists(state_path):
                try:
                    with open(state_path, "rb") as f:
                        state = pickle.load(f)
                except Exception:
                    pass

            with jobs_lock:
                jobs[job_id] = {
                    "status": "complete",
                    "patient_id": job_id,
                    "filename": f"{job_id}.pdf",
                    "report_html": r_html,
                    "patient_name": job_id,
                    "state": state
                }


load_existing_jobs()


def run_agent_job(job_id: str, pdf_path: str, patient_id: str):
    """Run the discharge agent in a background thread (single PDF, legacy)."""
    run_agent_job_folder(job_id, os.path.dirname(pdf_path), patient_id)


def run_agent_job_folder(job_id: str, patient_folder: str, patient_id: str):
    """Run the discharge agent in a background thread using a patient folder."""
    try:
        with jobs_lock:
            jobs[job_id]["status"] = "processing"
            jobs[job_id]["step"] = "Reading PDF…"

        from agent.loop import DischargeAgent
        from output.html_report import generate_html_report
        import pickle

        agent = DischargeAgent(
            patient_folder=patient_folder,
            patient_id=patient_id,
            max_steps=25,
        )
        with jobs_lock:
            jobs[job_id]["state"] = agent.state
        state = agent.run()

        report_html = generate_html_report(state, None)

        # Save HTML report, trace file, and state pickle to outputs directory
        report_path = os.path.join(OUTPUT_DIR, f"{job_id}_report.html")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        trace_path = os.path.join(OUTPUT_DIR, f"{job_id}_trace.json")
        agent.tracer.export_trace(trace_path)

        state_path = os.path.join(OUTPUT_DIR, f"{job_id}_state.pkl")
        with open(state_path, "wb") as f:
            pickle.dump(state, f)

        # Serialise conflict details for the UI
        raw_conflicts = state.conflicts_detected or []
        conflict_details = []
        for c in raw_conflicts:
            if isinstance(c, dict):
                conflict_details.append(c)
            elif hasattr(c, '__dict__'):
                conflict_details.append(vars(c))

        with jobs_lock:
            jobs[job_id]["status"] = "complete"
            jobs[job_id]["report_html"] = report_html
            jobs[job_id]["steps"] = state.current_step
            jobs[job_id]["conflicts"] = len(raw_conflicts)
            jobs[job_id]["conflict_details"] = conflict_details
            jobs[job_id]["patient_name"] = (state.demographics or {}).get("patient_name") or patient_id

    except Exception as e:
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


@app.route("/upload", methods=["POST"])
def upload():
    if "pdf" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["pdf"]
    filename_lower = f.filename.lower()

    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".zip")):
        return jsonify({"error": "Only PDF or ZIP files accepted"}), 400

    job_id = str(uuid.uuid4())[:8]
    patient_id = os.path.splitext(f.filename)[0].replace(" ", "_")
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    if filename_lower.endswith(".zip"):
        import zipfile
        zip_save_path = os.path.join(job_dir, f.filename)
        f.save(zip_save_path)
        try:
            with zipfile.ZipFile(zip_save_path, "r") as z:
                z.extractall(job_dir)
        except zipfile.BadZipFile:
            return jsonify({"error": "Invalid ZIP file"}), 400
        finally:
            os.remove(zip_save_path)
    else:
        pdf_path = os.path.join(job_dir, f.filename)
        f.save(pdf_path)

    with jobs_lock:
        jobs[job_id] = {"status": "queued", "patient_id": patient_id, "filename": f.filename}
    t = threading.Thread(
        target=run_agent_job_folder,
        args=(job_id, job_dir, patient_id),
        daemon=True,
    )
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


@app.route("/outputs/<path:filename>")
def serve_outputs(filename):
    out_dir = os.path.abspath("outputs")
    file_path = os.path.join(out_dir, filename)
    if not os.path.exists(file_path):
        return "File not found", 404
    return send_file(file_path)


# UPLOAD_PAGE is loaded from ui.html at module startup (see top of file)


if __name__ == "__main__":
    print("\n[Hospital]  Discharge Summary Agent — Web UI")
    print("[Server]  http://localhost:5000\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
