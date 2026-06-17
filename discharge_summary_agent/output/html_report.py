from datetime import datetime
import html
import json
import os


def _build_learning_panel(state) -> str:
    """Build the Phase 2 learning metrics panel HTML block."""
    phase2 = getattr(state, "phase2_score", None)
    if not phase2:
        return ""

    ned = phase2.get("ned", None)
    smr = phase2.get("smr", None)
    rules = phase2.get("confirmed_rules", 0)

    # Load historical NED for this patient to compute improvement
    improvement_html = ""
    try:
        feedback_path = "outputs/feedback_log.json"
        if os.path.exists(feedback_path):
            with open(feedback_path) as f:
                history = json.load(f)
            patient_history = [
                h for h in history if h.get("patient_id") == state.patient_id
            ]
            if len(patient_history) >= 2:
                baseline_ned = patient_history[0]["normalized_edit_distance"]
                latest_ned = patient_history[-1]["normalized_edit_distance"]
                improvement_pct = round(
                    (baseline_ned - latest_ned) / max(baseline_ned, 0.0001) * 100, 1
                )
                direction = "↓" if improvement_pct > 0 else "→"
                color = "#2b8a6a" if improvement_pct > 0 else "#5c708a"
                improvement_html = f"""
                <div class="lm-improvement" style="margin-top:10px">
                  <strong>Learning Progress:</strong> Edit distance reduced by
                  <span style="color:{color};font-weight:700">
                    {direction}{abs(improvement_pct)}%
                  </span>
                  over {len(patient_history)} run(s)
                  &nbsp;·&nbsp; Baseline NED: <strong>{baseline_ned:.4f}</strong>
                  → Current NED: <strong>{latest_ned:.4f}</strong>
                </div>"""
    except Exception:
        pass

    ned_str = f"{ned:.4f}" if ned is not None else "—"
    smr_pct = f"{round(smr * 100, 1)}%" if smr is not None else "—"
    good_cls = "good" if ned is not None and ned < 0.05 else ""
    curve_link = ""
    if os.path.exists("outputs/improvement_curve.png"):
        curve_link = '<a href="/outputs/improvement_curve.png" target="_blank" style="font-size:.78rem;color:var(--primary);text-decoration:none;margin-left:auto"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/><line x1="2" y1="20" x2="22" y2="20"/></svg> View improvement curve →</a>'

    return f"""
<div class="learning-panel">
  <h3><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.46 2.5 2.5 0 0 1-1.07-4.73A3 3 0 0 1 4 11a2.5 2.5 0 0 1 1.5-4.5A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.46 2.5 2.5 0 0 0 1.07-4.73A3 3 0 0 0 20 11a2.5 2.5 0 0 0-1.5-4.5A2.5 2.5 0 0 0 14.5 2Z"/></svg> Phase 2 — Learning from Doctor Edits {curve_link}</h3>
  <div class="learning-metrics">
    <div class="lm-card {good_cls}">
      <div class="lm-num">{ned_str}</div>
      <div class="lm-lbl">Edit Distance (NED)</div>
    </div>
    <div class="lm-card good">
      <div class="lm-num">{smr_pct}</div>
      <div class="lm-lbl">Section Match Rate</div>
    </div>
    <div class="lm-card">
      <div class="lm-num">{rules}</div>
      <div class="lm-lbl">Confirmed Rules</div>
    </div>
  </div>
  {improvement_html}
  <div class="lm-improvement" style="margin-top:8px;font-size:.78rem">
    ⓘ NED = 0 means no doctor edits needed. Rules are learned from (draft, edited) pairs and injected into future prompts.
  </div>
</div>"""


