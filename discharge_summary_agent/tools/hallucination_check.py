"""
tools/hallucination_check.py

Hallucination Shield — cross-references all numeric medical values in the
generated discharge summary against the original source PDF text.

If a dosage, lab value, or frequency appears in the summary but CANNOT be
found verbatim in the raw source text, it is flagged as a hallucination risk.

Strategy:
  1. Extract all medical numeric tokens from the summary (dosages, lab values, frequencies).
  2. For each token, check if it appears verbatim in the source text.
  3. Return a structured list of hallucination risk flags.

Safe to call on any summary. Never raises — always returns a result dict.
"""

import re


# Regex patterns to capture clinically significant numeric tokens
_MEDICAL_PATTERNS = [
    # Dosages: 500mg, 40mg, 10 mg, 0.5mg
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mL|units?|IU|mmol|mEq)\b",
    # Frequencies: Q12h, Q8h, OD, BD, TDS, QID, PRN
    r"\b(?:Q\d+h|QD|OD|BD|TDS|QID|PRN|STAT|SOS)\b",
    # Lab values: 14500, 1.2, 13.8 — only extract if followed by a unit
    r"\b\d+(?:[,\.]\d+)?\s*(?:/µL|/uL|g/dL|mg/dL|mEq/L|mmol/L|%)\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _MEDICAL_PATTERNS]


def verify_summary(summary_text: str, source_text: str) -> dict:
    """
    Cross-reference all medical tokens in the summary against the source text.

    Args:
        summary_text : the final generated discharge summary
        source_text  : the raw text extracted from all source PDFs

    Returns:
        {
            "hallucination_flags": [
                {
                    "value": "600mg",
                    "conflict_type": "hallucination_risk",
                    "severity": "high",
                    "description": "...",
                    "action_required": "..."
                }
            ],
            "tokens_checked": 12,
            "tokens_flagged": 1,
        }
    """
    if not summary_text or not source_text:
        return {"hallucination_flags": [], "tokens_checked": 0, "tokens_flagged": 0}

    # Collect all unique medical tokens from the summary, keeping both original and whitespace-stripped forms
    tokens_found = {}
    for pattern in _COMPILED:
        for match in pattern.finditer(summary_text):
            raw_val = match.group()
            token = re.sub(r"\s+", "", raw_val).lower()
            tokens_found[token] = raw_val.strip()

    # Build a searchable version of the source text with NO whitespace at all
    source_normalized = re.sub(r"\s+", "", source_text).lower()

    hallucination_flags = []
    for token in sorted(tokens_found.keys()):
        # Check if the whitespace-stripped token appears in the stripped source text
        if token not in source_normalized:
            display_val = tokens_found[token]
            hallucination_flags.append({
                "conflict_type": "hallucination_risk",
                "field": "generated_summary",
                "severity": "high",
                "description": (
                    f"The value '{display_val}' appears in the generated summary "
                    f"but was NOT found verbatim in the source PDF text. "
                    f"This may indicate a model hallucination."
                ),
                "action_required": (
                    f"Manually verify '{display_val}' in the original patient documents "
                    f"before finalizing the discharge summary."
                ),
            })

    return {
        "hallucination_flags": hallucination_flags,
        "tokens_checked": len(tokens_found),
        "tokens_flagged": len(hallucination_flags),
    }
