"""
extractors/discharge_info.py
Discharge information extractor with Gemini responseSchema enforcement.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Feature 5: Gemini JSON Schema
# ---------------------------------------------------------------------------
RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "discharge_condition":           {"type": "STRING", "nullable": True},
        "discharge_type":                {"type": "STRING", "nullable": True},
        "follow_up_date":                {"type": "STRING", "nullable": True},
        "follow_up_instructions":        {"type": "STRING", "nullable": True},
        "pending_results_at_discharge":  {"type": "ARRAY", "items": {"type": "STRING"}},
        "diet_advice":                   {"type": "STRING", "nullable": True},
        "special_instructions":          {"type": "STRING", "nullable": True},
        "confidence_notes":              {"type": "STRING"},
    },
    "required": [
        "discharge_condition", "discharge_type", "follow_up_date",
        "follow_up_instructions", "pending_results_at_discharge",
        "diet_advice", "special_instructions", "confidence_notes",
    ],
}

SYSTEM = """Extract discharge information from hospital documents.
STRICT RULES: NEVER invent. Return null for anything not documented.

Return exactly this JSON:
{
  "discharge_condition": null or string,
  "discharge_type": null or string,
  "follow_up_date": null or string,
  "follow_up_instructions": null or string,
  "pending_results_at_discharge": [],
  "diet_advice": null or string,
  "special_instructions": null or string,
  "confidence_notes": string
}"""


def extract_discharge_info(text: str) -> dict:
    from extractors import extract_with_llm
    return extract_with_llm(
        SYSTEM,
        f"Extract discharge info from:\n\n{text}",
        response_schema=RESPONSE_SCHEMA,
    )
