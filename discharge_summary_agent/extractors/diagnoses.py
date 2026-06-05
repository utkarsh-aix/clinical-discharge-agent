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
    return extract_with_llm(SYSTEM, f"Extract all diagnoses from:\n\n{text}", max_tokens=2000)
