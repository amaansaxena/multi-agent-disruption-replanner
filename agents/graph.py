"""Wire the four agents into one LangGraph workflow.

    intake -> impact -> replanner -> (late alert? merge -> impact) -> critic
    impact -> merge, when there is nothing to plan yet but a late alert is waiting
    critic  -> human (pass) | replanner (fail, retries left) | escalate
    human   -> release (approve) | replanner (reject, retries left) | escalate
"""
from langgraph.graph import StateGraph, START, END

from tools.replanner import solve_plan, draft_message
from agents.state import RunState
from agents.planner import make_planner
from agents.impact_analyst import make_impact_analyst
from agents.replanner import make_replanner
from agents.critic import make_critic
from agents.human import make_human, auto_approve


def _after_impact(s):
    """Plan if there is work. If not, a second alert that is still waiting must
    not be dropped: fold it in first, and only stop if there is truly nothing."""
    if s["status"] == "working":
        return "replanner"
    return "merge" if s.get("late_alerts") else END


def build_graph(data, solver=solve_plan, drafter=draft_message, human=auto_approve):
    intake, merge, release, escalate = make_planner(data)
    g = StateGraph(RunState)
    g.add_node("intake", intake)
    g.add_node("impact", make_impact_analyst(data))
    g.add_node("replanner", make_replanner(data, solver, drafter))
    g.add_node("merge", merge)
    g.add_node("critic", make_critic(data))
    g.add_node("human", make_human(human))
    g.add_node("release", release)
    g.add_node("escalate", escalate)

    g.add_edge(START, "intake")
    g.add_conditional_edges("intake", lambda s: END if s["status"] == "bad_alert" else "impact")
    g.add_conditional_edges("impact", _after_impact)
    g.add_conditional_edges("replanner", lambda s: "merge" if s.get("late_alerts") else "critic")
    g.add_edge("merge", "impact")
    g.add_conditional_edges("critic", lambda s: s["next"])
    g.add_conditional_edges("human", lambda s: END if s["next"] == "pending" else s["next"])
    g.add_edge("release", END)
    g.add_edge("escalate", END)
    return g.compile()


def run_agents(graph, alerts, late_alerts=None):
    """Run one case. `late_alerts` arrive after the Replanner's first pass."""
    start = {"alerts_text": list(alerts), "late_alerts": list(late_alerts or []), "log": []}
    return graph.invoke(start, config={"recursion_limit": 60})
