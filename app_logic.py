"""Everything the Streamlit app needs that is not layout. Testable without Streamlit.

The app shows three ways of handling a delay side by side, and all three are
priced the same way, by the Critic's own recompute_cost():
  nobody acts     stock goes out by due date, everything else waits for the late shipment
  manual fix      what a busy planner would do by hand: orders by due date, first option that works
  optimized plan  the cheapest plan the solver finds
"""
import json
import os
import statistics
from html import escape

from config import STOCK
from tools.alerts import parse_alert, AlertError
from tools.replanner import solve_plan, draft_message, build_options
from tools.critic import recompute_cost
from agents.graph import build_graph, run_agents
from agents.faults import apply_fault
from data.generate_data import PARTS, SUPPLIER_NAMES

HERE = os.path.dirname(os.path.abspath(__file__))

FAULTS = {"No planted mistake": None,
          "The solver reports a wrong total on its first try": "wrong_total_once",
          "Supplier messages always quote one unit too many": "wrong_message_always"}

RULE_TEXT = {"R1": "Never uses more stock than is on the shelf",
             "R2": "Never asks a supplier for more than they can make",
             "R3": "Every affected order gets all the parts it needs",
             "R4": "The reported cost matches a fresh recalculation",
             "R5": "Every number in every message matches the plan"}

PART_NAME = {pid: v[0] for pid, v in PARTS.items()}

COLOR = {"ink": "#1C2830", "steel": "#3E6A8A", "steel_light": "#A9BCCB", "signal": "#F2B705",
         "late": "#C23B22", "ok": "#2E7D5B", "rule": "#D3D9D5", "faint": "#E7EBE8", "muted": "#66737C"}

CATEGORY = {"normal": ("Ordinary delays", "a plan was made and approved"),
            "second_alert": ("A second delay arrives during planning", "both delays handled in one plan"),
            "no_shortfall": ("Delay too short to matter", "correctly left alone"),
            "no_impact": ("Alert about a backup supplier", "correctly left alone"),
            "bad_alert": ("Alerts with a mistake in them", "rejected before any planning"),
            "fault": ("Planted mistakes", "caught by the Critic")}

OUTCOME = {"released": "a plan is approved", "escalated": "handed to a person", "bad_alert": "alert rejected",
           "no_impact": "no action needed", "no_shortfall": "no action needed",
           "awaiting_approval": "waiting for a decision", "critic_fail": "failed the checks"}

MANUAL_EXPLAINED = ("The manual fix is what a busy planner would do by hand: go through the orders by due date "
                    "and, for each one, take the first option that covers it in time.")


def money(x):
    return f"{x:,.0f}"


def plural(n, word, many=None):
    return f"{n} {word if n == 1 else (many or word + 's')}"


# ---------------------------------------------------------------- running the agents

def load_scenarios():
    with open(os.path.join(HERE, "scenarios", "scenarios.json")) as f:
        return json.load(f)


def execute(data, alerts, late_alerts, fault, decisions):
    """Run the four agents. `decisions` is the human's clicks so far, e.g. [("reject", "too costly")].

    With no more clicks left the run stops at 'awaiting_approval'. Replaying the
    earlier clicks each time is cheap here and keeps the app stateless.
    """
    solver, drafter = apply_fault(fault, solve_plan, draft_message)
    calls = {"n": 0}

    def human(state):
        i = calls["n"]
        calls["n"] += 1
        return decisions[i] if i < len(decisions) else ("pending", "")

    graph = build_graph(data, solver=solver, drafter=drafter, human=human)
    return run_agents(graph, alerts, late_alerts)


# ---------------------------------------------------------------- labels

def supplier_name(sid):
    return SUPPLIER_NAMES.get(sid, sid)


def part_name(pid):
    return PART_NAME.get(pid, pid)


def supplier_label(sid):
    return f"{supplier_name(sid)} ({sid})"


def part_label(pid):
    return f"{part_name(pid)} ({pid})"


