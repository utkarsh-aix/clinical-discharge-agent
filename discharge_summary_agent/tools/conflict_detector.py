def detect_conflicts(state) -> list[dict]:
    """
    Detect conflicts across extracted data.
    Returns list of conflict dicts.
    """
    conflicts = []

    # 1. DIAGNOSIS CONFLICTS
    # Flag when multiple distinct diagnoses appear across different document sections
    if state.diagnoses_raw:
        mentions = state.diagnoses_raw.get("all_diagnosis_mentions", [])
        unique_diagnoses = set(m["diagnosis"].lower().strip() for m in mentions)

        # 1a. Lateral Conflicts (e.g. "left" vs "right" mentioned in diagnoses)
        has_left = any("left" in d for d in unique_diagnoses)
        has_right = any("right" in d for d in unique_diagnoses)
        if has_left and has_right:
            conflicts.append({
                "conflict_type": "diagnosis_mismatch",
                "field": "principal_diagnosis",
                "description": f"Lateral diagnosis mismatch: Both 'left' and 'right' sides mentioned across diagnoses: {list(unique_diagnoses)}",
                "all_mentions": mentions,
                "severity": "high",
                "action_required": "Clinician must confirm final lateralization (left vs right side) of the diagnosis"
            })

        # 1b. Missing Principal Diagnosis when multiple conditions exist
        if len(unique_diagnoses) > 1 and not state.principal_diagnosis:
            conflicts.append({
                "conflict_type": "diagnosis_mismatch",
                "field": "principal_diagnosis",
                "description": "Multiple diagnoses documented but no Principal Diagnosis was clearly identified.",
                "all_mentions": mentions,
                "severity": "medium",
                "action_required": "Clinician must select or specify the primary admitting diagnosis"
            })

    # 2. CULTURE RESULT vs INFECTION DIAGNOSIS CONFLICT
    # Flag when any infection-type diagnosis is documented alongside a negative/no-growth culture
    if state.labs and (state.secondary_diagnoses or state.principal_diagnosis):
        urine_cx = state.labs.get("urine_culture", {})
        if urine_cx and urine_cx.get("result"):
            result_text = str(urine_cx["result"]).lower()
            no_growth = any(w in result_text for w in
                            ["no significant", "no growth", "negative", "<10,000", "no organisms"])

            infection_keywords = ["infection", "itis", "sepsis", "bacteremia", "bacteria", "abscess"]
            diagnoses_text = (
                str(state.secondary_diagnoses or "").lower()
                + str(state.principal_diagnosis or "").lower()
                + str(state.diagnoses_raw or "").lower()
            )
            has_infection_dx = any(kw in diagnoses_text for kw in infection_keywords)

            if no_growth and has_infection_dx:
                conflicts.append({
                    "conflict_type": "lab_diagnosis_mismatch",
                    "field": "culture_vs_infection_diagnosis",
                    "description": (
                        f"An infection-type diagnosis is documented but urine culture "
                        f"shows no significant growth: {urine_cx.get('result')}"
                    ),
                    "value_a": "Diagnosis includes infection indicator",
                    "value_b": f"Urine C/S: {urine_cx.get('result')}",
                    "severity": "high",
                    "action_required": "Clinician review required — culture-negative infection or diagnosis revision needed"
                })

    # 3. MEDICATION STOPPED WITHOUT DOCUMENTED REASON
    # Reuse reconciliation data (already computed) — generalises to any stopped medication
    if state.medication_reconciliation:
        stopped = state.medication_reconciliation.get("stopped", [])
        for med in stopped:
            med_name = med.get("name", "Unknown")
            conflicts.append({
                "conflict_type": "medication_stopped_no_reason",
                "field": f"medication_{med_name}",
                "description": (
                    f"'{med_name}' was present at admission but absent from discharge "
                    f"medications with no documented reason."
                ),
                "severity": "medium",
                "action_required": (
                    f"Reconcile why '{med_name}' was stopped or not included at discharge"
                )
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
