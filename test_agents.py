"""Day 4 checks.   python test_agents.py"""
import copy

from tools.data_loader import load_data
from tools.replanner import solve_plan, draft_message
from agents.graph import build_graph, run_agents
from agents.faults import wrong_total_once, wrong_message_always

data = load_data()
ALERT = ["S2 delays P4 by 25 days"]


def run(alerts=ALERT, late=None, **kw):
    return run_agents(build_graph(data, **kw), alerts, late)


def events(state, agent=None):
    return [(e["agent"], e["event"]) for e in state["log"] if agent in (None, e["agent"])]


# ---- happy path ----
s = run()
assert s["status"] == "released" and s["attempt"] == 0
assert [e for e in events(s) if e[0] != "Replanner"] == [
    ("Planner", "alert accepted"), ("Impact Analyst", "impact found"), ("Critic", "PASS"),
    ("Human planner", "approved"), ("Planner", "released")]

# ---- exception boxes: the run ends where the diagram says ----
assert run(["S9 delays P4 by 5 days"])["status"] == "bad_alert"
assert run(["S2 delays P1 by 10 days"])["status"] == "no_impact"
assert run(["S2 delays P4 by 1 days"])["status"] == "no_shortfall"
assert run(["nonsense"])["status"] == "bad_alert"

# ---- Critic fails once, the retry fixes it ----
s = run(solver=wrong_total_once(solve_plan))
assert s["status"] == "released" and s["attempt"] == 1
assert ("Critic", "FAIL") in events(s) and ("Critic", "PASS") in events(s)
assert s["plan"]["optimized"] is True, "second solve should be the real optimized plan"

# ---- wrong message numbers: only the messages are redrafted, plan is kept ----
once = {"n": 0}


def flaky_drafter(result, impact, d, feedback=None):
    msgs = draft_message(result, impact, d, feedback=feedback)
    once["n"] += 1
    if once["n"] == 1:
        msgs = copy.deepcopy(msgs)
        msgs[0]["numbers"]["qty"] += 3
    return msgs


s = run(drafter=flaky_drafter)
assert s["status"] == "released" and s["attempt"] == 1
assert ("Replanner", "redraft") in events(s), "a messages-only failure must not re-solve the plan"

# ---- Critic keeps failing the plan: re-solve, then fall back to the baseline ----
def always_wrong_total(impact, d):
    res = copy.deepcopy(solve_plan(impact, d))
    res["claimed_total"] += 500
    return res


s = run(solver=always_wrong_total)
assert s["status"] == "released" and s["attempt"] == 2
assert ("Replanner", "fallback") in events(s) and "unoptimized" in s["plan"]["status"]

# ---- Critic never passes: escalate after 2 failed retries, with the full log ----
s = run(drafter=wrong_message_always(draft_message))
assert s["status"] == "escalated" and s["attempt"] == 2
assert sum(1 for e in events(s) if e == ("Critic", "FAIL")) == 3
assert s["reason"] and s["log"][-1]["event"] == "escalated to a human"

# ---- solver finds no plan: baseline used, marked unoptimized ----
stub = lambda impact, d: {"plan": [], "claimed_total": None, "claimed_late_orders": [], "optimized": False, "status": "Infeasible"}
s = run(solver=stub)
assert s["status"] == "released" and "unoptimized" in s["plan"]["status"]
assert ("Replanner", "no feasible plan") in events(s)

# ---- human rejects: offered the simpler plan; rejecting again repeatedly escalates ----
calls = {"n": 0}


def reject_first(state):
    calls["n"] += 1
    return ("reject", "too many rush orders") if calls["n"] == 1 else ("approve", "")


s = run(human=reject_first)
assert s["status"] == "released" and s["attempt"] == 1
assert ("Replanner", "alternative plan") in events(s) and "FCFS" in s["plan"]["status"]

# rejecting the simpler plan too leaves nothing new to offer: escalate, do not show it again
s = run(human=lambda st: ("reject", "no"))
assert s["status"] == "escalated" and s["attempt"] == 1 and s["escalated_by"] == "human"
assert events(s).count(("Human planner", "rejected")) == 2

# ---- second alert arrives mid-run ----
s = run(["S2 delays P4 by 20 days"], ["S1 delays P1 by 35 days"])
assert s["status"] == "released" and set(s["impact"]["parts"]) == {"P4", "P1"}
assert events(s).count(("Impact Analyst", "impact found")) == 2, "restarts at the Impact Analyst"
assert ("Planner", "restart at Impact Analyst") in events(s)

# a late alert that is bad is ignored, the run carries on with the first alert
s = run(["S2 delays P4 by 20 days"], ["S9 delays P1 by 35 days"])
assert s["status"] == "released" and set(s["impact"]["parts"]) == {"P4"}
assert ("Planner", "ignored late alert") in events(s)

# a late alert for the same part replaces the first one
s = run(["S2 delays P4 by 10 days"], ["S2 delays P4 by 30 days"])
assert s["alerts"] == [{"supplier_id": "S2", "part_id": "P4", "delay_days": 30}]

# a late alert is not dropped when the first alert needs no action
for first in ("S2 delays P1 by 10 days", "S2 delays P4 by 1 days"):
    s = run([first], ["S1 delays P1 by 35 days"])
    assert s["status"] == "released" and "P1" in s["impact"]["parts"], (first, s["status"])

# the Critic escalation says who escalated
s = run(drafter=wrong_message_always(draft_message))
assert s["escalated_by"] == "critic" and "rejected 3 plans" in s["log"][-1]["detail"]

# ---- the Critic sees the same plan the human is shown ----
s = run()
assert s["critic"]["verdict"] == "PASS" and s["critic"]["totals"]["total_cost"] == s["plan"]["claimed_total"]

print("all agent checks passed")
