from datetime import datetime


def generate_html_report(state, output_path: str = "outputs/report.html") -> str:
    import os
    demo = state.demographics or {}
    conflicts = state.conflicts_detected or []
    interactions = state.drug_interactions or []
    recon = state.medication_reconciliation or {}
    recon_flags = recon.get("reconciliation_flags", [])

    model_name = "gemini-2.5-flash"
    powered_by = "Google Gemini"

    def val(v, fallback="—"):
        return str(v) if v else fallback

    def med_rows(meds):
        if not meds:
            return '<tr><td colspan="5" class="missing">No data extracted</td></tr>'
        rows = ""
        for m in meds:
            if isinstance(m, dict):
                rows += f"<tr><td>{m.get('name','—')}</td><td>{m.get('dose','—')}</td><td>{m.get('route','—')}</td><td>{m.get('frequency','—')}</td><td>{m.get('duration') or m.get('dates','—')}</td></tr>"
        return rows

    def conflict_cards(items):
        if not items:
            return '<div class="ok-badge">✓ No conflicts detected</div>'
        html = ""
        for c in items:
            sev = c.get("severity", "low")
            html += f"""<div class="conflict-card sev-{sev}">
  <span class="sev-tag">{sev.upper()}</span>
  <strong>{c.get('conflict_type','').replace('_',' ').title()}</strong>
  <p>{c.get('description','')}</p>
  <div class="action">→ {c.get('action_required','Clinician review required')}</div>
</div>"""
        return html

    def ix_cards(items):
        if not items:
            return '<div class="ok-badge">✓ No interactions flagged</div>'
        html = ""
        for ix in items:
            sev = ix.get("severity", "low")
            html += f"""<div class="conflict-card sev-{sev}">
  <span class="sev-tag">{sev.upper()}</span>
  <strong>{ix.get('drug_a','').title()} + {ix.get('drug_b','').title()}</strong>
  <p>{ix.get('description','')}</p>
</div>"""
        return html

    labs = state.labs or {}
    cbc = labs.get("cbc", {}) or {}
    bio = labs.get("biochemistry", {}) or {}
    abg = labs.get("abg", {}) or {}
    uc  = labs.get("urine_culture", {}) or {}

    def lab_row(label, value, unit=""):
        v = val(value)
        cls = "missing" if v == "—" else ""
        return f'<tr><td>{label}</td><td class="{cls}">{v}</td><td>{unit}</td></tr>'

    dx_list = ""
    for d in (state.secondary_diagnoses or []):
        dx_list += f"<li>{d}</li>"

    proc_list = ""
    for p in (state.procedures or []):
        name = p.get("name", str(p)) if isinstance(p, dict) else str(p)
        proc_list += f"<li>{name}</li>"

    recon_rows = ""
    for f in recon_flags:
        icon = "⚠️" if "FLAG" in f else "ℹ️"
        recon_rows += f'<div class="recon-flag">{icon} {f}</div>'
    if not recon_rows:
        recon_rows = '<div class="ok-badge">✓ No reconciliation flags</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Discharge Summary — {val(demo.get('patient_name'), 'Patient')}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#0f1117;--surface:#1a1d27;--surface2:#22263a;--border:#2e3250;
  --text:#e8eaf6;--muted:#8b92b8;--primary:#6c63ff;--primary-light:#8b85ff;
  --success:#00c897;--warning:#ffb347;--danger:#ff5c7a;--info:#4fc3f7;
  --font:'Inter',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;padding:24px}}
