from datetime import datetime

MISSING = "[MISSING - ⚠️ FLAG FOR CLINICIAN REVIEW]"


def fmt(value, fallback=None):
    """Format a value, returning MISSING marker if None or empty."""
    if value is None or value == "" or value == []:
        return fallback or MISSING
    return str(value)


def fmt_list(items, fallback=None):
    if not items:
        return fallback or MISSING
    if isinstance(items, list):
        return "\n".join(f"  • {item}" for item in items if item)
    return str(items)


def build_discharge_summary(state) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Demographics
    demo = state.demographics or {}
    name = fmt(demo.get("patient_name"))
    age_gender = f"{fmt(demo.get('age'))} / {fmt(demo.get('gender'))}"
    mrn = fmt(demo.get("mrn"))
    ip_num = fmt(demo.get("ip_number"))
    blood_group = fmt(demo.get("blood_group"))
    weight = fmt(demo.get("weight_kg"))

    # Dates
    adm_date = fmt(state.admission_date or demo.get("admission_date"))
    dis_date = fmt(state.discharge_date or demo.get("discharge_date"))
    dept = fmt(demo.get("department"))

    # Diagnoses
    principal_dx = fmt(state.principal_diagnosis)
    secondary_dx = fmt_list(state.secondary_diagnoses)

    # Procedures
    procedures = fmt_list(
        [p.get("name", str(p)) for p in (state.procedures or [])] if state.procedures else None
    )

    # Labs summary
    labs = state.labs or {}
    cbc = labs.get("cbc", {}) or {}
    bio = labs.get("biochemistry", {}) or {}
    abg = labs.get("abg", {}) or {}
    labs_summary = f"""  CBC: Hb {fmt(cbc.get('hemoglobin'))}, WBC {fmt(cbc.get('wbc'))}, Platelets {fmt(cbc.get('platelets'))}
  Biochemistry: Creatinine {fmt(bio.get('creatinine'))}, Na {fmt(bio.get('sodium'))}, RBS {fmt(bio.get('rbs'))}, HbA1c {fmt(bio.get('hba1c'))}
  ABG: pH {fmt(abg.get('ph'))}, HCO3 {fmt(abg.get('hco3'))}, pCO2 {fmt(abg.get('pco2'))}
  Urine C/S: {fmt(labs.get('urine_culture', {}).get('result') if isinstance(labs.get('urine_culture'), dict) else labs.get('urine_culture'))}
  USG: {fmt(labs.get('usg'))}
  CT KUB: {fmt(labs.get('ct_kub'))}
  Echo: {fmt(labs.get('echo'))}
  CRP: {fmt(labs.get('crp'))}"""

    # Medications
    def format_med_list(meds):
        if not meds:
            return MISSING
        lines = []
        for m in meds:
            if isinstance(m, dict):
                med_name = m.get("name", "Unknown")
                dose = m.get("dose", "")
                route = m.get("route", "")
                freq = m.get("frequency", "")
                dur = m.get("duration", "")
                lines.append(f"  • {med_name} {dose} {route} {freq} {dur}".strip())
            else:
                lines.append(f"  • {m}")
        return "\n".join(lines)

    discharge_meds = format_med_list(state.discharge_medications)

    # Medication reconciliation
    recon = state.medication_reconciliation or {}
    recon_text = ""
    if recon:
        if recon.get("stopped"):
            recon_text += "\n  STOPPED (no documented reason):\n"
            for m in recon["stopped"]:
                recon_text += f"    ⚠️  {m.get('name')} - {m.get('reason_documented')}\n"
        if recon.get("new_at_discharge"):
            recon_text += "\n  NEWLY STARTED AT DISCHARGE:\n"
            for m in recon["new_at_discharge"]:
                recon_text += f"    ➕ {m.get('name')}\n"
        if recon.get("reconciliation_flags"):
            for flag in recon["reconciliation_flags"]:
                recon_text += f"\n  🚨 {flag}"
    if not recon_text:
        recon_text = MISSING

    # Conflicts section
    conflicts_text = ""
    if state.conflicts_detected:
        for i, c in enumerate(state.conflicts_detected, 1):
            conflicts_text += f"\n  [{i}] [{c.get('severity','?').upper()}] {c.get('conflict_type','')}\n"
            conflicts_text += f"      {c.get('description','')}\n"
            conflicts_text += f"      ACTION: {c.get('action_required','Clinician review required')}\n"
    else:
        conflicts_text = "  No conflicts detected."

    # Flags section
    flags_text = ""
    if state.flags_for_review:
        for i, f in enumerate(state.flags_for_review, 1):
            flags_text += f"\n  [{i}] {f.get('description', f.get('reason', str(f)))}\n"

    # Drug interactions
    if state.drug_interactions:
        flags_text += "\n  DRUG INTERACTIONS (Mock Check):\n"
        for interaction in state.drug_interactions:
            flags_text += f"    ⚡ {interaction.get('drug_a')} + {interaction.get('drug_b')}: {interaction.get('description')}\n"

    if not flags_text:
        flags_text = "  No flags raised."

    # Pending results
    pending = fmt_list(state.pending_results)

    summary = f"""
╔══════════════════════════════════════════════════════════════╗
║           DISCHARGE SUMMARY — DRAFT                          ║
║    ⚠️  FOR CLINICIAN REVIEW ONLY — NOT FINALIZED            ║
╚══════════════════════════════════════════════════════════════╝
Generated: {now}
Patient ID: {state.patient_id}
Agent Steps: {state.current_step}/{state.max_steps} | Status: {state.status}

━━━ PATIENT DEMOGRAPHICS ━━━
Name:         {name}
Age / Gender: {age_gender}
MRN:          {mrn}
IP Number:    {ip_num}
Blood Group:  {blood_group}
Weight:       {weight}

━━━ ADMISSION & DISCHARGE ━━━
Date of Admission:  {adm_date}
Date of Discharge:  {dis_date}
Department:         {dept}

━━━ DIAGNOSES ━━━
Principal Diagnosis:
  {principal_dx}

Secondary Diagnoses:
{secondary_dx}

━━━ HOSPITAL COURSE ━━━
{fmt(state.hospital_course, "See source notes - hospital course not auto-extracted")}

━━━ PROCEDURES PERFORMED ━━━
{procedures}

━━━ KEY INVESTIGATIONS ━━━
{labs_summary}

━━━ DISCHARGE MEDICATIONS ━━━
{discharge_meds}

━━━ MEDICATION CHANGES FROM ADMISSION ━━━
{recon_text}

━━━ ALLERGIES ━━━
{fmt(state.allergies, "Not Known / Not Documented")}

━━━ DISCHARGE CONDITION ━━━
{fmt(state.discharge_condition)}

━━━ FOLLOW-UP INSTRUCTIONS ━━━
{fmt(state.follow_up_instructions)}

━━━ PENDING RESULTS AT DISCHARGE ━━━
{pending}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  CONFLICTS DETECTED — CLINICIAN ACTION REQUIRED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{conflicts_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 CLINICAL FLAGS & ESCALATIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{flags_text}

━━━ AGENT TRACE ━━━
Docs found: {len(state.documents_found)} | Read: {len(state.documents_read)} | Failed: {len(state.documents_failed)}
Missing fields: {state.missing_fields}
Conflicts: {len(state.conflicts_detected or [])} | Flags: {len(state.flags_for_review or [])}
"""
    return summary



