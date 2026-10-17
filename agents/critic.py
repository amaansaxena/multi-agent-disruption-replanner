"""Critic agent: recompute from raw data, check R1 to R5, send the run on."""
from config import MAX_RETRIES
from tools.critic import review
from agents.state import entry


def make_critic(data):
    def node(state):
        v = review(state["plan"], state["messages"], data, state["alerts"])
        failed = [r for r, x in v["rules"].items() if not x["ok"]]
        if v["verdict"] == "PASS":
            return {"critic": v, "next": "human", "feedback": [],
                    "log": [entry("Critic", "PASS", "all five checks passed")]}
        reason = "plan" if any(r in failed for r in ("R1", "R2", "R3", "R4")) else "messages"
        log = [entry("Critic", "FAIL", v["issues"][0] + (f" (and {len(v['issues']) - 1} more)" if len(v["issues"]) > 1 else ""))]
        if state.get("attempt", 0) < MAX_RETRIES:
            return {"critic": v, "next": "replanner", "feedback": v["issues"], "retry_reason": reason,
                    "attempt": state.get("attempt", 0) + 1, "log": log}
        return {"critic": v, "next": "escalate", "feedback": v["issues"], "escalated_by": "critic", "log": log}
    return node
