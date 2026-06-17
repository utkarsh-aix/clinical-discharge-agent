"""
agent/feedback.py — Edit Signal & Reward Metric Engine

Computes two quality signals from a (draft, edited) pair:

  1. Normalized Edit Distance (NED) — character-level Levenshtein,
     normalized to [0, 1]. Lower = better draft (less editing needed).

  2. Section Match Rate (SMR) — for each named clinical section, checks
     if the agent's output matches the doctor's version exactly.
     Returns a score in [0, 1].

Both signals are logged to outputs/feedback_log.json for trend tracking.
"""

import os
import json
import re
from datetime import datetime


# ─── Levenshtein Edit Distance ───────────────────────────────────────────────

def _levenshtein(s1: str, s2: str) -> int:
    """Classic dynamic-programming Levenshtein distance."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for c1 in s1:
        curr_row = [prev_row[0] + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def normalized_edit_distance(draft: str, edited: str) -> float:
    """
    Compute NED between draft and edited string.
    Returns 0.0 if identical, 1.0 if completely different.
    """
    if not draft and not edited:
        return 0.0
    dist = _levenshtein(draft, edited)
    max_len = max(len(draft), len(edited))
    return round(dist / max_len, 4)


# ─── Section Extraction ───────────────────────────────────────────────────────

SECTION_HEADERS = [
    "PATIENT DEMOGRAPHICS",
    "ADMISSION & DISCHARGE",
    "DIAGNOSES",
    "HOSPITAL COURSE",
    "PROCEDURES PERFORMED",
    "KEY INVESTIGATIONS",
    "DISCHARGE MEDICATIONS",
    "MEDICATION CHANGES",
    "ALLERGIES",
    "DISCHARGE CONDITION",
    "FOLLOW-UP INSTRUCTIONS",
    "PENDING RESULTS",
    "CONFLICTS DETECTED",
    "CLINICAL FLAGS",
]


def _extract_sections(text: str) -> dict[str, str]:
    """Split text into sections by header. Returns {section_name: content}."""
    sections = {}
    current_header = "__preamble__"
    current_lines = []

    for line in text.split("\n"):
        matched = False
        for header in SECTION_HEADERS:
            if header in line.upper():
                if current_lines:
                    sections[current_header] = "\n".join(current_lines).strip()
                current_header = header
                current_lines = []
                matched = True
                break
        if not matched:
            current_lines.append(line)

    if current_lines:
        sections[current_header] = "\n".join(current_lines).strip()

    return sections


def section_match_rate(draft: str, edited: str) -> dict:
    """
    Compute section-level match between draft and edited version.

    Returns:
        {
            "overall_smr": float,       # 0..1, higher is better
            "per_section": {            # per section NED scores
                "DISCHARGE MEDICATIONS": 0.12,
                ...
            }
        }
    """
    draft_secs = _extract_sections(draft)
    edited_secs = _extract_sections(edited)

    all_headers = set(draft_secs.keys()) | set(edited_secs.keys())
    per_section = {}
    match_count = 0

    for h in all_headers:
        if h == "__preamble__":
            continue
        d = draft_secs.get(h, "")
        e = edited_secs.get(h, "")
        ned = normalized_edit_distance(d, e)
        per_section[h] = round(ned, 4)
        if ned == 0.0:
            match_count += 1

    overall_smr = round(match_count / max(len(per_section), 1), 4)
    return {"overall_smr": overall_smr, "per_section": per_section}


# ─── Main Scoring Function ────────────────────────────────────────────────────

def score_draft(draft: str, edited: str, patient_id: str, iteration: int) -> dict:
    """
    Compute full quality signal for one (draft, edited) pair.

    Args:
        draft:      Agent-generated summary text
        edited:     Doctor-corrected summary text
        patient_id: e.g. 'patient_2'
        iteration:  Learning loop iteration number (0, 1, 2, ...)

    Returns:
        Score dict with NED, SMR, and metadata. Also appended to feedback_log.json.
    """
    ned = normalized_edit_distance(draft, edited)
    smr_result = section_match_rate(draft, edited)

    score = {
        "patient_id": patient_id,
        "iteration": iteration,
        "timestamp": datetime.now().isoformat(),
        "normalized_edit_distance": ned,
        "section_match_rate": smr_result["overall_smr"],
        "sections": smr_result["per_section"],
        "draft_chars": len(draft),
        "edited_chars": len(edited),
        "total_edits": _levenshtein(draft, edited),
    }

    # Append to persistent feedback log
    log_path = "outputs/feedback_log.json"
    os.makedirs("outputs", exist_ok=True)
    history = []
    if os.path.exists(log_path):
        try:
            with open(log_path) as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            history = []

    history.append(score)
    with open(log_path, "w") as f:
        json.dump(history, f, indent=2)

    return score
