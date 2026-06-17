"""
extractors/labs.py
Laboratory results extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema
# ---------------------------------------------------------------------------
_CBC_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "date":       {"type": "STRING", "nullable": True},
        "hemoglobin": {"type": "STRING", "nullable": True},
        "wbc":        {"type": "STRING", "nullable": True},
        "platelets":  {"type": "STRING", "nullable": True},
        "pcv":        {"type": "STRING", "nullable": True},
    },
    "required": ["date", "hemoglobin", "wbc", "platelets", "pcv"],
}

_BIOCHEM_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "date":       {"type": "STRING", "nullable": True},
        "creatinine": {"type": "STRING", "nullable": True},
        "sodium":     {"type": "STRING", "nullable": True},
        "potassium":  {"type": "STRING", "nullable": True},
        "rbs":        {"type": "STRING", "nullable": True},
        "hba1c":      {"type": "STRING", "nullable": True},
    },
    "required": ["date", "creatinine", "sodium", "potassium", "rbs", "hba1c"],
}

_ABG_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "date":    {"type": "STRING", "nullable": True},
        "ph":      {"type": "STRING", "nullable": True},
        "hco3":    {"type": "STRING", "nullable": True},
        "pco2":    {"type": "STRING", "nullable": True},
        "lactate": {"type": "STRING", "nullable": True},
    },
    "required": ["date", "ph", "hco3", "pco2", "lactate"],
}

_URINE_ROUTINE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "date":     {"type": "STRING", "nullable": True},
        "findings": {"type": "STRING", "nullable": True},
    },
    "required": ["date", "findings"],
}

_URINE_CULTURE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "date":   {"type": "STRING", "nullable": True},
        "result": {"type": "STRING", "nullable": True},
    },
    "required": ["date", "result"],
}

_OTHER_LAB_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "test":   {"type": "STRING"},
        "value":  {"type": "STRING", "nullable": True},
        "date":   {"type": "STRING", "nullable": True},
        "notes":  {"type": "STRING", "nullable": True},
    },
    "required": ["test", "value", "date", "notes"],
}

RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "cbc":              _CBC_SCHEMA,
        "biochemistry":     _BIOCHEM_SCHEMA,
        "abg":              _ABG_SCHEMA,
        "urine_routine":    _URINE_ROUTINE_SCHEMA,
        "urine_culture":    _URINE_CULTURE_SCHEMA,
        "crp":              {"type": "STRING", "nullable": True},
        "widal":            {"type": "STRING", "nullable": True},
        "echo":             {"type": "STRING", "nullable": True},
        "usg":              {"type": "STRING", "nullable": True},
        "ct_kub":           {"type": "STRING", "nullable": True},
        "other":            {"type": "ARRAY", "items": _OTHER_LAB_SCHEMA},
        "pending_results":  {"type": "ARRAY", "items": {"type": "STRING"}},
        "confidence_notes": {"type": "STRING"},
    },
    "required": [
        "cbc", "biochemistry", "abg", "urine_routine", "urine_culture",
        "crp", "widal", "echo", "usg", "ct_kub",
        "other", "pending_results", "confidence_notes",
    ],
}

SYSTEM = """You are a clinical data extractor. Extract all lab results from hospital documents.
STRICT RULES:
- NEVER invent lab values
- Include the date for each result if present
- Note any results outside reference range

Return exactly this JSON:
{
  "cbc": {"date": null or string, "hemoglobin": null or string, "wbc": null or string, "platelets": null or string, "pcv": null or string},
  "biochemistry": {"date": null or string, "creatinine": null or string, "sodium": null or string, "potassium": null or string, "rbs": null or string, "hba1c": null or string},
  "abg": {"date": null or string, "ph": null or string, "hco3": null or string, "pco2": null or string, "lactate": null or string},
  "urine_routine": {"date": null or string, "findings": null or string},
  "urine_culture": {"date": null or string, "result": null or string},
  "crp": null or string,
  "widal": null or string,
  "echo": null or string,
  "usg": null or string,
  "ct_kub": null or string,
  "other": [],
  "pending_results": [],
  "confidence_notes": string
}"""


def extract_labs(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract all lab results from:\n\n{text}",
        max_tokens=2000,
        response_schema=RESPONSE_SCHEMA,
    )
