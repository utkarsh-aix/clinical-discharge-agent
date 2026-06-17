import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_pdf_report(state) -> bytes:
    """
    Generates a professional, print-ready PDF discharge summary from AgentState
    using reportlab. Returns the PDF file as bytes.
    """
    buffer = io.BytesIO()
    
    # Page setup: letter size, 0.5 inch margins for clinical layout efficiency
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    
    styles = getSampleStyleSheet()
    
    # Custom colors matching the dashboard style
    color_primary = colors.HexColor("#1D9E75") # Clinical Teal
    color_dark = colors.HexColor("#2C3E50")    # Header Text
    color_muted = colors.HexColor("#7F8C8D")   # Muted Label
    color_bg_light = colors.HexColor("#F8F9FA")# Alternating rows / backgrounds
    color_border = colors.HexColor("#E2E8F0")  # Tables border
    color_danger = colors.HexColor("#E53E3E")  # Red for conflicts
    color_danger_bg = colors.HexColor("#FFF5F5")# Light red card
    
    # Custom Paragraph Styles
    style_title = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=color_primary,
        spaceAfter=4
    )
    
    style_subtitle = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=color_muted,
        spaceAfter=15
    )
    
    style_h1 = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=color_dark,
        spaceBefore=14,
        spaceAfter=6,
        keepWithNext=True
    )
    
    style_body = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=color_dark
    )
    
    style_body_bold = ParagraphStyle(
        'BodyBold',
        parent=style_body,
        fontName='Helvetica-Bold'
    )
    
    style_table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )
    
    style_table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=color_dark
    )
    
    style_table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=style_table_cell,
        fontName='Helvetica-Bold'
    )
    
    style_banner = ParagraphStyle(
        'BannerText',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#D69E2E"),
        alignment=1 # Center
    )
    
    style_conflict_text = ParagraphStyle(
        'ConflictText',
        parent=style_body,
        textColor=color_danger
    )

    story = []
    
    # --- HEADER / TITLE ---
    story.append(Paragraph("DISCHARGE SUMMARY DRAFT", style_title))
    gen_time = datetime.now().strftime('%d %b %Y, %H:%M')
    story.append(Paragraph(f"Generated on {gen_time} | Patient ID: {state.patient_id}", style_subtitle))
    
    # --- DRAFT WARNING BANNER ---
    banner_data = [[Paragraph("⚠️ DRAFT REPORT — FOR CLINICIAN REVIEW ONLY — NOT CLINICALLY FINALIZED", style_banner)]]
    banner_table = Table(banner_data, colWidths=[540])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#FFFDF5")),
        ('BORDER', (0, 0), (-1, -1), 1, colors.HexColor("#F6E05E")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 15))
    
    # --- PATIENT DEMOGRAPHICS ---
    story.append(Paragraph("Patient Demographics", style_h1))
    
    demo = state.demographics or {}
    demo_fields = [
        ("Patient Name:", demo.get("patient_name", "—")),
        ("Age / Gender:", f"{demo.get('age', '—')} / {demo.get('gender', '—')}" if demo.get("age") or demo.get("gender") else "—"),
        ("MRN:", demo.get("mrn", "—")),
        ("IP Number:", demo.get("ip_number", "—")),
        ("Admission Date:", state.admission_date or "—"),
        ("Discharge Date:", state.discharge_date or "—"),
        ("Blood Group:", demo.get("blood_group", "—")),
        ("Weight:", demo.get("weight_kg", "—")),
        ("Department:", demo.get("department", "—")),
    ]
    
    # Format demographics in a 3-column table layout
    demo_table_data = []
    current_row = []
    for lbl, val_str in demo_fields:
        current_row.extend([
            Paragraph(lbl, style_body_bold),
            Paragraph(str(val_str), style_body)
        ])
        if len(current_row) == 6: # 3 sets of (label, val)
            demo_table_data.append(current_row)
            current_row = []
    if current_row:
        while len(current_row) < 6:
            current_row.extend(["", ""])
        demo_table_data.append(current_row)
        
    demo_table = Table(demo_table_data, colWidths=[95, 85, 95, 85, 95, 85])
    demo_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, color_border),
    ]))
    story.append(demo_table)
    story.append(Spacer(1, 12))
    
    # --- DIAGNOSES ---
    story.append(Paragraph("Clinical Diagnoses", style_h1))
    dx_data = []
    if state.principal_diagnosis:
        dx_data.append(Paragraph(f"<b>Principal Diagnosis:</b> {state.principal_diagnosis}", style_body))
    
    sec_dx = state.secondary_diagnoses or []
    if sec_dx:
        dx_data.append(Paragraph("<b>Secondary Diagnoses:</b>", style_body))
        for d in sec_dx:
            dx_data.append(Paragraph(f"• {d}", style_body))
            
    if not dx_data:
        dx_data.append(Paragraph("No diagnoses documented.", style_body))
        
    story.append(KeepTogether(dx_data))
    story.append(Spacer(1, 12))
    
    # --- HOSPITAL COURSE ---
    if state.hospital_course:
        story.append(Paragraph("Brief Hospital Course", style_h1))
        story.append(Paragraph(state.hospital_course.replace('\n', '<br/>'), style_body))
        story.append(Spacer(1, 12))
        
    # --- PROCEDURES ---
    procs = state.procedures or []
    if procs:
        story.append(Paragraph("Procedures Performed", style_h1))
        proc_flow = []
        for p in procs:
            p_name = p.get("name", str(p)) if isinstance(p, dict) else str(p)
            proc_flow.append(Paragraph(f"• {p_name}", style_body))
        story.append(KeepTogether(proc_flow))
        story.append(Spacer(1, 12))
        
    # --- LAB RESULTS ---
    labs = state.labs or {}
    cbc = labs.get("cbc", {}) or {}
    bio = labs.get("biochemistry", {}) or {}
    abg = labs.get("abg", {}) or {}
    uc  = labs.get("urine_culture", {}) or {}
    
    lab_items = [
        ("Hemoglobin", cbc.get("hemoglobin"), "g/dL"),
        ("WBC", cbc.get("wbc"), "cells/µL"),
        ("Platelets", cbc.get("platelets"), "lakh/µL"),
        ("Creatinine", bio.get("creatinine"), "mg/dL"),
        ("Sodium", bio.get("sodium"), "mEq/L"),
        ("RBS", bio.get("rbs"), "mg/dL"),
        ("HbA1c", bio.get("hba1c"), "%"),
        ("pH (ABG)", abg.get("ph"), ""),
        ("HCO3", abg.get("hco3"), "mEq/L"),
        ("Urine Culture", uc.get("result") if isinstance(uc, dict) else uc, ""),
        ("USG", labs.get("usg"), ""),
        ("CT KUB", labs.get("ct_kub"), ""),
        ("Echo", labs.get("echo"), ""),
        ("CRP", labs.get("crp"), "mg/L"),
    ]
    
    # Filter out empty labs to show a clean list
    active_labs = [(lbl, val, unit) for lbl, val, unit in lab_items if val]
    
    if active_labs:
        story.append(Paragraph("Key Investigations & Labs", style_h1))
        lab_table_data = [[
            Paragraph("Investigation / Test", style_table_header),
            Paragraph("Result Value", style_table_header),
            Paragraph("Unit", style_table_header)
        ]]
        for lbl, val, unit in active_labs:
            lab_table_data.append([
                Paragraph(lbl, style_table_cell_bold),
                Paragraph(str(val), style_table_cell),
                Paragraph(str(unit), style_table_cell)
            ])
            
        lab_table = Table(lab_table_data, colWidths=[240, 180, 120])
        lab_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), color_primary),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, color_border),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, color_bg_light]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(KeepTogether([lab_table]))
        story.append(Spacer(1, 12))
        
    # --- MEDICATIONS ---
    meds = state.discharge_medications or []
    if meds:
        story.append(Paragraph("Discharge Medications", style_h1))
        med_table_data = [[
            Paragraph("Medication Name", style_table_header),
            Paragraph("Dose", style_table_header),
            Paragraph("Route", style_table_header),
            Paragraph("Frequency", style_table_header),
            Paragraph("Duration / Info", style_table_header)
        ]]
        for m in meds:
            if isinstance(m, dict):
                med_table_data.append([
                    Paragraph(m.get("name", "—"), style_table_cell_bold),
                    Paragraph(m.get("dose", "—"), style_table_cell),
                    Paragraph(m.get("route", "—"), style_table_cell),
                    Paragraph(m.get("frequency", "—"), style_table_cell),
                    Paragraph(m.get("duration") or m.get("dates", "—"), style_table_cell)
                ])
                
        med_table = Table(med_table_data, colWidths=[150, 90, 80, 90, 130])
        med_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), color_primary),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, color_border),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, color_bg_light]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(KeepTogether([med_table]))
        story.append(Spacer(1, 12))
        
    # --- CLINICAL INFO / INSTRUCTIONS ---
    story.append(Paragraph("Discharge Info & Instructions", style_h1))
    info_flow = [
        Paragraph(f"<b>Condition at Discharge:</b> {state.discharge_condition or '—'}", style_body),
        Paragraph(f"<b>Follow-up Appointments:</b> {state.follow_up_instructions or '—'}", style_body),
        Paragraph(f"<b>Allergies:</b> {state.allergies or 'No documented drug allergies.'}", style_body),
    ]
    if state.pending_results:
        pend_str = ", ".join(state.pending_results)
        info_flow.append(Paragraph(f"<b>Pending Lab Results:</b> {pend_str}", style_body))
        
    story.append(KeepTogether(info_flow))
    story.append(Spacer(1, 12))
    
    # --- CONFLICTS DETECTED (RED WARNING SECTION) ---
    conflicts = state.conflicts_detected or []
    if conflicts:
        story.append(Paragraph("⚠️ Record Conflicts Flagged for Verification", style_h1))
        conflict_flow = []
        for c in conflicts:
            sev = c.get("severity", "low").upper()
            c_type = c.get("conflict_type", "").replace("_", " ").title()
            desc = c.get("description", "")
            action = c.get("action_required", "Verify with attending team prior to discharge.")
            
            conflict_flow.append(Paragraph(f"<b>[{sev}] {c_type}</b>", style_conflict_text))
            conflict_flow.append(Paragraph(f"Description: {desc}", style_body))
            conflict_flow.append(Paragraph(f"Action: {action}", style_body_bold))
            conflict_flow.append(Spacer(1, 6))
            
        conflict_table_data = [[conflict_flow]]
        conflict_table = Table(conflict_table_data, colWidths=[540])
        conflict_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), color_danger_bg),
            ('BORDER', (0, 0), (-1, -1), 1, color_danger),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        story.append(KeepTogether([conflict_table]))
        story.append(Spacer(1, 12))
        
    # --- DRUG INTERACTIONS ---
    interactions = state.drug_interactions or []
    if interactions:
        story.append(Paragraph("Potential Drug-Drug Interactions", style_h1))
        ix_flow = []
        for ix in interactions:
            sev = ix.get("severity", "low").upper()
            drugs = ", ".join(ix.get("drugs", []))
            desc = ix.get("description", "")
            ix_flow.append(Paragraph(f"• <b>[{sev}]</b> {drugs}: {desc}", style_body))
        story.append(KeepTogether(ix_flow))
        story.append(Spacer(1, 12))
        
    # Build document
    doc.build(story)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
