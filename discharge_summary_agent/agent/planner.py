"""
Planner — decides which tools and extractors to invoke at each step,
using the Groq LLM to reason over the current agent state.
"""

from groq import Groq


class Planner:
    """LLM-backed planner that generates the next action for the agent loop."""

    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def plan_next_step(self, state_summary: str) -> dict:
        """
        Given a summary of the current agent state, decide the next action.

        Args:
            state_summary: A text description of what has been done so far.

        Returns:
            A dict with keys 'action' and optional 'params'.
        """
        # TODO: Implement LLM-based planning
        raise NotImplementedError("Planner.plan_next_step not yet implemented")

    def decide_extraction_order(self, available_pages: list[str]) -> list[str]:
        """
        Decide which extractors to run and in what order.

        Args:
            available_pages: List of text content from each PDF page.

        Returns:
            Ordered list of extractor names to invoke.
        """
        # Default extraction order
        return [
            "demographics",
            "diagnoses",
            "medications",
            "labs",
            "procedures",
            "discharge_info",
        ]
