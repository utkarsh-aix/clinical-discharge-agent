from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class AgentState:
    patient_id: str
    patient_folder: str
    max_steps: int = 25

    # Document tracking
    documents_found: list = field(default_factory=list)
    documents_read: list = field(default_factory=list)
    documents_failed: list = field(default_factory=list)
    raw_text: str = ""                    # full extracted text

    # Extracted fields (None = not yet attempted, "MISSING" = tried but not found)
    demographics: Optional[dict] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    principal_diagnosis: Optional[str] = None
    secondary_diagnoses: Optional[list] = None
    hospital_course: Optional[str] = None
    procedures: Optional[list] = None
    admission_medications: Optional[list] = None
    discharge_medications: Optional[list] = None
    inpatient_medications: Optional[list] = None
    allergies: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    pending_results: Optional[list] = None
    discharge_condition: Optional[str] = None
    labs: Optional[dict] = None
    diagnoses_raw: Optional[dict] = None
    discharge_info_raw: Optional[dict] = None

    # Flags
    conflicts_detected: Optional[list] = None
    missing_fields: list = field(default_factory=list)
    flags_for_review: list = field(default_factory=list)
    medication_reconciliation: Optional[dict] = None
    drug_interactions: Optional[list] = None

    # Control
    current_step: int = 0
    iteration_history: list = field(default_factory=list)
    status: str = "running"              # running | complete | failed | max_steps_reached
    final_summary: Optional[str] = None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