def describe_alert(text):
    """'S2 delays P4 by 25 days' -> 'Brightline Electronics is 25 days late with the wiring harness'."""
    try:
        a = parse_alert(text)
    except AlertError:
        return text
    if a["supplier_id"] not in SUPPLIER_NAMES or a["part_id"] not in PART_NAME:
        return text
    return (f"{supplier_name(a['supplier_id'])} is {plural(a['delay_days'], 'day')} late with "
            f"the {part_name(a['part_id']).lower()}")


def parts_supplied_by(data, sid):
    """Parts this supplier is the main source for. Only these make a real disruption."""
    s = data["suppliers"]
    return sorted(s[(s.supplier_id == sid) & (s.is_primary)].part_id)


def is_main_supplier(data, sid, pid):
    return pid in parts_supplied_by(data, sid)


# ---------------------------------------------------------------- what kind of plan is on the table

def has_plan(state):
    return bool(state) and state["status"] in ("awaiting_approval", "released", "escalated") and bool(state.get("plan"))


def plan_kind(state):
    """optimized, manual (offered after the person rejected the optimized one) or fallback."""
    plan = state.get("plan") or {}
    if not plan:
        return None
    if plan.get("optimized"):
        return "optimized"
    return "manual" if "FCFS plan offered" in plan.get("status", "") else "fallback"


def do_nothing_rows(impact):
    """The plan nobody made: stock by due date, the rest waits for the late shipment."""
    rows = []
    for pid, rep in impact["parts"].items():
        for o in rep["orders"]:
            if o["stock_default"]:
                rows.append({"order_id": o["order_id"], "part_id": pid, "supplier_id": STOCK,
                             "mode": "stock", "qty": o["stock_default"]})
            if o["incoming_default"]:
                rows.append({"order_id": o["order_id"], "part_id": pid, "supplier_id": rep["supplier_id"],
                             "mode": "wait", "qty": o["incoming_default"]})
    return rows


def compare(state, data):
    """The three options, priced the same way. Returns a list of dicts, plus which one is on the table."""
    alerts, impact = state["alerts"], state["impact"]
    kind = plan_kind(state)
    optimized_rows = state["plan"]["plan"] if kind == "optimized" else solve_plan(impact, data)["plan"]
    options = [("nothing", "If nobody acts", do_nothing_rows(impact)),
               ("manual", "Manual fix", state["baseline"]["plan"]),
               ("optimized", "Optimized plan", optimized_rows)]
    out = []
    for key, label, rows in options:
        t = recompute_cost(rows, data, alerts)
        out.append({"key": key, "label": label, "rows": rows, "total": t["total_cost"],
                    "purchase": t["purchase_cost"], "penalty": t["penalty_cost"],
                    "late": t["late_orders"], "arrivals": t["arrivals"]})
    on_table = "optimized" if kind == "optimized" else "manual"
    return {"options": out, "on_table": on_table, "by_key": {o["key"]: o for o in out}}


def nothing_only(state, data):
    """Same shape as compare(), with only the do-nothing option. For cases with no plan."""
    t = recompute_cost(do_nothing_rows(state["impact"]), data, state["alerts"])
    o = {"key": "nothing", "label": "If nobody acts", "total": t["total_cost"], "purchase": t["purchase_cost"],
         "penalty": t["penalty_cost"], "late": t["late_orders"], "arrivals": t["arrivals"]}
    return {"options": [o], "on_table": "nothing", "by_key": {"nothing": o}}


# ---------------------------------------------------------------- headline and summary

def verdict(state):
    """(headline, tone). Tone is ok, wait, stop or quiet."""
    s = state["status"]
    if s == "awaiting_approval":
        return {"manual": "The manual fix is ready for your decision",
                "fallback": "The optimized plan failed its checks, so the manual fix is ready instead"}.get(
                    plan_kind(state), "A recovery plan is ready for your decision"), "wait"
    if s == "released":
        return "Plan approved. The messages are ready to send", "ok"
    if s == "escalated":
        if state.get("escalated_by") == "human":
            return "Both plans were rejected, so this goes to a person", "stop"
        return "The Critic kept finding mistakes, so this goes to a person", "stop"
    if s == "bad_alert":
        return "This alert could not be used", "stop"
    if s == "no_impact":
        return "No action needed: no open order depends on this delay", "quiet"
    if s == "no_shortfall":
        return "No action needed: every order still ships on time", "quiet"
    return s.replace("_", " ").capitalize(), "quiet"


