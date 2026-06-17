"""
agent/reviewer.py — Simulated Doctor Reviewer

Applies a consistent, HIDDEN editing policy to any discharge summary draft.
The agent never sees these rules — it can only observe the edited output
and learn from the delta. This models a real clinician review loop.

Editing policy covers:
  1. Medication frequency code normalization (1-0-0 → Once daily)
  2. Route injection for tablets/injections (adds Oral / IV if missing)
  3. Dosage abbreviation standardization (Mitr/mcg normalization)
  4. Drug name casing (TAB. EMESET → Tab. Emeset)
  5. Allergy standardization (None → NKDA)
  6. Department expansion (ward → General Medicine Ward)
  7. Pending results formatting
"""

import re


# ─── Hidden Editing Rules ────────────────────────────────────────────────────

FREQUENCY_MAP = {
    r"1\s*-\s*0\s*-\s*0": "Once daily (OD)",
    r"1\s*-\s*1\s*-\s*1": "Three times daily (TDS)",
    r"1\s*-\s*0\s*-\s*1": "Twice daily (BD)",
    r"0\s*-\s*0\s*-\s*1": "Once at night (ON)",
    r"1\s*-\s*1\s*-\s*0": "Twice daily (BD)",
    r"\bOD\b": "Once daily (OD)",
    r"\bBD\b": "Twice daily (BD)",
    r"\bTDS\b": "Three times daily (TDS)",
    r"\bQID\b": "Four times daily (QID)",
    r"\bSOS\b": "When required (SOS)",
    r"\bPRN\b": "When required (PRN)",
    r"\bPDAN\b": "Once daily (OD)",      # OCR artifact
}

DOSAGE_MAP = {
    r"(\d+)\s*Mitr\b": r"\1mg",
    r"(\d+)\s*mcg\b": r"\1μg",
    r"(\d+)\s*ML\b": r"\1mL",
    r"(\d+)\s*IU\b": r"\1 IU",
}

DEPARTMENT_MAP = {
    r"\bward\b": "General Medicine Ward",
    r"\bICU\b": "Intensive Care Unit (ICU)",
    r"\bCCU\b": "Cardiac Care Unit (CCU)",
    r"\bOPD\b": "Outpatient Department (OPD)",
}

DRUG_PREFIXES = ["TAB\.", "CAP\.", "INJ\.", "SYR\.", "TAB", "CAP", "INJ", "SYR"]


# ─── Rule Application Functions ──────────────────────────────────────────────

def _normalize_frequencies(text: str) -> str:
    for pattern, replacement in FREQUENCY_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _normalize_dosages(text: str) -> str:
    for pattern, replacement in DOSAGE_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _normalize_drug_names(text: str) -> str:
    """Convert TAB. EMESET to Tab. Emeset — title case after prefix."""
    for prefix in DRUG_PREFIXES:
        # Match prefix followed by drug name in ALL CAPS
        pattern = rf"({prefix})\s+([A-Z][A-Z0-9\s\-]+?)(?=\s+\d|\s*$|\s*\||\s*,)"
        def _titlecase(m):
            return m.group(1).title() + " " + m.group(2).title().strip()
        text = re.sub(pattern, _titlecase, text)
    return text


def _inject_routes(text: str) -> str:
    """
    If a medication line mentions TAB/CAP with no route, inject 'Oral'.
    If INJ with no route, inject 'IV'.
    """
    lines = text.split("\n")
    out = []
    for line in lines:
        # Only touch medication lines (contain drug names and dosages)
        if re.search(r"\d+\s*(mg|μg|mL|IU|mcg)", line, re.IGNORECASE):
            if re.search(r"\bOral\b|\bIV\b|\bIM\b|\bSC\b|\bTopical\b|\bInhaled\b", line, re.IGNORECASE):
                out.append(line)  # already has route
            elif re.search(r"\bTAB\b|\bCAP\b", line, re.IGNORECASE):
                # Inject Oral before the frequency
                line = re.sub(
                    r"(Once daily|Twice daily|Three times daily|Four times daily|When required|OD|BD|TDS|QID|SOS|PRN)",
                    r"Oral \1",
                    line,
                    count=1,
                    flags=re.IGNORECASE
                )
                out.append(line)
            elif re.search(r"\bINJ\b", line, re.IGNORECASE):
                line = re.sub(
                    r"(Once daily|Twice daily|Three times daily|Four times daily|When required|OD|BD|TDS|QID|SOS|PRN|Q\d+h)",
                    r"IV \1",
                    line,
                    count=1,
                    flags=re.IGNORECASE
                )
                out.append(line)
            else:
                out.append(line)
        else:
            out.append(line)
    return "\n".join(out)


def _normalize_allergies(text: str) -> str:
    """Replace bare 'None' in allergy section with NKDA."""
    text = re.sub(
        r"(Allergies\s*[:\-]\s*)(None|nil|no known|nkda|N/A)",
        r"\1No known drug allergies (NKDA)",
        text,
        flags=re.IGNORECASE
    )
    return text


def _normalize_departments(text: str) -> str:
    for pattern, replacement in DEPARTMENT_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


# ─── Main Public Function ────────────────────────────────────────────────────

def apply_doctor_edits(draft: str) -> str:
    """
    Apply the simulated doctor's editing policy to the draft.
    Returns the edited version. The difference between draft and this output
    is the learning signal for the correction memory.

    Args:
        draft: The agent's generated discharge summary text.

    Returns:
        Edited summary string representing what a doctor would correct.
    """
    edited = draft
    edited = _normalize_dosages(edited)
    edited = _normalize_frequencies(edited)
    edited = _inject_routes(edited)
    edited = _normalize_drug_names(edited)
    edited = _normalize_allergies(edited)
    edited = _normalize_departments(edited)
    return edited


def get_edit_pairs(draft: str) -> list[dict]:
    """
    Return a list of (original_line, edited_line) pairs where the reviewer
    made a change. Useful for building correction memory.

    Returns:
        List of dicts with keys: original, corrected, line_index
    """
    edited = apply_doctor_edits(draft)
    draft_lines = draft.split("\n")
    edited_lines = edited.split("\n")

    pairs = []
    for i, (orig, corr) in enumerate(zip(draft_lines, edited_lines)):
        if orig.strip() != corr.strip() and orig.strip():
            pairs.append({
                "line_index": i,
                "original": orig.strip(),
                "corrected": corr.strip(),
            })
    return pairs
