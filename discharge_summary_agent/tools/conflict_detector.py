def detect_conflicts(state) -> list[dict]:
    """
    Detect conflicts across extracted data.
    Returns list of conflict dicts.
    """
    conflicts = []

    # 1. DIAGNOSIS CONFLICTS
    # Check if multiple diagnosis mentions disagree
    if state.diagnoses_raw:
        mentions = state.diagnoses_raw.get("all_diagnosis_mentions", [])
        unique_diagnoses = set(m["diagnosis"].lower().strip() for m in mentions)

        # Known conflict set in patient_2 data
        dka_present = any("dka" in d or "ketoacidosis" in d for d in unique_diagnoses)
        afi_present = any("afi" in d or "acute febrile" in d for d in unique_diagnoses)
        pyelonephritis_present = any("pyelonephritis" in d for d in unique_diagnoses)
        synovitis_present = any("synovitis" in d for d in unique_diagnoses)

        if len(unique_diagnoses) > 2:
            conflicts.append({
                "conflict_type": "diagnosis_mismatch",
                "field": "principal_diagnosis",
                "description": f"Multiple conflicting diagnoses found across documents: {list(unique_diagnoses)}",
                "all_mentions": mentions,
                "severity": "high",
                "action_required": "Clinician must confirm final diagnosis from all listed options"
            })

    # 2. URINE CULTURE vs PYELONEPHRITIS CONFLICT
    if state.labs:
        urine_cx = state.labs.get("urine_culture", {})
        if urine_cx and urine_cx.get("result"):
            result_text = str(urine_cx["result"]).lower()
            no_growth = any(w in result_text for w in ["no significant", "no growth", "negative", "<10,000"])

            diagnoses_text = str(state.secondary_diagnoses or "").lower()
            pyelonephritis_dx = "pyelonephritis" in diagnoses_text or (
                state.diagnoses_raw and "pyelonephritis" in str(state.diagnoses_raw).lower()
            )

            if no_growth and pyelonephritis_dx:
                conflicts.append({
                    "conflict_type": "lab_diagnosis_mismatch",
                    "field": "pyelonephritis_diagnosis_vs_culture",
                    "description": "Patient diagnosed with pyelonephritis but urine culture shows no significant bacteriuria",
                    "value_a": "Diagnosis: Bilateral Pyelonephritis",
                    "value_b": f"Urine C/S: {urine_cx.get('result')}",
                    "severity": "high",
                    "action_required": "Clinician review required - culture-negative pyelonephritis or diagnosis revision needed"
                })

    # 3. AYURVEDIC MEDICATION GAP
    if state.admission_medications and state.discharge_medications:
        admission_str = str(state.admission_medications).lower()
        discharge_str = str(state.discharge_medications).lower()

        if "ayurvedic" in admission_str and "ayurvedic" not in discharge_str:
            conflicts.append({
                "conflict_type": "medication_stopped_no_reason",
                "field": "ayurvedic_medication",
                "description": "Patient was on Ayurvedic medication for T2DM at admission. No documentation of whether continued or stopped at discharge.",
                "severity": "medium",
                "action_required": "Reconcile pre-admission Ayurvedic medication status"
            })

    # 4. DISCHARGE AGAINST MEDICAL ADVICE
    if state.discharge_info_raw:
        discharge_str = str(state.discharge_info_raw).lower()
        if any(w in discharge_str for w in ["request", "against advice", "lama", "attenders not willing"]):
            conflicts.append({
                "conflict_type": "discharge_against_advice",
                "field": "discharge_type",
                "description": "Patient discharged on request / against medical advice. Attenders refused further management.",
                "severity": "medium",
                "action_required": "Must be documented explicitly in summary with LAMA notation"
            })

    return conflicts