def _what_happened(state):
    return " and ".join(f"{supplier_name(p['supplier_id'])} is {plural(p['delay_days'], 'day')} late with "
                        f"the {part_name(pid).lower()}" for pid, p in state["impact"]["parts"].items())


def summary(state, data, cmp=None):
    """A short paragraph in plain words. Every number in it comes from a recalculation."""
    s = state["status"]
    if s == "bad_alert":
        return f"{state['reason']}. Check the supplier, the part and the number of days, then run it again."
    if s == "no_impact":
        a = state["alerts"][0]
        if not is_main_supplier(data, a["supplier_id"], a["part_id"]):
            return (f"{supplier_name(a['supplier_id'])} is only a backup source for the {part_name(a['part_id']).lower()}. "
                    "We have nothing on order from them, so their delay changes nothing.")
        return f"No open order uses the {part_name(a['part_id']).lower()}, so the delay changes nothing."
    if s == "no_shortfall":
        return ("Stock on hand covers the earliest orders and the delayed shipment still lands before the "
                "rest are due. Nothing needs to change.")

    imp = state["impact"]
    cmp = cmp or compare(state, data)
    opt, man = cmp["by_key"]["optimized"], cmp["by_key"]["manual"]
    n = len(imp["orders_at_risk"])
    text = [f"{_what_happened(state)}.",
            f"If nobody acts, {plural(n, 'order')} ship late and the late penalties come to {money(imp['penalty_if_nothing_done'])}."]

    kind = plan_kind(state)
    if s == "escalated" and state.get("escalated_by") == "human":
        text.append(f"You turned down both the optimized plan, at {money(opt['total'])}, and the "
                    f"manual fix, at {money(man['total'])}. Nothing was approved.")
        return " ".join(text)
    if kind == "optimized":
        saving = man["total"] - opt["total"]
        if saving > 0.5:
            text.append(f"The optimized plan costs {money(opt['total'])} in parts and penalties. That is "
                        f"{money(saving)} ({saving / man['total']:.0%}) less than the manual fix.")
        else:
            text.append(f"The optimized plan costs {money(opt['total'])}, the same as the manual fix.")
        shown = opt
    else:
        extra = man["total"] - opt["total"]
        lead = ("You rejected the optimized plan, so this is the manual fix instead."
                if kind == "manual" else
                "The optimized plan did not pass the Critic's checks, so this is the manual fix instead.")
        text.append(f"{lead} It costs {money(man['total'])}"
                    + (f", {money(extra)} more than the optimized plan." if extra > 0.5 else ", the same as the optimized plan."))
        shown = man

    late = len(shown["late"])
    if late == 0:
        text.append("Every order ships on time.")
    elif kind == "optimized":
        text.append(f"{plural(late, 'order')} still {'ships' if late == 1 else 'ship'} late. Getting "
                    f"{'it' if late == 1 else 'them'} out on time would either cost more than the late penalties "
                    "or need more parts than the backup suppliers can make.")
    else:
        text.append(f"{plural(late, 'order')} still {'ships' if late == 1 else 'ship'} late.")
    return " ".join(text)


def next_step(state):
    s, kind = state["status"], plan_kind(state)
    if s == "awaiting_approval":
        if kind == "optimized":
            return "Nothing is sent until you approve. If you reject it, you will be offered the manual fix instead."
        return "If you reject this one too, the case goes to a person, because there is no other plan to offer."
    if s == "released":
        return "The supplier and customer messages are under What to send."
    if s == "escalated":
        if state.get("escalated_by") == "human":
            return "Nothing was sent. The full agent log is under How the agents worked."
        issues = (state.get("critic") or {}).get("issues") or [""]
        problem = PROBLEM_TEXT.get(issues[0].split(":")[0])
        tries = state.get("attempt", 0) + 1
        return (f"Nothing was sent. The Critic rejected the plan {tries} times in a row, and each time "
                + problem + ". The details are under How the agents worked." if problem else "Nothing was sent.")
    return ""


