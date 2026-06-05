import os
import json
import webbrowser
from dotenv import load_dotenv
load_dotenv()

from agent.loop import DischargeAgent
from output.html_report import generate_html_report


def run_patient(patient_folder: str, patient_id: str, max_steps: int = 25):
    print(f"\n🏥 Discharge Summary Agent — {patient_id}")
    print(f"📁 Folder: {patient_folder}")
    model_name = "gemini-2.5-flash" if os.getenv("GEMINI_API_KEY") else os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    print(f"🤖 Model: {model_name}")
    print("=" * 60)

    agent = DischargeAgent(patient_folder, patient_id, max_steps)
    state = agent.run()

    os.makedirs("outputs", exist_ok=True)

    # Save summary
    summary_path = f"outputs/{patient_id}_discharge_summary.txt"
    with open(summary_path, "w") as f:
        f.write(state.final_summary or "SUMMARY NOT GENERATED")

    # Save HTML report
    report_path = f"outputs/{patient_id}_report.html"
    generate_html_report(state, report_path)

    # Save trace
    trace_path = f"outputs/{patient_id}_trace.json"
    agent.tracer.export_trace(trace_path)

    print(f"\n{'='*60}")
    print(f"✅ Status:    {state.status}")
    print(f"📊 Steps:     {state.current_step}/{state.max_steps}")
    print(f"⚠️  Conflicts: {len(state.conflicts_detected or [])}")
    print(f"🚨 Flags:     {len(state.flags_for_review or [])}")
    print(f"📄 Summary:   {summary_path}")
    print(f"🌐 Report:    {report_path}")
    print(f"🔍 Trace:     {trace_path}")

    # Open HTML report in browser
    webbrowser.open(f"file://{os.path.abspath(report_path)}")
    print("\n🌐 HTML report opened in browser.")

    # Print summary to console
    print("\n" + "=" * 60)
    print(state.final_summary)

    return state


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Discharge Summary Agent")
    parser.add_argument("--patient-folder", required=True, 
                        help="Path to patient folder containing PDFs")
    parser.add_argument("--patient-id", default=None, 
                        help="Patient ID (defaults to folder name)")
    parser.add_argument("--max-steps", type=int, default=25)
    args = parser.parse_args()
    pid = args.patient_id or os.path.basename(
        args.patient_folder.rstrip("/\\")
    )
    run_patient(args.patient_folder, pid, args.max_steps)