def _build_diff_viewer(state) -> str:
    """Build a word-level diff card comparing raw PDF text vs final summary."""
    import difflib
    raw = getattr(state, "raw_text", None) or ""
    summary = getattr(state, "final_summary", None) or ""
    if not raw or not summary:
        return ""

    # Tokenise both texts into words for a readable word-level diff
    raw_words    = raw.split()
    summ_words   = summary.split()

    # Keep only the first 600 tokens from each side to keep the card compact
    raw_words  = raw_words[:600]
    summ_words = summ_words[:600]

    diff = list(difflib.ndiff(raw_words, summ_words))

    # Build HTML spans
    html_tokens = []
    for token in diff:
        code = token[:2]
        word = html.escape(token[2:])  # XSS fix: escape raw OCR/LLM text
        if code == "  ":   # unchanged
            html_tokens.append(f"<span>{word}</span>")
        elif code == "+ ":  # added in summary
            html_tokens.append(f'<ins class="diff-add">{word}</ins>')
        elif code == "- ":  # removed from source
            html_tokens.append(f'<del class="diff-del">{word}</del>')
        # "? " lines are hints — skip

    diff_html = " ".join(html_tokens)
    truncated_note = "" if len(raw.split()) <= 600 else " <em style='color:var(--muted);font-size:.75rem'>(showing first 600 tokens)</em>"

    return f"""
<div class="card full-width" style="margin-top:20px">
  <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg></span><h2>What Changed — Source vs Summary Diff{truncated_note}</h2></div>
  <div class="card-body">
    <div class="diff-legend">
      <span class="diff-add-badge">+ Added by Agent</span>
      <span class="diff-del-badge">&minus; In Source Only</span>
      <span style="font-size:.75rem;color:var(--muted)">Unchanged text shown in grey</span>
    </div>
    <div class="diff-body">{diff_html}</div>
  </div>
</div>"""


