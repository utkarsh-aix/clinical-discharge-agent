"""
extractors/diagnoses.py
Clinical diagnoses extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema
# ---------------------------------------------------------------------------
_DIAGNOSIS_MENTION_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "diagnosis":      {"type": "STRING"},
        "source_section": {"type": "STRING"},
        "type": {
            "type": "STRING",
            "enum": ["provisional", "final", "working", "ER"],
        },
    },
    "required": ["diagnosis", "source_section", "type"],
}

RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "all_diagnosis_mentions": {
            "type": "ARRAY",
            "items": _DIAGNOSIS_MENTION_SCHEMA,
        },
        "principal_diagnosis":   {"type": "STRING", "nullable": True},
        "secondary_diagnoses":   {"type": "ARRAY", "items": {"type": "STRING"}},
        "conflicts_present":     {"type": "BOOLEAN"},
        "conflict_description":  {"type": "STRING", "nullable": True},
        "confidence_notes":      {"type": "STRING"},
    },
    "required": [
        "all_diagnosis_mentions", "principal_diagnosis", "secondary_diagnoses",
        "conflicts_present", "conflict_description", "confidence_notes",
    ],
}

SYSTEM = """You are a clinical data extractor. Extract ALL diagnosis mentions from hospital documents.
STRICT RULES:
- NEVER invent or guess diagnoses
- Capture EVERY diagnosis mention from EVERY document section, even if they conflict
- Note which section/document each diagnosis came from
- Do NOT resolve conflicts - list them all

Return exactly this JSON:
{
  "all_diagnosis_mentions": [
    {"diagnosis": string, "source_section": string, "type": "provisional|final|working|ER"}
  ],
  "principal_diagnosis": null or string,
  "secondary_diagnoses": [],
  "conflicts_present": true or false,
  "conflict_description": null or string,
  "confidence_notes": string
}"""


def extract_diagnoses(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract all diagnoses from:\n\n{text}",
        max_tokens=2000,
        response_schema=RESPONSE_SCHEMA,
    )
