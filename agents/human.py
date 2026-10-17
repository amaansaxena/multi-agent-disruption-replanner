"""The human planner's step. `decide(state)` returns ("approve" | "reject" | "pending", note)."""
from config import MAX_RETRIES
from agents.state import entry


def auto_approve(state):
    return "approve", ""


def make_human(decide):
    def node(state):
        decision, note = decide(state)
        if decision == "pending":      # the app is showing the plan and waiting for a click
            return {"next": "pending", "status": "awaiting_approval",
                    "log": [entry("Human planner", "waiting", "")]}
        if decision == "approve":
            return {"next": "release", "log": [entry("Human planner", "approved", note)]}
        log = [entry("Human planner", "rejected", note or "no reason given")]
        # Only the optimized plan has an alternative (the first-come-first-served
        # plan). Rejecting that alternative too leaves nothing new to offer, so
        # the case goes to a person instead of showing the same plan again.
        if state.get("plan", {}).get("optimized") and state.get("attempt", 0) < MAX_RETRIES:
            return {"next": "replanner", "feedback": [f"human rejected the plan: {note}"], "retry_reason": "human",
                    "attempt": state.get("attempt", 0) + 1, "log": log}
        return {"next": "escalate", "feedback": [f"human rejected the plan: {note}"], "escalated_by": "human", "log": log}
    return node
