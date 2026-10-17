"""One or more alerts through every tool, no agents.

Useful for Day 3 numbers. Day 4's LangGraph run does the same work, plus the
retry loop, the human step, and a second alert arriving mid-run.
"""
from tools.alerts import read_alerts
from tools.impact import analyse_impact
from tools.replanner import solve_plan, fcfs_baseline, draft_message
from tools.critic import review, recompute_cost


def run_alert(texts, data, solver=solve_plan):
    texts = [texts] if isinstance(texts, str) else list(texts)
    alerts, problems = read_alerts(texts, data)
    if problems:
        return {"status": "bad_alert", "reason": "; ".join(problems)}

    impact = analyse_impact(data, alerts)
    if not impact["parts"]:
        return {"status": "no_impact", "alerts": alerts, "reason": "The part affects no open orders", "impact": impact}
    if impact["shortfall_total"] == 0:
        return {"status": "no_shortfall", "alerts": alerts, "impact": impact,
                "reason": "Stock and the delayed shipment still meet every due date"}

    baseline = fcfs_baseline(impact, data)
    chosen = solver(impact, data)
    note = None
    if not chosen["optimized"]:                      # no feasible plan: fall back and say so
        chosen = {**baseline, "status": f"unoptimized (solver said {chosen['status']})"}
        note = "Solver found no plan, baseline used and marked unoptimized"
    messages = draft_message(chosen, impact, data)
    verdict = review(chosen, messages, data, alerts)
    return {"status": "ok", "alerts": alerts, "impact": impact, "plan": chosen, "baseline": baseline,
            "baseline_totals": recompute_cost(baseline["plan"], data, alerts),
            "messages": messages, "critic": verdict, "note": note}
