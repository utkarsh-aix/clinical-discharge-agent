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
    return extract_with_llm(SYSTEM, f"Extract discharge info from:\n\n{text}")