PROBLEM_TEXT = {"R1": "it used more stock than is on the shelf",
                "R2": "it asked a supplier for more than they can make",
                "R3": "some order was not fully covered",
                "R4": "its reported cost did not match a fresh recalculation",
                "R5": "a message quoted a number that is not in the plan"}


# ---------------------------------------------------------------- the plan as actions

MODE_WORD = {"stock": "From stock", "alternate": "Backup supplier", "expedite": "Rush order", "wait": "Late shipment"}


# The agents' log is written for the code and the tests. These turn it into plain sentences.
EVENT_TEXT = {
    ("Planner", "alert accepted"): "accepted the alert", ("Planner", "stop"): "could not use the alert",
    ("Planner", "second alert arrived"): "received a second alert",
    ("Planner", "ignored late alert"): "ignored the second alert because it could not be used",
    ("Planner", "restart at Impact Analyst"): "sent the work back to the Impact Analyst",
    ("Planner", "released"): "released the plan and the messages",
    ("Planner", "escalated to a human"): "handed the case to a person",
    ("Impact Analyst", "impact found"): "checked the orders", ("Impact Analyst", "no impact"): "checked the orders",
    ("Impact Analyst", "no shortfall"): "checked the orders",
    ("Replanner", "plan solved"): "built the optimized plan",
    ("Replanner", "no feasible plan"): "could not build an optimized plan",
    ("Replanner", "messages drafted"): "drafted",
    ("Replanner", "redraft"): "kept the plan and rewrote the messages",
    ("Replanner", "alternative plan"): "switched to the manual fix",
    ("Replanner", "fallback"): "switched to the manual fix",
    ("Critic", "PASS"): "checked everything again", ("Critic", "FAIL"): "found a problem and sent the plan back",
    ("Human planner", "waiting"): "need to approve or reject the plan",
    ("Human planner", "approved"): "approved the plan", ("Human planner", "rejected"): "rejected the plan",
}
BAD_EVENTS = {"FAIL", "escalated to a human", "rejected", "stop", "ignored late alert"}


def log_line(e):
    """(who, what, detail, is_bad) for one log entry, in plain words."""
    who = "You" if e["agent"] == "Human planner" else e["agent"]
    what = EVENT_TEXT.get((e["agent"], e["event"]), e["event"])
    detail = e["detail"] or ""
    if e["event"] == "messages drafted":
        what, detail = f"drafted {detail}", ""
    elif e["event"] in ("alert accepted", "second alert arrived"):
        detail = "; ".join(describe_alert(t.strip()) for t in detail.split(";"))
    elif e["event"] == "FAIL":
        rule, _, rest = detail.partition(": ")
        detail = (PROBLEM_TEXT[rule].capitalize() + f" ({rest})") if rule in PROBLEM_TEXT else detail
    return who, what, detail, e["event"] in BAD_EVENTS


def action_summary(state, data):
    """The plan as a short list of actions, one per source and part."""
    look = {pid: {(o["mode"], o["supplier_id"]): o for o in build_options(state["impact"], data, pid)}
            for pid in state["impact"]["parts"]}
    groups = {}
    for r in state["plan"]["plan"]:
        k = (r["mode"], r["supplier_id"], r["part_id"])
        groups[k] = groups.get(k, 0) + r["qty"]
    order = {"stock": 0, "alternate": 1, "expedite": 2, "wait": 3}
    items = []
    for (mode, sid, pid), q in sorted(groups.items(), key=lambda kv: (order[kv[0][0]], kv[0][2], kv[0][1])):
        o = look[pid][(mode, sid)]
        items.append({"mode": mode, "label": MODE_WORD[mode], "qty": q, "part": part_name(pid).lower(),
                      "who": supplier_name(sid), "day": o["arrival_day"], "cost": q * o["unit_price"]})
    return items


