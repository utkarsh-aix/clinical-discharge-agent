"""
agent/evaluate.py — Phase 2 Evaluation Loop

Runs the learning loop efficiently by REUSING existing summary files
rather than re-running the full agent each time. This avoids hitting
API quota limits during evaluation.

The learning loop works as follows:
  Iteration 0: Original draft (no correction rules) → reviewer edits → measure NED
  Iteration 1: Apply 1 round of learned rules to draft → reviewer edits → measure NED
  Iteration 2: Apply 2 rounds of learned rules → reviewer edits → measure NED

This simulates what would happen over multiple real-world patient runs
without exhausting the API quota.

Outputs:
  - outputs/evaluation_report.json   — full per-patient per-iteration scores
  - outputs/improvement_curve.png    — line chart showing NED falling

Usage:
  python3 agent/evaluate.py
  python3 agent/evaluate.py --patients patient_1 patient_2 --iterations 3
"""

import os
import sys
import json
import re
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.reviewer import apply_doctor_edits, get_edit_pairs
from agent.feedback import score_draft, normalized_edit_distance
from agent.correction_memory import (
    record_corrections,
    get_confirmed_rule_count,
    get_prompt_injection,
    _load_memory,
    _save_memory,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _clear_memory():
    for f in ["outputs/correction_memory.json", "outputs/feedback_log.json"]:
        if os.path.exists(f):
            os.remove(f)


def _load_summary(patient_id: str) -> str | None:
    path = f"outputs/{patient_id}_discharge_summary.txt"
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return None


def _apply_memory_rules_to_draft(draft: str) -> str:
    """
    Simulate what the LLM would produce IF it had the correction rules
    injected into its prompt. We apply the confirmed rules directly to
    the text as a stand-in for prompt-based learning.
    """
    memory = _load_memory()
    confirmed = [r for r in memory if r.get("confirmed", False)]
    confirmed.sort(key=lambda r: r["count"], reverse=True)

    improved = draft
    for rule in confirmed[:8]:
        orig = re.escape(rule["original"].strip())
        corr = rule["corrected"].strip()
        try:
            improved = re.sub(orig, corr, improved)
        except re.error:
            pass  # Skip rules with problematic regex chars

    return improved


# ─── Main Evaluation ─────────────────────────────────────────────────────────

def run_evaluation(
    patients: list[tuple[str, str]],
    iterations: int = 3,
    clear_memory: bool = True,
) -> dict:
    """
    Run the before/after evaluation loop using pre-generated summaries.
    No additional API calls are made.
    """
    if clear_memory:
        _clear_memory()

    # Verify all summaries exist
    summaries = {}
    for patient_id, _ in patients:
        text = _load_summary(patient_id)
        if not text:
            print(f"  ⚠️  No summary found for {patient_id}. Run the agent first:")
            print(f"     python3 main.py --patient-folder patients/{patient_id} --patient-id {patient_id}")
            return {}
        summaries[patient_id] = text
        print(f"  ✅ Loaded summary for {patient_id} ({len(text):,} chars)")

    results = {
        "iterations": iterations,
        "patients": [p[0] for p in patients],
        "per_iteration": [],
        "summary": []
    }

    print()
    for iteration in range(iterations):
        print(f"{'='*60}")
        print(f"  ITERATION {iteration} / {iterations - 1}")
        confirmed = get_confirmed_rule_count()
        print(f"  Confirmed correction rules in memory: {confirmed}")
        print(f"{'='*60}")

        iteration_scores = {
            "iteration": iteration,
            "confirmed_rules_in_memory": confirmed,
            "patient_scores": []
        }

        for patient_id, _ in patients:
            original_draft = summaries[patient_id]

            # Iteration 0: raw draft. Iteration 1+: apply learned rules
            if iteration == 0:
                draft = original_draft
            else:
                draft = _apply_memory_rules_to_draft(original_draft)

            # Apply simulated doctor edits
            edited = apply_doctor_edits(draft)

            # Score
            score = score_draft(draft, edited, patient_id, iteration)
            ned = score["normalized_edit_distance"]
            smr = score["section_match_rate"]
            print(f"\n  {patient_id}:")
            print(f"    NED = {ned:.4f}  |  SMR = {smr:.4f}  |  Rules in memory: {confirmed}")

            iteration_scores["patient_scores"].append({
                "patient_id": patient_id,
                "ned": ned,
                "smr": smr,
                "sections": score["sections"],
            })

            # Feed corrections into memory
            pairs = get_edit_pairs(draft)
            record_corrections(pairs)
            new_confirmed = get_confirmed_rule_count()
            if new_confirmed > confirmed:
                print(f"    📚 {new_confirmed - confirmed} new confirmed rule(s) added!")
                confirmed = new_confirmed

        results["per_iteration"].append(iteration_scores)

    # ─── Build summary ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  EVALUATION SUMMARY")
    print(f"{'='*60}")

    for patient_id, _ in patients:
        ned_vals = []
        smr_vals = []
        for it in results["per_iteration"]:
            for ps in it["patient_scores"]:
                if ps["patient_id"] == patient_id:
                    ned_vals.append(ps["ned"])
                    smr_vals.append(ps["smr"])

        if ned_vals:
            improvement = round(
                (ned_vals[0] - ned_vals[-1]) / max(ned_vals[0], 0.0001) * 100, 1
            )
            print(f"\n  {patient_id}:")
            for i, (ned, smr) in enumerate(zip(ned_vals, smr_vals)):
                arrow = "  (baseline)" if i == 0 else f"  (↓{round((ned_vals[0]-ned)/max(ned_vals[0],0.0001)*100,1)}% from baseline)"
                print(f"    Iteration {i}: NED={ned:.4f}  SMR={smr:.4f}{arrow}")
            print(f"  → Total improvement: {improvement}% reduction in edit distance")

            results["summary"].append({
                "patient_id": patient_id,
                "ned_per_iteration": ned_vals,
                "smr_per_iteration": smr_vals,
                "improvement_pct": improvement,
            })

    # ─── Save & plot ─────────────────────────────────────────────────────────
    os.makedirs("outputs", exist_ok=True)
    report_path = "outputs/evaluation_report.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  📄 Report saved to {report_path}")

    _plot_improvement_curve(results)
    return results


