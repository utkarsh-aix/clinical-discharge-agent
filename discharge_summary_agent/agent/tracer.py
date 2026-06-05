from rich.console import Console
from rich.panel import Panel
from rich.text import Text
import json
from datetime import datetime

console = Console()


class Tracer:
    def __init__(self, state):
        self.state = state

    def log_step(self, reasoning: str, tool_chosen: str,
                 inputs: dict, result: dict, next_decision: str):

        step_num = self.state.current_step + 1

        step_record = {
            "step": step_num,
            "timestamp": datetime.now().isoformat(),
            "reasoning": reasoning,
            "tool_chosen": tool_chosen,
            "inputs_summary": str(inputs)[:200],
            "result_summary": str(result)[:300],
            "next_decision": next_decision
        }
        self.state.iteration_history.append(step_record)

        # Rich console output
        console.print(f"\n[bold cyan]═══ STEP {step_num} / {self.state.max_steps} ═══[/bold cyan]")
        console.print(f"[yellow]REASONING:[/yellow] {reasoning}")
        console.print(f"[green]TOOL:[/green] {tool_chosen}")

        if "error" in result:
            console.print(f"[red]RESULT:[/red] ERROR - {result.get('error')}")
        elif "conflict" in tool_chosen.lower() or "flag" in tool_chosen.lower():
            console.print(f"[red bold]RESULT:[/red bold] {str(result)[:200]}")
        else:
            console.print(f"[white]RESULT:[/white] {str(result)[:200]}")

        console.print(f"[blue]NEXT:[/blue] {next_decision}")

    def export_trace(self, output_path: str):
        with open(output_path, "w") as f:
            json.dump({
                "patient_id": self.state.patient_id,
                "status": self.state.status,
                "total_steps": self.state.current_step,
                "conflicts_found": len(self.state.conflicts_detected or []),
                "flags_raised": len(self.state.flags_for_review or []),
                "missing_fields": self.state.missing_fields,
                "steps": self.state.iteration_history
            }, f, indent=2)
        console.print(f"\n[green]Trace saved to: {output_path}[/green]")