def reconcile_medications(admission_meds: list, discharge_meds: list,
                          inpatient_meds: list, pre_admission_meds: list = None) -> dict:
    """
    Compare admission vs discharge medications.
    Flag any changes without documented reason.
    """
    result = {
        "continued": [],
        "stopped": [],
        "new_at_discharge": [],
        "changed": [],
        "pre_admission_status": [],
        "reconciliation_flags": []
    }

    if not admission_meds:
        result["reconciliation_flags"].append(
            "WARNING: No admission medications documented - reconciliation incomplete"
        )
        admission_meds = []

    if not discharge_meds:
        result["reconciliation_flags"].append(
            "WARNING: No explicit discharge medication list found in documents - FLAG FOR CLINICIAN"
        )
        discharge_meds = []

    # Normalize names for comparison
    def normalize(name):
        return str(name).lower().strip() if name else ""

    admission_names = {normalize(m.get("name", m) if isinstance(m, dict) else m): m
                       for m in admission_meds}
    discharge_names = {normalize(m.get("name", m) if isinstance(m, dict) else m): m
                       for m in discharge_meds}

    # Continued
    for name in admission_names:
        if any(name in d_name for d_name in discharge_names):
            result["continued"].append({
                "name": name,
                "admission_details": admission_names[name],
                "discharge_details": discharge_names.get(name)
            })

    # Stopped (on admission, not at discharge)
    for name, med in admission_names.items():
        if not any(name in d_name for d_name in discharge_names):
            result["stopped"].append({
                "name": name,
                "details": med,
                "reason_documented": "NO REASON DOCUMENTED",
                "flag": True
            })
            result["reconciliation_flags"].append(
                f"FLAG: {name} was on admission medications but not found in discharge medications - reason undocumented"
            )

    # New at discharge
    for name, med in discharge_names.items():
        if not any(name in a_name for a_name in admission_names):
            result["new_at_discharge"].append({
                "name": name,
                "details": med,
                "reason_documented": "SEE INPATIENT COURSE"
            })

    # Pre-admission medications (Ayurvedic)
    if pre_admission_meds:
        for med in pre_admission_meds:
            med_name = med.get("name", str(med))
            in_discharge = any(normalize(med_name) in d for d in discharge_names)
            result["pre_admission_status"].append({
                "name": med_name,
                "status_at_discharge": "CONTINUED" if in_discharge else "STATUS UNKNOWN - FLAG",
                "flag": not in_discharge
            })
            if not in_discharge:
                result["reconciliation_flags"].append(
                    f"FLAG: Pre-admission medication '{med_name}' status at discharge not documented"
                )

    return result
