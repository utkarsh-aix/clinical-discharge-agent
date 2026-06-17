"""
agent/correction_memory.py — Persistent Correction Memory Store

Stores structured correction records extracted from (draft, edited) pairs.
Corrections seen 2+ times are promoted to "confirmed rules" and injected
into the agent's LLM prompt as few-shot examples.

Storage: outputs/correction_memory.json
"""

import os
import json
import re
from difflib import SequenceMatcher


MEMORY_PATH = "outputs/correction_memory.json"
CONFIRM_THRESHOLD = 2  # Minimum occurrences to become a confirmed rule


# ─── Section Detection ────────────────────────────────────────────────────────

def _detect_section(line: str) -> str:
    """Guess which clinical section a line belongs to."""
    line_upper = line.upper()
    if any(k in line_upper for k in ["MEDICATION", "DRUG", "TAB", "CAP", "INJ", "DOSE"]):
        return "Discharge Medications"
    if any(k in line_upper for k in ["ALLERG"]):
        return "Allergies"
    if any(k in line_upper for k in ["DEPARTMENT", "WARD", "ICU"]):
        return "Demographics"
    if any(k in line_upper for k in ["DIAGNOSIS", "DIAGNOS"]):
        return "Diagnoses"
    if any(k in line_upper for k in ["FOLLOW", "REVIEW", "OPD"]):
        return "Follow-up Instructions"
    return "General"


def _rule_summary(original: str, corrected: str) -> str:
    """Generate a concise human-readable rule description from a diff."""
    orig_words = set(original.split())
    corr_words = set(corrected.split())
    added = corr_words - orig_words
    removed = orig_words - corr_words
    parts = []
    if removed:
        parts.append(f"Replace '{' '.join(removed)}'")
    if added:
        parts.append(f"with '{' '.join(added)}'")
    if parts:
        return " ".join(parts)
    return f"Normalize: '{original[:40]}' → '{corrected[:40]}'"


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ─── Memory Load / Save ───────────────────────────────────────────────────────

def _load_memory() -> list[dict]:
    os.makedirs("outputs", exist_ok=True)
    if not os.path.exists(MEMORY_PATH):
        return []
    try:
        with open(MEMORY_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_memory(records: list[dict]) -> None:
    os.makedirs("outputs", exist_ok=True)
    with open(MEMORY_PATH, "w") as f:
        json.dump(records, f, indent=2)


# ─── Memory Update ────────────────────────────────────────────────────────────

def record_corrections(edit_pairs: list[dict]) -> None:
    """
    Add new (original, corrected) pairs to memory.
    Deduplicates similar corrections and increments count for existing ones.

    Args:
        edit_pairs: List of dicts with keys 'original', 'corrected'
                    (as returned by reviewer.get_edit_pairs)
    """
    memory = _load_memory()

    for pair in edit_pairs:
        orig = pair.get("original", "").strip()
        corr = pair.get("corrected", "").strip()
        if not orig or not corr or orig == corr:
            continue

        # Check if a very similar correction already exists
        matched = False
        for record in memory:
            if (_similarity(record["original"], orig) > 0.85 and
                    _similarity(record["corrected"], corr) > 0.85):
                record["count"] += 1
                record["confirmed"] = record["count"] >= CONFIRM_THRESHOLD
                matched = True
                break

        if not matched:
            section = _detect_section(orig)
            memory.append({
                "section": section,
                "original": orig,
                "corrected": corr,
                "rule_summary": _rule_summary(orig, corr),
                "count": 1,
                "confirmed": False,
            })

    _save_memory(memory)


# ─── Prompt Injection ─────────────────────────────────────────────────────────

def get_prompt_injection(top_n: int = 8) -> str:
    """
    Build a prompt snippet containing the top confirmed correction rules
    to inject into the LLM system prompt.

    Phase 4 — Prompt Injection Guard:
    All rules are validated for type, length, and content before injection.
    Malformed or oversized records are silently dropped.

    Args:
        top_n: Maximum number of rules to inject.

    Returns:
        A formatted string block ready to append to system prompts.
        Returns empty string if no confirmed rules exist yet.
    """
    _MAX_RULE_LEN = 200  # max chars per field to prevent prompt hijacking
    _FORBIDDEN = ["\n", "system:", "user:", "assistant:", "<", ">"]

    def _is_safe(s: str) -> bool:
        """Reject strings that are too long or contain prompt-injection patterns."""
        if not isinstance(s, str) or len(s) > _MAX_RULE_LEN:
            return False
        sl = s.lower()
        return not any(f in sl for f in _FORBIDDEN)

    memory = _load_memory()
    confirmed = [
        r for r in memory
        if r.get("confirmed", False)
        and _is_safe(r.get("original", ""))
        and _is_safe(r.get("corrected", ""))
        and _is_safe(r.get("rule_summary", ""))
    ]

    if not confirmed:
        return ""

    # Sort by count descending (most seen = most important)
    confirmed.sort(key=lambda r: r["count"], reverse=True)
    top = confirmed[:top_n]

    lines = [
        "",
        "━━━ CLINICIAN CORRECTION HISTORY (Apply these learned rules) ━━━",
        "The following corrections were made by a clinician reviewing past drafts.",
        "Apply these rules when generating your output to reduce editing burden.",
        "",
    ]
    for i, rule in enumerate(top, 1):
        lines.append(f"[Rule {i}] Section: {rule['section']}")
        lines.append(f"  Before: {rule['original'][:120]}")
        lines.append(f"  After:  {rule['corrected'][:120]}")
        lines.append(f"  Rule: {rule['rule_summary']}")
        lines.append("")

    lines.append("━━━ END CORRECTION HISTORY ━━━")
    lines.append("")
    return "\n".join(lines)


def get_confirmed_rule_count() -> int:
    """Return the number of confirmed correction rules in memory."""
    return sum(1 for r in _load_memory() if r.get("confirmed", False))


def get_all_rules() -> list[dict]:
    """Return all memory records for inspection."""
    return _load_memory()