.header{{background:linear-gradient(135deg,#1a1d27 0%,#22263a 100%);border:1px solid var(--border);border-radius:16px;padding:32px;margin-bottom:24px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px}}
.header-left h1{{font-size:1.6rem;font-weight:700;background:linear-gradient(135deg,var(--primary-light),#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}}
.header-left p{{color:var(--muted);font-size:.85rem;margin-top:6px}}
.badges{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}}
.badge{{padding:5px 14px;border-radius:20px;font-size:.78rem;font-weight:600}}
.badge-ok{{background:rgba(0,200,151,.15);color:var(--success);border:1px solid rgba(0,200,151,.3)}}
.badge-warn{{background:rgba(255,179,71,.15);color:var(--warning);border:1px solid rgba(255,179,71,.3)}}
.badge-danger{{background:rgba(255,92,122,.15);color:var(--danger);border:1px solid rgba(255,92,122,.3)}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px;text-align:center}}
.stat-card .num{{font-size:1.8rem;font-weight:700;color:var(--primary-light)}}
.stat-card .lbl{{font-size:.75rem;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:.05em}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px;margin-bottom:20px}}
.card{{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden}}
.card-header{{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0}}
.card-header .icon{{font-size:1.1rem}}
.card-header h2{{font-size:.95rem;font-weight:600;color:var(--text)}}
.card-body{{padding:20px;flex:1;overflow:auto}}
.table-responsive{{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}}
.field{{display:flex;justify-content:space-between;align-items:baseline;padding:7px 0;border-bottom:1px solid rgba(46,50,80,.5)}}
.field:last-child{{border-bottom:none}}
.field .lbl{{font-size:.8rem;color:var(--muted);min-width:120px}}
.field .val{{font-size:.85rem;font-weight:500;text-align:right;word-break:break-word}}
.missing{{color:#5c6080;font-style:italic;font-size:.8rem}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
th{{background:var(--surface2);color:var(--muted);padding:8px 12px;text-align:left;font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}}
td{{padding:8px 12px;border-bottom:1px solid rgba(46,50,80,.4);color:var(--text)}}
tr:last-child td{{border-bottom:none}}
.conflict-card{{background:var(--surface2);border-radius:10px;padding:14px 16px;margin-bottom:12px;border-left:4px solid var(--danger)}}
.sev-high .conflict-card,.conflict-card.sev-high{{border-left-color:var(--danger)}}
.conflict-card.sev-medium{{border-left-color:var(--warning)}}
.conflict-card.sev-low{{border-left-color:var(--info)}}
.sev-tag{{font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:4px;background:rgba(255,92,122,.2);color:var(--danger);display:inline-block;margin-bottom:6px}}
.conflict-card.sev-medium .sev-tag{{background:rgba(255,179,71,.2);color:var(--warning)}}
.conflict-card.sev-low .sev-tag{{background:rgba(79,195,247,.2);color:var(--info)}}
.conflict-card strong{{display:block;font-size:.88rem;margin-bottom:4px}}
.conflict-card p{{font-size:.82rem;color:var(--muted);line-height:1.5}}
.action{{font-size:.78rem;color:var(--primary-light);margin-top:8px;font-weight:500}}
.ok-badge{{background:rgba(0,200,151,.1);color:var(--success);border:1px solid rgba(0,200,151,.2);border-radius:8px;padding:10px 16px;font-size:.84rem;font-weight:500}}
.dx-primary{{background:linear-gradient(135deg,rgba(108,99,255,.2),rgba(108,99,255,.05));border:1px solid rgba(108,99,255,.4);border-radius:10px;padding:14px 16px;font-size:.95rem;font-weight:600;margin-bottom:12px}}
.dx-secondary{{list-style:none}}
.dx-secondary li{{padding:8px 0;border-bottom:1px solid rgba(46,50,80,.5);font-size:.85rem;display:flex;align-items:center;gap:8px}}
.dx-secondary li::before{{content:'›';color:var(--primary-light);font-weight:700}}
.proc-list{{list-style:none}}
.proc-list li{{padding:7px 0;border-bottom:1px solid rgba(46,50,80,.4);font-size:.83rem;display:flex;align-items:center;gap:8px}}
.proc-list li::before{{content:'◆';color:var(--primary);font-size:.5rem}}
.recon-flag{{background:rgba(255,179,71,.08);border:1px solid rgba(255,179,71,.2);border-radius:8px;padding:10px 14px;font-size:.82rem;color:var(--warning);margin-bottom:8px}}
.footer{{text-align:center;color:var(--muted);font-size:.75rem;margin-top:32px;padding:16px;border-top:1px solid var(--border)}}
.full-width{{grid-column:1/-1}}
.draft-banner{{background:rgba(255,179,71,.08);border:1px solid rgba(255,179,71,.25);border-radius:10px;padding:12px 20px;margin-bottom:20px;font-size:.84rem;color:var(--warning);text-align:center;font-weight:500}}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>🏥 Discharge Summary</h1>
    <p>Generated {datetime.now().strftime('%d %b %Y, %H:%M')} &nbsp;·&nbsp; Patient ID: <strong>{state.patient_id}</strong></p>
    <div class="badges">
      <span class="badge {'badge-ok' if state.status=='complete' else 'badge-warn'}">{state.status.upper()}</span>
      <span class="badge badge-ok">Steps: {state.current_step}/{state.max_steps}</span>
      {'<span class="badge badge-danger">⚠ ' + str(len(conflicts)) + ' Conflicts</span>' if conflicts else '<span class="badge badge-ok">✓ No Conflicts</span>'}
      {'<span class="badge badge-warn">⚡ ' + str(len(interactions)) + ' Interactions</span>' if interactions else ''}
    </div>
  </div>
</div>

<div class="draft-banner">⚠️ DRAFT — FOR CLINICIAN REVIEW ONLY — NOT FINALIZED</div>

<div class="stats">
  <div class="stat-card"><div class="num">{state.current_step}</div><div class="lbl">Agent Steps</div></div>
  <div class="stat-card"><div class="num">{len(state.documents_read)}</div><div class="lbl">PDFs Read</div></div>
  <div class="stat-card"><div class="num">{len(conflicts)}</div><div class="lbl">Conflicts</div></div>
  <div class="stat-card"><div class="num">{len(interactions)}</div><div class="lbl">Drug Interactions</div></div>
  <div class="stat-card"><div class="num">{len(recon_flags)}</div><div class="lbl">Recon Flags</div></div>
  <div class="stat-card"><div class="num">{len(state.procedures or [])}</div><div class="lbl">Procedures</div></div>
</div>

<div class="grid">

  <div class="card">
    <div class="card-header"><span class="icon">👤</span><h2>Patient Demographics</h2></div>
    <div class="card-body">
      <div class="field"><span class="lbl">Name</span><span class="val {'missing' if not demo.get('patient_name') else ''}">{val(demo.get('patient_name'))}</span></div>
      <div class="field"><span class="lbl">Age / Gender</span><span class="val">{val(demo.get('age'))} / {val(demo.get('gender'))}</span></div>
      <div class="field"><span class="lbl">MRN</span><span class="val {'missing' if not demo.get('mrn') else ''}">{val(demo.get('mrn'))}</span></div>
      <div class="field"><span class="lbl">IP Number</span><span class="val {'missing' if not demo.get('ip_number') else ''}">{val(demo.get('ip_number'))}</span></div>
      <div class="field"><span class="lbl">Blood Group</span><span class="val">{val(demo.get('blood_group'))}</span></div>
      <div class="field"><span class="lbl">Weight</span><span class="val">{val(demo.get('weight_kg'))}</span></div>
      <div class="field"><span class="lbl">Department</span><span class="val">{val(demo.get('department'))}</span></div>
      <div class="field"><span class="lbl">Admission</span><span class="val">{val(state.admission_date)}</span></div>
      <div class="field"><span class="lbl">Discharge</span><span class="val">{val(state.discharge_date)}</span></div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon">🩺</span><h2>Diagnoses</h2></div>
    <div class="card-body">
      <div class="dx-primary">{'⚡ ' + str(state.principal_diagnosis) if state.principal_diagnosis else '<span class="missing">Principal diagnosis not extracted</span>'}</div>
      {'<ul class="dx-secondary">' + dx_list + '</ul>' if dx_list else '<span class="missing">No secondary diagnoses extracted</span>'}
    </div>
  </div>

  <div class="card full-width">
    <div class="card-header"><span class="icon">⚗️</span><h2>Key Investigations</h2></div>
    <div class="card-body">
      <div class="table-responsive">
        <table>
          <tr><th>Test</th><th>Value</th><th>Unit</th></tr>
          {lab_row("Hemoglobin", cbc.get("hemoglobin"), "g/dL")}
          {lab_row("WBC", cbc.get("wbc"), "cells/µL")}
          {lab_row("Platelets", cbc.get("platelets"), "lakh/µL")}
          {lab_row("Creatinine", bio.get("creatinine"), "mg/dL")}
          {lab_row("Sodium", bio.get("sodium"), "mEq/L")}
          {lab_row("RBS", bio.get("rbs"), "mg/dL")}
          {lab_row("HbA1c", bio.get("hba1c"), "%")}
          {lab_row("pH (ABG)", abg.get("ph"), "")}
          {lab_row("HCO3", abg.get("hco3"), "mEq/L")}
          {lab_row("Urine Culture", uc.get("result") if isinstance(uc, dict) else uc, "")}
          {lab_row("USG", labs.get("usg"), "")}
          {lab_row("CT KUB", labs.get("ct_kub"), "")}
          {lab_row("Echo", labs.get("echo"), "")}
          {lab_row("CRP", labs.get("crp"), "mg/L")}
        </table>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon">💊</span><h2>Discharge Medications</h2></div>
    <div class="card-body">
      <div class="table-responsive">
        <table>
          <tr><th>Drug</th><th>Dose</th><th>Route</th><th>Freq</th><th>Duration</th></tr>
          {med_rows(state.discharge_medications)}
        </table>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon">🔬</span><h2>Procedures</h2></div>
    <div class="card-body">
      {'<ul class="proc-list">' + proc_list + '</ul>' if proc_list else '<span class="missing">No procedures extracted</span>'}
    </div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon">📋</span><h2>Discharge Info</h2></div>
    <div class="card-body">
      <div class="field"><span class="lbl">Condition</span><span class="val">{val(state.discharge_condition)}</span></div>
      <div class="field"><span class="lbl">Follow-up</span><span class="val">{val(state.follow_up_instructions)}</span></div>
      <div class="field"><span class="lbl">Allergies</span><span class="val">{val(state.allergies, 'Not documented')}</span></div>
      {''.join(f'<div class="field"><span class="lbl">Pending</span><span class="val">{p}</span></div>' for p in (state.pending_results or [])) or '<div class="field"><span class="lbl">Pending</span><span class="val missing">None documented</span></div>'}
    </div>
  </div>

  <div class="card full-width">
    <div class="card-header"><span class="icon">⚠️</span><h2>Conflicts Requiring Clinician Review</h2></div>
    <div class="card-body">{conflict_cards(conflicts)}</div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon">⚡</span><h2>Drug Interactions</h2></div>
    <div class="card-body">{ix_cards(interactions)}</div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon">🔁</span><h2>Medication Reconciliation</h2></div>
    <div class="card-body">{recon_rows}</div>
  </div>

</div>

<div class="footer">
  Discharge Summary Agent &nbsp;·&nbsp; Dscribe Take-Home &nbsp;·&nbsp; Powered by {powered_by}<br>
  Docs found: {len(state.documents_found)} &nbsp;|&nbsp; Read: {len(state.documents_read)} &nbsp;|&nbsp; Failed: {len(state.documents_failed)}
</div>

</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    return output_path
