import os
import glob
from agent.state import AgentState
from agent.tracer import Tracer
from tools.pdf_reader import read_pdf, get_full_text, get_ocr_stats
from tools.conflict_detector import detect_conflicts
from tools.drug_interaction import check_drug_interactions
from tools.escalation import flag_for_clinician_review
from extractors.demographics import extract_demographics
from extractors.diagnoses import extract_diagnoses
from extractors.medications import extract_medications
from extractors.labs import extract_labs
from extractors.procedures import extract_procedures
from extractors.discharge_info import extract_discharge_info
from output.summary_builder import build_discharge_summary, reconcile_medications


class DischargeAgent:
    def __init__(self, patient_folder: str, patient_id: str, max_steps: int = 25):
        self.state = AgentState(
            patient_id=patient_id,
            patient_folder=patient_folder,
            max_steps=max_steps
        )
        self.tracer = Tracer(self.state)

    def plan(self) -> str:
        """Decide next action based on current state."""
        s = self.state

        if not s.raw_text:                              return "read_pdfs"
        if s.demographics is None:                      return "extract_demographics"
        if s.diagnoses_raw is None:                     return "extract_diagnoses"
        if s.admission_medications is None:             return "extract_medications"
        if s.labs is None:                              return "extract_labs"
        if s.procedures is None:                        return "extract_procedures"
        if s.discharge_info_raw is None:                return "extract_discharge_info"
        if s.conflicts_detected is None and s.diagnoses_raw: return "detect_conflicts"
        if s.drug_interactions is None:                 return "check_drug_interactions"
        if s.conflicts_detected and not s.flags_for_review: return "escalate_conflicts"
        if s.medication_reconciliation is None:         return "reconcile_medications"
        if s.final_summary is None:                     return "build_summary"
        return "complete"

    def explain_why(self, tool: str) -> str:
        explanations = {
            "read_pdfs": "No text extracted yet. Reading all PDFs in patient folder first.",
            "extract_demographics": "Text available. Extracting patient demographics.",
            "extract_diagnoses": "Demographics done. Extracting all diagnosis mentions - will check for conflicts.",
            "extract_medications": "Diagnoses extracted. Extracting admission, inpatient, and discharge medications.",
            "extract_labs": "Medications extracted. Extracting all laboratory and imaging results.",
            "extract_procedures": "Labs extracted. Extracting procedures performed.",
            "extract_discharge_info": "Procedures done. Extracting discharge condition and follow-up.",
            "detect_conflicts": "All data extracted. Checking for conflicts across documents.",
            "check_drug_interactions": "Conflicts checked. Running mock drug interaction check.",
            "escalate_conflicts": f"Found {len(self.state.conflicts_detected or [])} conflicts. Escalating to clinician review flags.",
            "reconcile_medications": "Interactions checked. Reconciling admission vs discharge medications.",
            "build_summary": "All data gathered. Building final discharge summary draft.",
        }
        return explanations.get(tool, f"Executing {tool}")

    def run(self) -> AgentState:
        while (self.state.current_step < self.state.max_steps
               and self.state.status == "running"):

            next_tool = self.plan()

            if next_tool == "complete":
                self.state.status = "complete"
                break

            reasoning = self.explain_why(next_tool)
            result = {}

            try:
                result = self._execute(next_tool)
                if isinstance(result, dict) and "error" in result:
                    err_msg = str(result.get("details", "")) + " " + str(result.get("error", ""))
                    if any(kw in err_msg.lower() for kw in ["429", "quota", "limit", "resource_exhausted"]):
                        raise RuntimeError(f"Gemini API Quota Exceeded (429). Please verify your API key limits or billing details: {err_msg}")
                    if any(kw in err_msg.lower() for kw in ["400", "invalid api key", "api_key_invalid", "key not found"]):
                        raise RuntimeError(f"Invalid Gemini API Key. Please check the API key in your .env file: {err_msg}")
            except Exception as e:
                err_msg = str(e)
                if any(kw in err_msg.lower() for kw in ["quota", "429", "api key", "key", "resource_exhausted"]):
                    self.state.status = "error"
                    self.tracer.log_step(reasoning, next_tool, {}, {"error": err_msg}, "error")
                    raise e
                result = {"error": str(e), "details": "Exception in tool execution"}

            self._update_state(next_tool, result)

            next_decision = self.plan()
            self.tracer.log_step(reasoning, next_tool, {}, result, next_decision)
            self.state.current_step += 1

        if self.state.current_step >= self.state.max_steps:
            self.state.status = "max_steps_reached"

        # Always try to build summary with whatever we have
        if self.state.final_summary is None:
            try:
                self.state.final_summary = build_discharge_summary(self.state)
            except Exception as e:
                self.state.final_summary = (
                    f"SUMMARY BUILD FAILED: {e}\n\nPartial data:\n{str(self.state)}"
                )

        return self.state

    def _execute(self, tool: str) -> dict:
        s = self.state

        if tool == "read_pdfs":
            pdfs = list(dict.fromkeys(
                glob.glob(f"{s.patient_folder}/**/*.pdf", recursive=True) +
                glob.glob(f"{s.patient_folder}/*.pdf")
            ))
            if not pdfs:
                return {"error": "no_pdfs_found", "folder": s.patient_folder}
            s.documents_found = pdfs
            all_text = []
            total_ocr = 0
            # Use pre-rendered text/images from scratch_ocr/ if they exist
            possible_caches = [
                os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scratch_ocr")),
                os.path.abspath(os.path.join(os.getcwd(), "..", "scratch_ocr")),
                os.path.abspath(os.path.join(os.getcwd(), "scratch_ocr"))
            ]
            image_cache = None
            for p in possible_caches:
                if os.path.isdir(p):
                    image_cache = p
                    break
            for pdf_path in pdfs:
                result = read_pdf(pdf_path, ocr=True, image_cache_dir=image_cache)
                if result["success"]:
                    s.documents_read.append(pdf_path)
                    all_text.append(get_full_text(result))
                    stats = get_ocr_stats(result)
                    total_ocr += stats["ocr_pages"]
                else:
                    s.documents_failed.append(pdf_path)
            s.raw_text = "\n\n".join(all_text)
            return {
                "pdfs_found": len(pdfs),
                "pdfs_read": len(s.documents_read),
                "total_text_chars": len(s.raw_text),
                "ocr_pages_processed": total_ocr,
                "cache_used": image_cache is not None,
            }

        elif tool == "extract_demographics":
            result = extract_demographics(s.raw_text)
            return result

        elif tool == "extract_diagnoses":
            result = extract_diagnoses(s.raw_text)
            s.diagnoses_raw = result
            return result

        elif tool == "extract_medications":
            return extract_medications(s.raw_text)

        elif tool == "extract_labs":
            return extract_labs(s.raw_text)

        elif tool == "extract_procedures":
            return extract_procedures(s.raw_text)

        elif tool == "extract_discharge_info":
            result = extract_discharge_info(s.raw_text)
            s.discharge_info_raw = result
            return result

        elif tool == "detect_conflicts":
            return detect_conflicts(s)

        elif tool == "check_drug_interactions":
            meds = (s.inpatient_medications or []) + (s.discharge_medications or [])
            return check_drug_interactions(meds)

        elif tool == "escalate_conflicts":
            escalations = []
            for conflict in s.conflicts_detected:
                esc = flag_for_clinician_review(
                    reason=conflict["description"],
                    severity=conflict["severity"],
                    details=conflict
                )
                escalations.append(esc)
            return {"escalations_created": len(escalations)}

        elif tool == "reconcile_medications":
            return reconcile_medications(
                s.admission_medications or [],
                s.discharge_medications or [],
                s.inpatient_medications or [],
                pre_admission_meds=None
            )

        elif tool == "build_summary":
            summary_text = build_discharge_summary(s)
            return {"summary": summary_text}

        return {"error": f"unknown_tool: {tool}"}

    def _update_state(self, tool: str, result: dict):
        s = self.state
        if "error" in result:
            s.flags_for_review.append({
                "reason": f"Extraction tool '{tool}' failed: {result.get('error')}",
                "severity": "high",
                "details": result.get("details", "")
            })
            if tool == "extract_demographics":
                s.demographics = {}
            elif tool == "extract_diagnoses":
                s.diagnoses_raw = {}
                s.principal_diagnosis = None
                s.secondary_diagnoses = []
            elif tool == "extract_medications":
                s.admission_medications = []
                s.discharge_medications = []
                s.inpatient_medications = []
            elif tool == "extract_labs":
                s.labs = {}
                s.pending_results = []
            elif tool == "extract_procedures":
                s.procedures = []
            elif tool == "extract_discharge_info":
                s.discharge_info_raw = {}
                s.discharge_condition = None
                s.follow_up_instructions = None
            elif tool == "detect_conflicts":
                s.conflicts_detected = []
            elif tool == "check_drug_interactions":
                s.drug_interactions = []
            elif tool == "escalate_conflicts":
                pass
            elif tool == "reconcile_medications":
                s.medication_reconciliation = {}
            elif tool == "build_summary":
                s.final_summary = "ERROR: Summary generation failed."
            return

        if tool == "extract_demographics":
            s.demographics = result
            s.admission_date = result.get("admission_date")
            s.discharge_date = result.get("discharge_date")

        elif tool == "extract_diagnoses":
            s.principal_diagnosis = result.get("principal_diagnosis")
            s.secondary_diagnoses = result.get("secondary_diagnoses", [])

        elif tool == "extract_medications":
            s.admission_medications = result.get("admission_medications", [])
            s.discharge_medications = result.get("discharge_medications", [])
            s.inpatient_medications = result.get("inpatient_medications", [])

        elif tool == "extract_labs":
            s.labs = result
            s.pending_results = result.get("pending_results", [])

        elif tool == "extract_procedures":
            s.procedures = result.get("procedures", [])

        elif tool == "extract_discharge_info":
            s.discharge_condition = result.get("discharge_condition")
            s.follow_up_instructions = result.get("follow_up_instructions")
            if result.get("pending_results_at_discharge"):
                s.pending_results = (s.pending_results or []) + result["pending_results_at_discharge"]

        elif tool == "detect_conflicts":
            s.conflicts_detected = result if isinstance(result, list) else []

        elif tool == "check_drug_interactions":
            s.drug_interactions = result if isinstance(result, list) else []

        elif tool == "escalate_conflicts":
            s.flags_for_review.extend(s.conflicts_detected)

        elif tool == "reconcile_medications":
            s.medication_reconciliation = result

        elif tool == "build_summary":
            s.final_summary = result.get("summary", "")
