"""Planner agent: checks the alert, sets the tasks, runs the retry loop, escalates."""
from tools.alerts import read_alerts, normalize_alerts
from agents.state import entry


def make_planner(data):
    def intake(state):
        alerts, problems = read_alerts(state["alerts_text"], data)
        if problems:
            reason = "; ".join(problems)
            return {"status": "bad_alert", "reason": reason, "log": [entry("Planner", "stop", reason)]}
        return {"alerts": alerts, "status": "working", "attempt": 0, "feedback": [], "retry_reason": "", "escalated_by": "",
                "log": [entry("Planner", "alert accepted", "; ".join(
                    f"{a['supplier_id']} delays {a['part_id']} by {a['delay_days']} days" for a in alerts))]}

    def merge(state):
        """A second alert landed mid-run: fold it in and restart at the Impact Analyst."""
        fresh, problems = read_alerts(state["late_alerts"], data)
        log = [entry("Planner", "second alert arrived", "; ".join(state["late_alerts"]))]
        if problems:
            log.append(entry("Planner", "ignored late alert", "; ".join(problems)))
        merged = normalize_alerts(state["alerts"] + fresh)
        log.append(entry("Planner", "restart at Impact Analyst", f"{len(merged)} delays now handled in one plan" if len(merged) > 1 else "1 delay to plan for"))
        return {"alerts": merged, "late_alerts": [], "attempt": 0, "feedback": [], "retry_reason": "",
                "plan": {}, "messages": [], "log": log}

    def release(state):
        return {"status": "released", "log": [entry("Planner", "released", "")]}

    def escalate(state):
        issues = "; ".join(state.get("feedback", []))[:300]
        if state.get("escalated_by") == "human":
            detail = "both plans were rejected and there is no other plan to offer"
        else:
            fails = state.get("attempt", 0) + 1
            detail = f"the Critic rejected {fails} plans in a row"
        return {"status": "escalated", "reason": issues, "log": [entry("Planner", "escalated to a human", detail)]}

    return intake, merge, release, escalate