def action_sentence(a):
    return {"stock": f"Use {a['qty']} {a['part']} units we already have in stock",
            "alternate": f"Buy {a['qty']} {a['part']} units from {a['who']}, arriving on day {a['day']}",
            "expedite": f"Pay {a['who']} to rush {a['qty']} {a['part']} units, arriving on day {a['day']}",
            "wait": f"Wait for {a['qty']} {a['part']} units from {a['who']}, arriving on day {a['day']}"}[a["mode"]]


def plan_table(state):
    rows = []
    for r in state["plan"]["plan"]:
        rows.append({"Order": r["order_id"], "Part": part_name(r["part_id"]),
                     "Comes from": "Stock" if r["mode"] == "stock" else supplier_name(r["supplier_id"]),
                     "How": MODE_WORD[r["mode"]], "Units": r["qty"]})
    return sorted(rows, key=lambda x: (x["Order"], x["Part"]))


def impact_tables(state):
    out = {}
    for pid, p in state["impact"]["parts"].items():
        out[pid] = [{"Order": o["order_id"], "Due on day": o["due_day"], "Units needed": o["need"],
                     "From stock": o["stock_default"], "Waiting on the late shipment": o["incoming_default"],
                     "Days late if nobody acts": o["days_late_default"], "Penalty per day": o["penalty_per_day"]}
                    for o in p["orders"]]
    return out


# ---------------------------------------------------------------- drawings (inline SVG)