def generate_html_report(state, output_path: str = None) -> str:
    import os
    demo = state.demographics or {}
    conflicts = state.conflicts_detected or []
    interactions = state.drug_interactions or []
    recon = state.medication_reconciliation or {}
    recon_flags = recon.get("reconciliation_flags", [])

    # --- OCR Confidence Badge ---
    ocr_conf = getattr(state, "ocr_confidence", None)
    if ocr_conf is not None:
        if ocr_conf >= 85:
            ocr_cls, ocr_icon, ocr_label = "badge-ok",   """<svg xmlns='http://www.w3.org/2000/svg' width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='display:inline;vertical-align:-2px'><path d='M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z'/><circle cx='12' cy='12' r='3'/></svg>""", f"OCR Quality: {ocr_conf:.1f}%"
        elif ocr_conf >= 70:
            ocr_cls, ocr_icon, ocr_label = "badge-warn", """<svg xmlns='http://www.w3.org/2000/svg' width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='display:inline;vertical-align:-2px'><path d='m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z'/><line x1='12' y1='9' x2='12' y2='13'/><line x1='12' y1='17' x2='12.01' y2='17'/></svg>""",  f"Moderate OCR: {ocr_conf:.1f}%"
        else:
            ocr_cls, ocr_icon, ocr_label = "badge-danger","""<svg xmlns='http://www.w3.org/2000/svg' width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='display:inline;vertical-align:-2px'><circle cx='12' cy='12' r='10'/><line x1='12' y1='8' x2='12' y2='12'/><line x1='12' y1='16' x2='12.01' y2='16'/></svg>""",f"Poor OCR: {ocr_conf:.1f}% — Review!"
        ocr_badge = f'<span class="badge {ocr_cls}">{ocr_icon} {ocr_label}</span>'
    else:
        ocr_badge = '<span class="badge badge-ok"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> Digital PDF</span>'

    def val(v, fallback="—"):
        return html.escape(str(v)) if v else fallback

    def med_rows(meds):
        if not meds:
            return '<tr><td colspan="5" class="missing">No data extracted</td></tr>'
        rows = ""
        for m in meds:
            if isinstance(m, dict):
                name = html.escape(str(m.get('name', '—')))
                dose = html.escape(str(m.get('dose', '—')))
                route = html.escape(str(m.get('route', '—')))
                freq = html.escape(str(m.get('frequency', '—')))
                dur = html.escape(str(m.get('duration') or m.get('dates', '—')))
                rows += f"<tr><td>{name}</td><td>{dose}</td><td>{route}</td><td>{freq}</td><td>{dur}</td></tr>"
        return rows

    def conflict_cards(items):
        if not items:
            return '<div class="ok-badge">✓ No conflicts detected</div>'
        h = ""
        for c in items:
            sev = html.escape(str(c.get("severity", "low")))
            ctype = html.escape(c.get("conflict_type", "").replace("_", " ").title())
            desc = html.escape(str(c.get("description", "")))
            action = html.escape(str(c.get("action_required", "Clinician review required")))
            h += f"""<div class="conflict-card sev-{sev}">
  <span class="sev-tag">{sev.upper()}</span>
  <strong>{ctype}</strong>
  <p>{desc}</p>
  <div class="action">→ {action}</div>
</div>"""
        return h

    def ix_cards(items):
        if not items:
            return '<div class="ok-badge">✓ No interactions flagged</div>'
        h = ""
        for ix in items:
            sev = html.escape(str(ix.get("severity", "low")))
            drug_a = html.escape(str(ix.get("drug_a", "")).title())
            drug_b = html.escape(str(ix.get("drug_b", "")).title())
            desc = html.escape(str(ix.get("description", "")))
            h += f"""<div class="conflict-card sev-{sev}">
  <span class="sev-tag">{sev.upper()}</span>
  <strong>{drug_a} + {drug_b}</strong>
  <p>{desc}</p>
</div>"""
        return h

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
        icon = "<svg xmlns='http://www.w3.org/2000/svg' width='15' height='15' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='display:inline;vertical-align:-2px'><path d='m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z'/><line x1='12' y1='9' x2='12' y2='13'/><line x1='12' y1='17' x2='12.01' y2='17'/></svg>" if "FLAG" in f else "<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' stroke-linejoin='round' style='display:inline;vertical-align:-2px'><circle cx='12' cy='12' r='10'/><line x1='12' y1='16' x2='12' y2='12'/><line x1='12' y1='8' x2='12.01' y2='8'/></svg>"
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
  --bg:#f8fafc;
  --surface:#ffffff;
  --surface2:#f1f5f9;
  --border:#e2e8f0;
  --text:#0f172a;
  --muted:#64748b;
  --primary:#0f766e;
  --primary-light:#0d9488;
  --success:#047857;
  --success-bg:rgba(4, 120, 87, 0.06);
  --warning:#b45309;
  --warning-bg:rgba(180, 83, 9, 0.06);
  --danger:#be123c;
  --danger-bg:rgba(190, 18, 60, 0.06);
  --info:#0284c7;
  --info-bg:rgba(2, 132, 199, 0.06);
  --font:'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --r-sm:8px;
  --r-md:12px;
  --r-lg:16px;
  --sh-sm:0 1px 2px 0 rgba(0, 0, 0, 0.02), 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  --sh-md:0 4px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px -2px rgba(0, 0, 0, 0.04), 0 10px 15px -3px rgba(0, 0, 0, 0.03);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;padding:24px;line-height:1.5}}
