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
    return extract_with_llm(SYSTEM, f"Extract procedures from:\n\n{text}")
