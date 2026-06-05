"""
Templates — formatting templates for rendering the discharge summary
in various output formats (plain text, markdown, JSON).
"""

from datetime import datetime


def render_markdown(summary: dict) -> str:
    """
    Render a discharge summary as a structured Markdown document.

    Args:
        summary: Structured summary dict from summary_builder.

    Returns:
        Formatted Markdown string.
    """
    patient = summary.get("patient", {})
    diagnoses = summary.get("diagnoses", [])
    medications = summary.get("medications", [])
    labs = summary.get("labs", [])
    procedures = summary.get("procedures", [])
    discharge = summary.get("discharge", {})
    interactions = summary.get("drug_interactions", [])
    conflicts = summary.get("conflicts", [])
    escalations = summary.get("escalations", [])

    lines = [
        "# Discharge Summary",
        f"*Generated: {summary.get('generated_at', datetime.now().isoformat())}*",
        "",
        "---",
        "",
        "## Patient Information",
        f"| Field | Value |",
        f"|---|---|",
        f"| **Name** | {patient.get('name', 'N/A')} |",
        f"| **Date of Birth** | {patient.get('date_of_birth', 'N/A')} |",
        f"| **Age** | {patient.get('age', 'N/A')} |",
        f"| **Gender** | {patient.get('gender', 'N/A')} |",
        f"| **MRN** | {patient.get('mrn', 'N/A')} |",
        f"| **Admission Date** | {patient.get('admission_date', 'N/A')} |",
        f"| **Discharge Date** | {patient.get('discharge_date', 'N/A')} |",
        f"| **Attending Physician** | {patient.get('attending_physician', 'N/A')} |",
        "",
    ]

    # Diagnoses
    lines += ["## Diagnoses", ""]
    if diagnoses:
        for dx in diagnoses:
            tag = f"**[{dx.get('type', '').upper()}]**"
            icd = f" *(ICD: {dx['icd_code']})*" if dx.get("icd_code") else ""
            lines.append(f"- {tag} {dx.get('name', 'Unknown')}{icd} — *{dx.get('status', '')}*")
    else:
        lines.append("*No diagnoses extracted.*")
    lines.append("")

    # Medications
    lines += ["## Medications", ""]
    if medications:
        lines += ["| Medication | Dose | Route | Frequency | Status |",
                  "|---|---|---|---|---|"]
        for med in medications:
            lines.append(
                f"| {med.get('name', 'N/A')} | {med.get('dose', 'N/A')} | "
                f"{med.get('route', 'N/A')} | {med.get('frequency', 'N/A')} | "
                f"{med.get('status', 'N/A')} |"
            )
    else:
        lines.append("*No medications extracted.*")
    lines.append("")

    # Labs
    lines += ["## Laboratory Results", ""]
    if labs:
        lines += ["| Test | Value | Unit | Flag | Date |",
                  "|---|---|---|---|---|"]
        for lab in labs:
            flag = lab.get("flag") or ""
            flag_str = f"⚠️ {flag.upper()}" if flag and flag != "normal" else flag
            lines.append(
                f"| {lab.get('test', 'N/A')} | {lab.get('value', 'N/A')} | "
                f"{lab.get('unit', '')} | {flag_str} | {lab.get('date', '')} |"
            )
    else:
        lines.append("*No lab results extracted.*")
    lines.append("")

    # Procedures
    lines += ["## Procedures", ""]
    if procedures:
        for proc in procedures:
            lines.append(f"- **{proc.get('name', 'Unknown')}** ({proc.get('type', '')}) — {proc.get('date', 'date unknown')}")
            if proc.get("findings"):
                lines.append(f"  - Findings: {proc['findings']}")
    else:
        lines.append("*No procedures extracted.*")
    lines.append("")

    # Discharge Info
    lines += ["## Discharge Planning", ""]
    lines.append(f"**Disposition:** {discharge.get('disposition', 'N/A')}")
    lines.append(f"**Condition at Discharge:** {discharge.get('discharge_condition', 'N/A')}")
    lines.append(f"**Diet:** {discharge.get('diet', 'N/A')}")
    lines.append(f"**Activity:** {discharge.get('activity', 'N/A')}")
    lines.append("")

    follow_ups = discharge.get("follow_up_appointments") or []
    if follow_ups:
        lines.append("**Follow-Up Appointments:**")
        for f in follow_ups:
            lines.append(
                f"- {f.get('provider', 'Unknown')} ({f.get('specialty', '')}) — "
                f"{f.get('timeframe', '')} — *{f.get('reason', '')}*"
            )
        lines.append("")

    return_prec = discharge.get("return_precautions") or []
    if return_prec:
        lines.append("**Return Precautions:**")
        for rp in return_prec:
            lines.append(f"- {rp}")
        lines.append("")

    # Flags Section
    if escalations:
        lines += ["---", "", "## ⚠️ Escalation Flags", ""]
        for esc in escalations:
            urgency = esc.get("urgency", "").upper()
            emoji = "🚨" if urgency == "EMERGENT" else "⚠️" if urgency == "URGENT" else "ℹ️"
            lines.append(f"{emoji} **[{urgency}]** {esc.get('finding', '')} — {esc.get('reason', '')}")
        lines.append("")

    if interactions:
        lines += ["## 💊 Drug Interactions", ""]
        for ix in interactions:
            sev = ix.get("severity", "").upper()
            drugs = ", ".join(ix.get("drugs", []))
            lines.append(f"- **[{sev}]** {drugs}: {ix.get('description', '')}")
        lines.append("")

    if conflicts:
        lines += ["## 🔍 Record Conflicts", ""]
        for c in conflicts:
            lines.append(f"- **[{c.get('severity', '').upper()}]** {c.get('type', '')}: {c.get('description', '')}")
        lines.append("")

    return "\n".join(lines)


def render_plain_text(summary: dict) -> str:
    """Render a minimal plain-text version of the discharge summary."""
    md = render_markdown(summary)
    # Strip markdown symbols for plain text
    plain = md.replace("**", "").replace("*", "").replace("##", "").replace("#", "").replace("|", "  ")
    return plain