def _plot_improvement_curve(results: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  ⚠️  matplotlib not installed. Run: pip install matplotlib")
        return

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
    fig.patch.set_facecolor("#f4f7fa")
    for ax in (ax1, ax2):
        ax.set_facecolor("#ffffff")

    colors = ["#5289b5", "#e28a1c", "#2b8a6a", "#d9383a"]
    iter_labels = [f"Iter {i}" for i in range(results["iterations"])]

    for idx, entry in enumerate(results["summary"]):
        c = colors[idx % len(colors)]
        label = f"{entry['patient_id']} (↓{entry['improvement_pct']}%)"
        ned_vals = entry["ned_per_iteration"]
        smr_vals = entry.get("smr_per_iteration", [])

        # NED plot
        ax1.plot(iter_labels[:len(ned_vals)], ned_vals, marker="o",
                 linewidth=2.5, markersize=8, color=c, label=label)
        for i, v in enumerate(ned_vals):
            ax1.annotate(f"{v:.3f}", (iter_labels[i], v),
                         textcoords="offset points", xytext=(0, 10),
                         ha="center", fontsize=9, color=c)

        # SMR plot
        if smr_vals:
            ax2.plot(iter_labels[:len(smr_vals)], smr_vals, marker="s",
                     linewidth=2.5, markersize=8, color=c,
                     linestyle="--", label=entry["patient_id"])
            for i, v in enumerate(smr_vals):
                ax2.annotate(f"{v:.2f}", (iter_labels[i], v),
                             textcoords="offset points", xytext=(0, 10),
                             ha="center", fontsize=9, color=c)

    ax1.set_title("Edit Distance (NED) — Lower is Better", fontsize=13, fontweight="bold", pad=14)
    ax1.set_ylabel("Normalized Edit Distance", fontsize=11)
    ax1.set_xlabel("Learning Iteration", fontsize=11)
    ax1.legend(fontsize=10)
    ax1.grid(axis="y", alpha=0.3, linestyle="--")
    ax1.set_ylim(bottom=0)

    ax2.set_title("Section Match Rate (SMR) — Higher is Better", fontsize=13, fontweight="bold", pad=14)
    ax2.set_ylabel("Section Match Rate", fontsize=11)
    ax2.set_xlabel("Learning Iteration", fontsize=11)
    ax2.legend(fontsize=10)
    ax2.grid(axis="y", alpha=0.3, linestyle="--")
    ax2.set_ylim(0, 1.05)

    plt.suptitle("Phase 2: Learning from Doctor Edits — Improvement Curve",
                 fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    out = "outputs/improvement_curve.png"
    plt.savefig(out, dpi=140, bbox_inches="tight")
    plt.close()
    print(f"  📊 Improvement curve saved to {out}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 2 — Learning Evaluation Loop")
    parser.add_argument("--patients", nargs="+", default=["patient_1", "patient_2"])
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--keep-memory", action="store_true")
    args = parser.parse_args()

    run_evaluation(
        patients=[(pid, f"patients/{pid}") for pid in args.patients],
        iterations=args.iterations,
        clear_memory=not args.keep_memory,
    )
