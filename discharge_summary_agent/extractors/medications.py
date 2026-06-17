"""
extractors/medications.py
Medications extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema
# ---------------------------------------------------------------------------
_MED_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "name":      {"type": "STRING"},
        "dose":      {"type": "STRING", "nullable": True},
        "route":     {"type": "STRING", "nullable": True},
        "frequency": {"type": "STRING", "nullable": True},
    },
    "required": ["name", "dose", "route", "frequency"],
}

_MED_INPATIENT_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "name":      {"type": "STRING"},
        "dose":      {"type": "STRING", "nullable": True},
        "route":     {"type": "STRING", "nullable": True},
        "frequency": {"type": "STRING", "nullable": True},
        "dates":     {"type": "STRING", "nullable": True},
    },
    "required": ["name", "dose", "route", "frequency", "dates"],
}

_MED_DISCHARGE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "name":      {"type": "STRING"},
        "dose":      {"type": "STRING", "nullable": True},
        "route":     {"type": "STRING", "nullable": True},
        "frequency": {"type": "STRING", "nullable": True},
        "duration":  {"type": "STRING", "nullable": True},
    },
    "required": ["name", "dose", "route", "frequency", "duration"],
}

_PRE_ADMIT_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "name":  {"type": "STRING"},
        "notes": {"type": "STRING"},
    },
    "required": ["name", "notes"],
}

RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "admission_medications":     {"type": "ARRAY", "items": _MED_SCHEMA},
        "inpatient_medications":     {"type": "ARRAY", "items": _MED_INPATIENT_SCHEMA},
        "discharge_medications":     {"type": "ARRAY", "items": _MED_DISCHARGE_SCHEMA},
        "pre_admission_medications": {"type": "ARRAY", "items": _PRE_ADMIT_SCHEMA},
        "confidence_notes":          {"type": "STRING"},
    },
    "required": [
        "admission_medications", "inpatient_medications",
        "discharge_medications", "pre_admission_medications",
        "confidence_notes",
    ],
}

SYSTEM = """You are a clinical data extractor. Extract all medications from hospital documents.
STRICT RULES:
- NEVER invent medication names, doses, or frequencies
- If dose is not documented, return null for that field - do not guess
- Capture admission meds, inpatient meds, and discharge meds separately

Return exactly this JSON:
{
  "admission_medications": [
    {"name": string, "dose": null or string, "route": null or string, "frequency": null or string}
  ],
  "inpatient_medications": [
    {"name": string, "dose": null or string, "route": null or string, "frequency": null or string, "dates": null or string}
  ],
  "discharge_medications": [
    {"name": string, "dose": null or string, "route": null or string, "frequency": null or string, "duration": null or string}
  ],
  "pre_admission_medications": [
    {"name": string, "notes": string}
  ],
  "confidence_notes": string
}"""


def extract_medications(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract all medications from:\n\n{text}",
        max_tokens=2000,
        response_schema=RESPONSE_SCHEMA,
    )
