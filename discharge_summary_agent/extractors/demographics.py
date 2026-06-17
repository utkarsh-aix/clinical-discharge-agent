"""
extractors/demographics.py
Patient demographics extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema — mirrors the JSON template exactly.
# Gemini's responseSchema uses OpenAPI-subset types:
#   STRING | INTEGER | NUMBER | BOOLEAN | ARRAY | OBJECT
# ---------------------------------------------------------------------------
RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "patient_name":    {"type": "STRING",  "nullable": True},
        "age":             {"type": "STRING",  "nullable": True},
        "gender":          {"type": "STRING",  "nullable": True},
        "mrn":             {"type": "STRING",  "nullable": True},
        "ip_number":       {"type": "STRING",  "nullable": True},
        "blood_group":     {"type": "STRING",  "nullable": True},
        "weight_kg":       {"type": "STRING",  "nullable": True},
        "admission_date":  {"type": "STRING",  "nullable": True},
        "discharge_date":  {"type": "STRING",  "nullable": True},
        "department":      {"type": "STRING",  "nullable": True},
        "allergies":       {"type": "STRING",  "nullable": True},
        "confidence_notes":{"type": "STRING"},
    },
    "required": [
        "patient_name", "age", "gender", "mrn", "ip_number",
        "blood_group", "weight_kg", "admission_date", "discharge_date",
        "department", "allergies", "confidence_notes",
    ],
}

SYSTEM = """You are a clinical data extractor. Extract patient demographics from hospital document text.
STRICT RULES:
- NEVER invent, guess, or hallucinate any value
- If a field is absent from the text, return null - do not fill it in
- If text is partially legible, include what is readable with note [PARTIALLY LEGIBLE]
- Return ONLY valid JSON with no extra text

Return exactly this JSON:
{
  "patient_name": null or string,
  "age": null or string,
  "gender": null or string,
  "mrn": null or string,
  "ip_number": null or string,
  "blood_group": null or string,
  "weight_kg": null or string,
  "admission_date": null or string,
  "discharge_date": null or string,
  "department": null or string,
  "allergies": null or string,
  "confidence_notes": string
}"""


def extract_demographics(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract demographics from this hospital document:\n\n{text}",
        response_schema=RESPONSE_SCHEMA,
    )
