import time

MOCK_INTERACTIONS = {
    ("meropenem", "lantus"): {
        "severity": "low",
        "description": "Broad-spectrum antibiotics may affect gut flora and indirectly impact glycemic control. Monitor blood glucose closely."
    },
    ("meropenem", "actrapid"): {
        "severity": "low",
        "description": "Monitor blood glucose during antibiotic therapy - infection itself causes hyperglycemia which may resolve with treatment."
    },
    ("meropenem", "dolo"): {
        "severity": "low",
        "description": "No significant pharmacokinetic interaction. Both renally cleared - monitor renal function."
    },
    ("lantus", "actrapid"): {
        "severity": "medium",
        "description": "Concurrent basal-bolus insulin therapy. Risk of hypoglycemia if doses not carefully titrated. Requires 2-hourly GRBS monitoring."
    },
    ("pan", "dolo"): {
        "severity": "low",
        "description": "PAN (Pantoprazole) co-prescribed appropriately with Dolo to protect gastric mucosa."
    }
}


def check_drug_interactions(medication_list: list) -> list:
    print(f"[MOCK TOOL] drug_interaction_checker called with {len(medication_list)} medications")
    time.sleep(0.3)

    interactions_found = []
    meds_lower = [m.lower() if isinstance(m, str) else
                  m.get("name", "").lower() for m in medication_list]

    for (drug_a, drug_b), interaction in MOCK_INTERACTIONS.items():
        a_present = any(drug_a in med for med in meds_lower)
        b_present = any(drug_b in med for med in meds_lower)
        if a_present and b_present:
            interactions_found.append({
                "drug_a": drug_a,
                "drug_b": drug_b,
                **interaction
            })

    return interactions_found