.header{{background:linear-gradient(135deg,var(--surface) 0%,var(--surface2) 100%);border:1px solid var(--border);border-radius:var(--r-lg);padding:32px;margin-bottom:24px;display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;box-shadow:var(--sh-md)}}
.header-left h1{{font-size:1.6rem;font-weight:700;background:linear-gradient(135deg,var(--text) 30%,var(--primary) 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;letter-spacing:-0.02em}}
.header-left p{{color:var(--muted);font-size:.85rem;margin-top:6px;font-weight:500}}
.badges{{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}}
.badge{{padding:6px 14px;border-radius:20px;font-size:.78rem;font-weight:600}}
.badge-ok{{background:var(--success-bg);color:var(--success);border:1px solid rgba(4,120,87,.2)}}
.badge-warn{{background:var(--warning-bg);color:var(--warning);border:1px solid rgba(180,83,9,.2)}}
.badge-danger{{background:var(--danger-bg);color:var(--danger);border:1px solid rgba(190,18,60,.2)}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:16px;text-align:center;box-shadow:var(--sh-sm);transition:all .2s ease}}
.stat-card:hover{{transform:translateY(-1px);box-shadow:var(--sh-md)}}
.stat-card .num{{font-size:1.8rem;font-weight:700;color:var(--primary)}}
.stat-card .lbl{{font-size:.75rem;color:var(--muted);margin-top:4px;text-transform:uppercase;letter-spacing:.05em;font-weight:600}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:20px;margin-bottom:20px}}
.card{{display:flex;flex-direction:column;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);overflow:hidden;box-shadow:var(--sh-sm)}}
.card-header{{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-shrink:0;background:var(--surface2)}}
.card-header .icon{{font-size:1.1rem;color:var(--primary)}}
.card-header h2{{font-size:.95rem;font-weight:600;color:var(--text);letter-spacing:-0.01em}}
.card-body{{padding:20px;flex:1;overflow:auto}}
.table-responsive{{width:100%;overflow-x:auto;-webkit-overflow-scrolling:touch}}
.field{{display:flex;justify-content:space-between;align-items:baseline;padding:8px 0;border-bottom:1px solid rgba(226,232,240,.5)}}
.field:last-child{{border-bottom:none}}
.field .lbl{{font-size:.8rem;color:var(--muted);min-width:120px;font-weight:500}}
.field .val{{font-size:.85rem;font-weight:600;text-align:right;word-break:break-word;color:var(--text)}}
.missing{{color:var(--muted);font-style:italic;font-size:.8rem;font-weight:400}}
table{{width:100%;border-collapse:collapse;font-size:.82rem}}
th{{background:var(--surface2);color:var(--muted);padding:10px 14px;text-align:left;font-weight:600;font-size:.75rem;text-transform:uppercase;letter-spacing:.04em}}
td{{padding:10px 14px;border-bottom:1px solid rgba(226,232,240,.5);color:var(--text);font-weight:500}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:rgba(241,245,249,.5)}}
.conflict-card{{background:var(--surface);border-radius:var(--r-md);padding:16px 20px;margin-bottom:12px;border:1px solid var(--border);border-left:4px solid var(--danger);box-shadow:var(--sh-sm)}}
.sev-high .conflict-card,.conflict-card.sev-high{{border-left-color:var(--danger);background:rgba(190,18,60,.01)}}
.conflict-card.sev-medium{{border-left-color:var(--warning);background:rgba(180,83,9,.01)}}
.conflict-card.sev-low{{border-left-color:var(--info);background:rgba(2,132,199,.01)}}
.sev-tag{{font-size:.7rem;font-weight:700;padding:3px 8px;border-radius:4px;background:var(--danger-bg);color:var(--danger);display:inline-block;margin-bottom:8px;text-transform:uppercase}}
.conflict-card.sev-medium .sev-tag{{background:var(--warning-bg);color:var(--warning)}}
.conflict-card.sev-low .sev-tag{{background:var(--info-bg);color:var(--info)}}
.conflict-card strong{{display:block;font-size:.88rem;margin-bottom:4px;color:var(--text)}}
.conflict-card p{{font-size:.82rem;color:var(--muted);line-height:1.5}}
.action{{font-size:.78rem;color:var(--primary);margin-top:8px;font-weight:600}}
.ok-badge{{background:var(--success-bg);color:var(--success);border:1px solid rgba(4,120,87,.15);border-radius:var(--r-sm);padding:12px 18px;font-size:.84rem;font-weight:600;display:inline-flex;align-items:center;gap:6px}}
.dx-primary{{background:linear-gradient(135deg,rgba(15,118,110,.08),rgba(15,118,110,.01));border:1px solid rgba(15,118,110,.2);border-radius:var(--r-sm);padding:14px 16px;font-size:.95rem;font-weight:600;margin-bottom:12px;color:var(--primary)}}
.dx-secondary{{list-style:none}}
.dx-secondary li{{padding:8px 0;border-bottom:1px solid rgba(226,232,240,.5);font-size:.85rem;display:flex;align-items:center;gap:8px}}
.dx-secondary li::before{{content:'›';color:var(--primary);font-weight:700;font-size:1.1rem}}
.proc-list{{list-style:none}}
.proc-list li{{padding:8px 0;border-bottom:1px solid rgba(226,232,240,.5);font-size:.83rem;display:flex;align-items:center;gap:8px}}
.proc-list li::before{{content:'◆';color:var(--primary);font-size:.5rem}}
.recon-flag{{background:var(--warning-bg);border:1px solid rgba(180,83,9,.15);border-radius:var(--r-sm);padding:10px 14px;font-size:.82rem;color:var(--warning);margin-bottom:8px;font-weight:500}}
.footer{{text-align:center;color:var(--muted);font-size:.75rem;margin-top:32px;padding:24px;border-top:1px solid var(--border)}}
.full-width{{grid-column:1/-1}}
.draft-banner{{background:var(--warning-bg);border:1px solid rgba(180,83,9,.15);border-radius:var(--r-sm);padding:12px 20px;margin-bottom:20px;font-size:.84rem;color:var(--warning);text-align:center;font-weight:600;letter-spacing:0.02em}}
.learning-panel{{background:linear-gradient(135deg,rgba(15,118,110,.04),rgba(4,120,87,.02));border:1px solid rgba(15,118,110,.15);border-radius:var(--r-lg);padding:24px;margin-top:20px;box-shadow:var(--sh-sm)}}
.learning-panel h3{{font-size:.9rem;font-weight:700;color:var(--primary);margin-bottom:16px;display:flex;align-items:center;gap:8px}}
.learning-metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}}
.lm-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-md);padding:14px;text-align:center;box-shadow:var(--sh-sm)}}
.lm-card .lm-num{{font-size:1.5rem;font-weight:700;color:var(--primary)}}
.lm-card .lm-lbl{{font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-top:4px;font-weight:600}}
.lm-card.good .lm-num{{color:var(--success)}}
.lm-improvement{{font-size:.82rem;color:var(--muted);line-height:1.6}}
.lm-improvement strong{{color:var(--text)}}
.diff-body{{font-size:.82rem;line-height:1.8;color:var(--muted);word-break:break-word;background:var(--surface2);border-radius:var(--r-md);padding:16px;max-height:340px;overflow-y:auto;font-family:var(--font)}}
ins.diff-add{{background:rgba(4,120,87,.15);color:var(--success);text-decoration:none;border-radius:3px;padding:2px 6px;font-weight:600}}
del.diff-del{{background:rgba(190,18,60,.08);color:var(--danger);border-radius:3px;padding:2px 6px}}
.diff-legend{{display:flex;gap:14px;margin-bottom:12px;align-items:center;flex-wrap:wrap}}
.diff-add-badge{{background:rgba(4,120,87,.1);color:var(--success);border:1px solid rgba(4,120,87,.2);border-radius:20px;padding:4px 12px;font-size:.73rem;font-weight:600}}
.diff-del-badge{{background:rgba(190,18,60,.08);color:var(--danger);border:1px solid rgba(190,18,60,.15);border-radius:20px;padding:4px 12px;font-size:.73rem;font-weight:600}}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-4px"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/><line x1="12" y1="6" x2="12" y2="10"/><line x1="10" y1="8" x2="14" y2="8"/></svg> Discharge Summary</h1>
    <p>Generated {datetime.now().strftime('%d %b %Y, %H:%M')} &nbsp;·&nbsp; Patient ID: <strong>{state.patient_id}</strong></p>
    <div class="badges">
      <span class="badge {'badge-ok' if state.status=='complete' else 'badge-warn'}">{state.status.upper()}</span>
      <span class="badge badge-ok">Steps: {state.current_step}/{state.max_steps}</span>
      {ocr_badge}
      {'<span class="badge badge-danger"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> ' + str(len(conflicts)) + ' Conflicts</span>' if conflicts else '<span class="badge badge-ok">✓ No Conflicts</span>'}
      {'<span class="badge badge-warn"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> ' + str(len(interactions)) + ' Interactions</span>' if interactions else ''}
    </div>
  </div>
