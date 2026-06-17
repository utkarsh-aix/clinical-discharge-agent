"""
extractors/procedures.py
Procedures extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema
# ---------------------------------------------------------------------------
_PROCEDURE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "name":    {"type": "STRING"},
        "date":    {"type": "STRING", "nullable": True},
        "details": {"type": "STRING", "nullable": True},
    },
    "required": ["name", "date", "details"],
}

RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "procedures":       {"type": "ARRAY", "items": _PROCEDURE_SCHEMA},
        "confidence_notes": {"type": "STRING"},
    },
    "required": ["procedures", "confidence_notes"],
}

SYSTEM = """Extract all procedures performed during hospital stay.
STRICT RULES: NEVER invent procedures. Only list what is explicitly documented.

Return exactly this JSON:
{
  "procedures": [
    {"name": string, "date": null or string, "details": null or string}
  ],
  "confidence_notes": string
}"""


def extract_procedures(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract procedures from:\n\n{text}",
        response_schema=RESPONSE_SCHEMA,
    )
