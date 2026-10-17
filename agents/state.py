"""The one shared state every agent reads and writes."""
import operator
from typing import Annotated, TypedDict


class RunState(TypedDict, total=False):
    alerts_text: list        # raw alert texts the run started with
    late_alerts: list        # raw alert texts that arrive mid-run
    alerts: list             # parsed, validated, merged alerts
    status: str              # working, bad_alert, no_impact, no_shortfall, released, escalated
    reason: str
    impact: dict
    plan: dict
    baseline: dict
    baseline_totals: dict
    messages: list
    critic: dict
    attempt: int             # re-plans used so far
    feedback: list           # the Critic's (or human's) latest issues
    retry_reason: str        # plan, messages or human: tells the Replanner what to change
    next: str                # where the Critic or human step sends the run next
    escalated_by: str        # "critic" or "human": who sent the case to a person
    log: Annotated[list, operator.add]


def entry(agent, event, detail=""):
    return {"agent": agent, "event": event, "detail": detail}