</div>

<div class="draft-banner"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> DRAFT — FOR CLINICIAN REVIEW ONLY — NOT FINALIZED</div>

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
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></span><h2>Patient Demographics</h2></div>
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
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M4.8 2.3A.3.3 0 1 0 5 2H4a2 2 0 0 0-2 2v5a6 6 0 0 0 6 6 6 6 0 0 0 6-6V4a2 2 0 0 0-2-2h-1a.2.2 0 1 0 .3.3"/><path d="M8 15v1a6 6 0 0 0 6 6v0a6 6 0 0 0 6-6v-4"/><circle cx="20" cy="10" r="2"/></svg></span><h2>Diagnoses</h2></div>
    <div class="card-body">
      <div class="dx-primary">{'<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> ' + str(state.principal_diagnosis) if state.principal_diagnosis else '<span class="missing">Principal diagnosis not extracted</span>'}</div>
      {'<ul class="dx-secondary">' + dx_list + '</ul>' if dx_list else '<span class="missing">No secondary diagnoses extracted</span>'}
    </div>
  </div>

  <div class="card full-width">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg></span><h2>Hospital Course</h2></div>
    <div class="card-body">
      {f'<p style="line-height:1.75;font-size:.88rem;white-space:pre-wrap;">{state.hospital_course}</p>' if state.hospital_course else '<div class="draft-banner" style="margin:0;"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Hospital course not extracted — FLAG FOR CLINICIAN REVIEW before finalising</div>'}
    </div>
  </div>

  <div class="card full-width" id="section-labs">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v8m0 0H3m6 0h12m-6 4v4m-4 0h8"/><path d="M6 17l-3 4h18l-3-4"/></svg></span><h2>Key Investigations</h2></div>
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

  <div class="card" id="section-medications">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/></svg></span><h2>Discharge Medications</h2></div>
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
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M6 18h8"/><path d="M3 22h18"/><path d="M14 22a7 7 0 1 0 0-14h-1"/><path d="M9 14h2"/><path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2Z"/><path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3"/></svg></span><h2>Procedures</h2></div>
    <div class="card-body">
      {'<ul class="proc-list">' + proc_list + '</ul>' if proc_list else '<span class="missing">No procedures extracted</span>'}
    </div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg></span><h2>Discharge Info</h2></div>
    <div class="card-body">
      <div class="field"><span class="lbl">Condition</span><span class="val">{val(state.discharge_condition)}</span></div>
      <div class="field"><span class="lbl">Follow-up</span><span class="val">{val(state.follow_up_instructions)}</span></div>
      <div class="field"><span class="lbl">Allergies</span><span class="val {'missing' if not state.allergies else ''}">{val(state.allergies, '<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg> Not documented — verify before discharge')}</span></div>
      {''.join(f'<div class="field"><span class="lbl">Pending</span><span class="val">{p}</span></div>' for p in (state.pending_results or [])) or '<div class="field"><span class="lbl">Pending</span><span class="val missing">None documented</span></div>'}
    </div>
  </div>

  <div class="card full-width" id="section-conflicts">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></span><h2>Conflicts Requiring Clinician Review</h2></div>
    <div class="card-body">{conflict_cards(conflicts)}</div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-2px"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg></span><h2>Drug Interactions</h2></div>
    <div class="card-body">{ix_cards(interactions)}</div>
  </div>

  <div class="card">
    <div class="card-header"><span class="icon"><svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="display:inline;vertical-align:-3px"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg></span><h2>Medication Reconciliation</h2></div>
    <div class="card-body">{recon_rows}</div>
  </div>

</div>

{_build_learning_panel(state)}


{_build_diff_viewer(state)}

<div class="footer">
  Discharge Summary Agent<br>
  Docs found: {len(state.documents_found)} &nbsp;|&nbsp; Read: {len(state.documents_read)} &nbsp;|&nbsp; Failed: {len(state.documents_failed)}
</div>

</body>
</html>"""

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path
    return html
