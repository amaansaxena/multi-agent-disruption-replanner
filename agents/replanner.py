"""Replanner agent: solve for the cheapest plan, then draft the messages.

On a retry it reacts to what went wrong:
  plan       re-solve once, then fall back to the first-come-first-served plan
  messages   keep the plan, just redraft the messages
  human      the person rejected the plan, so offer the simpler FCFS plan instead
"""
from config import MAX_RETRIES
from tools.replanner import fcfs_baseline
from tools.critic import recompute_cost
from agents.state import entry


def make_replanner(data, solver, drafter):
    def node(state):
        impact, alerts = state["impact"], state["alerts"]
        attempt, reason = state.get("attempt", 0), state.get("retry_reason", "")
        baseline = fcfs_baseline(impact, data)
        log = []

        if attempt > 0 and reason == "messages" and state.get("plan"):
            plan = state["plan"]
            log.append(entry("Replanner", "redraft", "the plan was fine, only the messages were wrong"))
        elif reason == "human":
            plan = {**baseline, "status": "FCFS plan offered after the human rejected the optimized one"}
            log.append(entry("Replanner", "alternative plan", "the person rejected the optimized plan"))
        elif attempt >= MAX_RETRIES and reason == "plan":
            plan = {**baseline, "status": "unoptimized (fallback after failed re-plans)"}
            log.append(entry("Replanner", "fallback", "the optimized plan failed the checks twice"))
        else:
            plan = solver(impact, data)
            if plan["optimized"]:
                log.append(entry("Replanner", "plan solved", f"it costs {plan['claimed_total']:,.0f}"))
            else:
                log.append(entry("Replanner", "no feasible plan", "the solver found no plan, so the manual fix is used instead"))
                plan = {**baseline, "status": f"unoptimized (solver said {plan['status']})"}

        messages = drafter(plan, impact, data, feedback=state.get("feedback") or None)
        log.append(entry("Replanner", "messages drafted", f"{len(messages)} message" + ("" if len(messages) == 1 else "s")))
        return {"plan": plan, "baseline": baseline, "messages": messages,
                "baseline_totals": recompute_cost(baseline["plan"], data, alerts), "log": log}
    return node