def _nice_max(x, step=5):
    return max(step * 2, int(-(-x // step) * step))


def timeline_svg(state, data, view, cmp=None):
    """One row per affected order: the due day, and the day its last part arrives.

    `view` is 'nothing' or 'plan'. The scale stays the same in both views, so
    switching between them shows the dots moving.
    """
    cmp = cmp or compare(state, data)
    imp = state["impact"]
    shown = cmp["by_key"]["nothing"] if view == "nothing" else cmp["by_key"][cmp["on_table"]]
    orders = sorted(imp["orders"].items(), key=lambda kv: (kv[1]["due_day"], kv[0]))
    parts = list(imp["parts"].values())

    every = [o["due_day"] for _, o in orders] + [p["delayed_arrival"] for p in parts]
    for opt in cmp["options"]:
        every += list(opt["arrivals"].values())
    top = _nice_max(max(every) + 3, 10 if max(every) > 45 else 5)
    tick = 10 if top > 45 else 5

    W, left, right = 960, 58, 86
    band_h, row_h = 36, 23
    head = 24 + band_h * len(parts) + 6
    H = head + row_h * len(orders) + 10

    def x(d):
        return left + (W - left - right) * d / top

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" class="tl" '
           f'aria-label="Due day and arrival day for {len(orders)} orders">',
           '<defs><pattern id="hz" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
           f'<rect width="10" height="10" fill="{COLOR["signal"]}"/><rect width="4" height="10" fill="{COLOR["ink"]}" opacity=".85"/>'
           '</pattern></defs>']
    for d in range(0, top + 1, tick):
        out.append(f'<line x1="{x(d):.1f}" x2="{x(d):.1f}" y1="18" y2="{H - 6}" stroke="{COLOR["faint"]}"/>')
        out.append(f'<text x="{x(d):.1f}" y="12" text-anchor="middle" class="ax">{"today" if d == 0 else f"day {d}"}</text>')

    for i, p in enumerate(parts):
        y = 24 + i * band_h
        x0, x1 = x(p["normal_arrival"]), x(p["delayed_arrival"])
        label = (f"{part_name(p['part_id'])} from {supplier_name(p['supplier_id'])}: "
                 f"was arriving day {p['normal_arrival']}, now day {p['delayed_arrival']}")
        tx = min(max(x0, left), W - 6.4 * len(label))
        out.append(f'<g><title>{escape(label)}</title>'
                   f'<text x="{tx:.1f}" y="{y + 11}" class="bl">{escape(label)}</text>'
                   f'<rect x="{x0:.1f}" y="{y + 17}" width="{max(x1 - x0, 2):.1f}" height="11" fill="url(#hz)" rx="2"/></g>')
        out.append(f'<line x1="{x1:.1f}" x2="{x1:.1f}" y1="{y + 28}" y2="{H - 6}" stroke="{COLOR["signal"]}" '
                   'stroke-width="1.5" stroke-dasharray="3 4"/>')

    for i, (oid, o) in enumerate(orders):
        y = head + i * row_h + row_h / 2
        due = o["due_day"]
        arr = shown["arrivals"].get(oid, 0)
        late = max(0, arr - due)
        tip = (f"Order {oid}: due day {due}, last part arrives day {arr}, "
               + (f"{plural(late, 'day')} late, {money(late * o['penalty_per_day'])} in penalties" if late else "on time"))
        out.append(f'<g class="row"><title>{escape(tip)}</title>'
                   f'<rect x="0" y="{y - row_h / 2:.1f}" width="{W}" height="{row_h}" class="hit"/>'
                   f'<text x="0" y="{y + 4:.1f}" class="oid">{oid}</text>'
                   f'<line x1="{x(0):.1f}" x2="{x(due):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{COLOR["rule"]}" stroke-width="3" stroke-linecap="round"/>'
                   f'<line x1="{x(due):.1f}" x2="{x(due):.1f}" y1="{y - 7:.1f}" y2="{y + 7:.1f}" stroke="{COLOR["ink"]}" stroke-width="2.5"/>')
        if late:
            out.append(f'<line x1="{x(due):.1f}" x2="{x(arr):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{COLOR["late"]}" stroke-width="3"/>'
                       f'<circle cx="{x(arr):.1f}" cy="{y:.1f}" r="5.5" fill="{COLOR["late"]}"/>'
                       f'<text x="{x(arr) + 10:.1f}" y="{y + 4:.1f}" class="lt">{plural(late, "day")} late</text>')
        else:
            out.append(f'<circle cx="{x(arr):.1f}" cy="{y:.1f}" r="5.5" fill="{COLOR["ok"]}"/>')
        out.append('</g>')
    out.append('</svg>')
    return "".join(out)


def cost_svg(cmp, status):
    """Three horizontal bars: parts cost plus penalties for each option."""
    W, left, right, row = 960, 250, 150, 54
    H = row * 3 + 6
    top = max(o["total"] for o in cmp["options"]) or 1
    tag = {"awaiting_approval": "waiting for you", "released": "approved", "escalated": "not sent"}.get(status, "")

    def w(v):
        return (W - left - right) * v / top

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" class="cost" aria-label="Cost of each way to handle the delay">']
    for i, o in enumerate(cmp["options"]):
        y = i * row + 8
        mine = o["key"] == cmp["on_table"]
        late = len(o["late"])
        out.append(f'<g><title>{escape(o["label"])}: parts {money(o["purchase"])}, penalties {money(o["penalty"])}</title>')
        out.append(f'<text x="0" y="{y + 15}" class="{"cl on" if mine else "cl"}">{escape(o["label"])}</text>')
        out.append(f'<text x="0" y="{y + 33}" class="cs">'
                   + ("every order on time" if late == 0 else f"{plural(late, 'order')} late") + '</text>')
        bp, bl = w(o["purchase"]), w(o["penalty"])
        out.append(f'<rect x="{left}" y="{y + 4}" width="{max(bp, 1):.1f}" height="22" fill="{COLOR["steel"] if mine else COLOR["steel_light"]}"/>')
        if bl > 0:
            out.append(f'<rect x="{left + bp:.1f}" y="{y + 4}" width="{bl:.1f}" height="22" fill="{COLOR["late"]}" opacity="{1 if mine else .55}"/>')
        out.append(f'<text x="{left + bp + bl + 10:.1f}" y="{y + 20}" class="{"cv on" if mine else "cv"}">{money(o["total"])}</text>')
        if mine and tag:
            out.append(f'<text x="{left + bp + bl + 10:.1f}" y="{y + 38}" class="ct">{tag}</text>')
        out.append('</g>')
    out.append('</svg>')
    return "".join(out)


# ---------------------------------------------------------------- results across the test cases

def results(data):
    """Run every test case through the agents and boil it down to a few plain facts."""
    from run_scenarios import run_graph
    scen = load_scenarios()
    rows = []
    for sc in scen:
        out = run_graph(sc, data)
        want = sc.get("expect_faulted", sc["expect"]) if sc.get("fault") else sc["expect"]
        rows.append({"sc": sc, "want": want, "got": out["status"], "ok": out["status"] == want,
                     "critic_fails": out["critic_fails"], "totals": out["totals"], "base": out["base"]})

    # Cost figures only from real replans. The two planted-mistake cases test the
    # Critic, and one of them repeats an ordinary case, so counting them would
    # count that case twice.
    cost = []
    for r in rows:
        if r["sc"]["category"] in ("normal", "second_alert") and r["totals"]:
            o, b = r["totals"], r["base"]
            cost.append({"id": r["sc"]["id"], "name": r["sc"]["name"], "opt": o["total_cost"], "base": b["total_cost"],
                         "opt_late": len(o["late_orders"]), "base_late": len(b["late_orders"]),
                         "saving": (b["total_cost"] - o["total_cost"]) / b["total_cost"]})
    groups = {}
    for r in rows:
        g = groups.setdefault(r["sc"]["category"], {"n": 0, "ok": 0})
        g["n"] += 1
        g["ok"] += r["ok"] and (r["sc"]["category"] != "fault" or r["critic_fails"] > 0)
    savings = [c["saving"] for c in cost]
    return {
        "rows": rows, "cost": cost, "groups": groups,
        "n": len(rows), "as_expected": sum(r["ok"] for r in rows),
        "cheaper": sum(c["opt"] < c["base"] - 0.5 for c in cost),
        "median": statistics.median(savings) if savings else 0,
        "low": min(savings) if savings else 0, "high": max(savings) if savings else 0,
        "big": [c for c in cost if c["saving"] >= 0.5],
        "opt_late": sum(c["opt_late"] for c in cost), "base_late": sum(c["base_late"] for c in cost),
        "more_late": [c for c in cost if c["opt_late"] > c["base_late"]],
        "fewer_late": [c for c in cost if c["opt_late"] < c["base_late"]],
    }


def results_svg(res):
    """Saving per test case, largest first, with the median marked."""
    cost = sorted(res["cost"], key=lambda c: -c["saving"])
    W, left, right, row = 1000, 300, 60, 24
    H = row * len(cost) + 34

    def x(p):
        return left + (W - left - right) * p

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" class="res" aria-label="Saving in each test case">']
    for p in (0, .25, .5, .75, 1):
        out.append(f'<line x1="{x(p):.1f}" x2="{x(p):.1f}" y1="4" y2="{H - 22}" stroke="{COLOR["faint"]}"/>'
                   f'<text x="{x(p):.1f}" y="{H - 6}" text-anchor="middle" class="ax">{p:.0%}</text>')
    for i, c in enumerate(cost):
        y = 6 + i * row
        tip = f"{c['name']}: optimized plan {money(c['opt'])}, manual fix {money(c['base'])}"
        out.append(f'<g><title>{escape(tip)}</title><text x="{left - 12}" y="{y + 14}" text-anchor="end" class="rn">{escape(c["name"])}</text>'
                   f'<rect x="{left}" y="{y + 3}" width="{max(x(c["saving"]) - left, 1):.1f}" height="15" fill="{COLOR["steel"]}"/>'
                   f'<text x="{x(c["saving"]) + 8:.1f}" y="{y + 15}" class="rv">{c["saving"]:.0%}</text></g>')
    m = x(res["median"])
    out.append(f'<line x1="{m:.1f}" x2="{m:.1f}" y1="0" y2="{H - 22}" stroke="{COLOR["ink"]}" stroke-width="1.5" stroke-dasharray="4 3"/>')
    out.append('</svg>')
    return "".join(out)


def results_table(res):
    return [{"Case": r["sc"]["id"], "What it tests": r["sc"]["name"],
             "Expected result": OUTCOME.get(r["want"], r["want"]), "Actual result": OUTCOME.get(r["got"], r["got"]),
             "Correct": "yes" if r["ok"] else "no",
             "Optimized cost": round(r["totals"]["total_cost"]) if r["totals"] else None,
             "Manual fix cost": round(r["base"]["total_cost"]) if r["base"] else None}
            for r in res["rows"]]
