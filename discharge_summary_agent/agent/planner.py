"""
Planner — state-machine based planning for the discharge summary agent.

Design Decision:
  The planner uses a deterministic state-machine approach (implemented in
  DischargeAgent.plan() inside agent/loop.py) rather than an LLM-based
  dynamic planner. This is intentional for a clinical context where:

    - Reliability and reproducibility matter more than flexibility.
      Every run on the same patient data must produce the same extraction
      order, making audits and debugging straightforward.

    - The extraction pipeline has a well-defined set of steps with clear
      dependencies (e.g. medication reconciliation requires medications to
      be extracted first; conflict detection is more useful after
      reconciliation so it can surface stopped-medication conflicts).

    - An LLM planner would add non-determinism and extra API calls with
      no clinical benefit for a fixed, well-understood workflow.

  DischargeAgent.plan() IS the planner — it inspects the AgentState after
  every tool execution and routes to the next appropriate tool based on
  which state fields are still None (not yet attempted).
"""

# Canonical execution order used by DischargeAgent.plan()
EXTRACTION_ORDER = [
    "read_pdfs",
    "extract_demographics",
    "extract_diagnoses",
    "extract_medications",
    "extract_labs",
    "extract_procedures",
    "extract_discharge_info",
    "extract_hospital_course",
    "reconcile_medications",
    "detect_conflicts",
    "check_drug_interactions",
    "escalate_conflicts",
    "build_summary",
    "verify_summary",
]

