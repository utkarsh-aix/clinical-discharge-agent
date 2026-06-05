from datetime import datetime
import time

escalation_log = []


def flag_for_clinician_review(reason: str, severity: str, details: dict) -> dict:
    """Mock escalation tool."""
    print(f"[MOCK TOOL] escalation called: [{severity.upper()}] {reason}")
    time.sleep(0.2)

    escalation_id = f"ESC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    record = {
        "flagged": True,
        "escalation_id": escalation_id,
        "reason": reason,
        "severity": severity,
        "details": details,
        "timestamp": datetime.now().isoformat()
    }
    escalation_log.append(record)
    return record
