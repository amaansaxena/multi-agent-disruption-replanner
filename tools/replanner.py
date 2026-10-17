"""Replanner's tools: solve_plan(), fcfs_baseline(), draft_message().

Every affected (order, part) needs `need` units of a late part. Units can come from:
  stock      free, arrives day 0, limited to what is on hand
  wait       the delayed shipment as it is, arrives late, limited to what is in transit
  expedite   the same supplier rushing part of it, 35% dearer, half the delay
  alternate  a backup supplier, 10% dearer, limited by their capacity
A plan is a list of rows {order_id, part_id, supplier_id, mode, qty}.
An order is as late as its latest part, and each late day costs the order's penalty.
"""
import math

import pulp

from tools.alerts import extra_delay
from data.generate_data import PARTS
from config import SPOT_PREMIUM, EXPEDITE_PREMIUM, EXPEDITE_CAPACITY, STOCK


def build_options(impact, data, pid):
    rep = impact["parts"][pid]
    sid, delay = rep["supplier_id"], rep["delay_days"]
    offers = data["suppliers"][data["suppliers"].part_id == pid]
    prim = offers[offers.supplier_id == sid].iloc[0]
    price, lead, transit = float(prim.unit_price), int(prim.lead_days), rep["incoming"]

    opts = [
        {"mode": "stock", "supplier_id": STOCK, "unit_price": 0.0, "arrival_day": 0, "cap": rep["on_hand"]},
        {"mode": "expedite", "supplier_id": sid, "unit_price": round(price * EXPEDITE_PREMIUM, 2),
         "arrival_day": lead + math.ceil(delay / 2), "cap": min(transit, int(prim.capacity * EXPEDITE_CAPACITY))},
        {"mode": "wait", "supplier_id": sid, "unit_price": price,
         "arrival_day": lead + delay, "cap": transit},
    ]
    for r in offers[offers.supplier_id != sid].sort_values("supplier_id").itertuples():
        opts.append({"mode": "alternate", "supplier_id": r.supplier_id,
                     "unit_price": round(float(r.unit_price) * SPOT_PREMIUM, 2),
                     "arrival_day": int(r.lead_days) + extra_delay(impact.get("alerts"), r.supplier_id, pid),
                     "cap": int(r.capacity)})
    return opts


def _pairs(impact):
    """Every (order, part) that needs units, ordered by due date."""
    out = []
    for pid, rep in impact["parts"].items():
        for o in rep["orders"]:
            if o["need"] > 0:
                out.append({"order_id": o["order_id"], "part_id": pid, "need": o["need"],
                            "due_day": o["due_day"], "pen": o["penalty_per_day"]})
    return sorted(out, key=lambda p: (p["due_day"], p["order_id"], p["part_id"]))


def _lookup(impact, data):
    return {pid: {(o["mode"], o["supplier_id"]): o for o in build_options(impact, data, pid)} for pid in impact["parts"]}


def summarize_plan(rows, impact, data):
    """Cost and lateness of a plan, using this module's option table."""
    look = _lookup(impact, data)
    arrival, purchase = {}, 0.0
    for r in rows:
        o = look[r["part_id"]][(r["mode"], r["supplier_id"])]
        purchase += r["qty"] * o["unit_price"]
        arrival[r["order_id"]] = max(arrival.get(r["order_id"], 0), o["arrival_day"])
    penalty, late = 0.0, []
    for oid, arr in arrival.items():
        d = max(0, arr - impact["orders"][oid]["due_day"])
        if d:
            late.append(oid)
            penalty += d * impact["orders"][oid]["penalty_per_day"]
    return {"purchase": round(purchase, 2), "penalty": round(penalty, 2),
            "total": round(purchase + penalty, 2), "late_orders": sorted(late)}


def _result(rows, impact, data, optimized, status, total=None):
    s = summarize_plan(rows, impact, data)
    return {"plan": rows, "claimed_total": s["total"] if total is None else round(total, 2),
            "claimed_late_orders": s["late_orders"], "optimized": optimized, "status": status}


# ---------------------------------------------------------------- Optimizer

def solve_plan(impact, data):
    """Cheapest mix of sources for every affected order and part (PuLP, whole units)."""
    pairs = _pairs(impact)
    opts = {pid: build_options(impact, data, pid) for pid in impact["parts"]}

    prob = pulp.LpProblem("replan", pulp.LpMinimize)
    q, y = {}, {}
    for i, p in enumerate(pairs):
        for k, o in enumerate(opts[p["part_id"]]):
            q[i, k] = pulp.LpVariable(f"q_{i}_{k}", lowBound=0, cat="Integer")
            if o["arrival_day"] > p["due_day"]:
                y[i, k] = pulp.LpVariable(f"y_{i}_{k}", cat="Binary")
    late = {oid: pulp.LpVariable(f"late_{n}", lowBound=0) for n, oid in enumerate(impact["orders"])}

    prob += (pulp.lpSum(q[i, k] * opts[p["part_id"]][k]["unit_price"] for i, p in enumerate(pairs)
                        for k in range(len(opts[p["part_id"]])))
             + pulp.lpSum(impact["orders"][oid]["penalty_per_day"] * late[oid] for oid in late))

    for i, p in enumerate(pairs):
        os_ = opts[p["part_id"]]
        prob += pulp.lpSum(q[i, k] for k in range(len(os_))) == p["need"]       # fully covered
        for k, o in enumerate(os_):
            if (i, k) in y:                                                      # slow source means a late order
                prob += q[i, k] <= p["need"] * y[i, k]
                prob += late[p["order_id"]] >= (o["arrival_day"] - p["due_day"]) * y[i, k]
    for pid, os_ in opts.items():
        idx = [i for i, p in enumerate(pairs) if p["part_id"] == pid]
        for k, o in enumerate(os_):                                              # capacity of each source
            prob += pulp.lpSum(q[i, k] for i in idx) <= o["cap"]
        w = next(k for k, o in enumerate(os_) if o["mode"] == "wait")
        e = next(k for k, o in enumerate(os_) if o["mode"] == "expedite")
        prob += pulp.lpSum(q[i, w] + q[i, e] for i in idx) <= impact["parts"][pid]["incoming"]

    status = pulp.LpStatus[prob.solve(pulp.PULP_CBC_CMD(msg=0))]
    if status != "Optimal":
        return {"plan": [], "claimed_total": None, "claimed_late_orders": [], "optimized": False, "status": status}

    rows = []
    for i, p in enumerate(pairs):
        for k, o in enumerate(opts[p["part_id"]]):
            n = int(round(q[i, k].value()))
            if n > 0:
                rows.append({"order_id": p["order_id"], "part_id": p["part_id"],
                             "supplier_id": o["supplier_id"], "mode": o["mode"], "qty": n})
    return _result(rows, impact, data, True, "Optimal", total=pulp.value(prob.objective))


# ---------------------------------------------------------------- Baseline

def fcfs_baseline(impact, data):
    """What a busy planner does: first come, first served, first fix that works.

    Orders are handled by due date, one late part at a time. Stock goes out in
    that order. For the rest, try a rush, then backup suppliers in ID order, and
    take the first one that covers the whole gap on time. If none does, wait.
    """
    rows = []
    for pid, rep in impact["parts"].items():
        opts = build_options(impact, data, pid)
        left = {(o["mode"], o["supplier_id"]): o["cap"] for o in opts}
        transit = {"left": rep["incoming"]}
        habit = [o for o in opts if o["mode"] == "expedite"] + [o for o in opts if o["mode"] == "alternate"]
        wait_opt = next(o for o in opts if o["mode"] == "wait")

        def add(order_id, o, n):
            left[(o["mode"], o["supplier_id"])] -= n
            if o["mode"] in ("wait", "expedite"):
                transit["left"] -= n
            rows.append({"order_id": order_id, "part_id": pid, "supplier_id": o["supplier_id"],
                         "mode": o["mode"], "qty": n})

        for order in sorted(rep["orders"], key=lambda r: (r["due_day"], r["order_id"])):
            need = order["need"]
            take = min(need, left[("stock", STOCK)])
            if take:
                add(order["order_id"], opts[0], take)
            need -= take
            if need == 0:
                continue
            for o in habit:
                fits = left[(o["mode"], o["supplier_id"])] >= need
                if o["mode"] == "expedite":
                    fits = fits and transit["left"] >= need
                if fits and o["arrival_day"] <= order["due_day"]:
                    add(order["order_id"], o, need)
                    break
            else:
                add(order["order_id"], wait_opt, need)
    return _result(rows, impact, data, False, "FCFS baseline")


# ---------------------------------------------------------------- Messages

def draft_message(result, impact, data, feedback=None):
    """Template messages built straight from the plan's numbers.

    `feedback` is the Critic's last list of issues. The template ignores it,
    but a language-model drafter can use it to fix its mistakes.
    The numbers must stay exactly as they are here, because the Critic checks them.
    """
    look = _lookup(impact, data)
    names = data["suppliers"].drop_duplicates("supplier_id").set_index("supplier_id")["supplier_name"].to_dict()
    verbs = {"wait": "please confirm you will deliver", "expedite": "please rush", "alternate": "please supply"}
    msgs = []

    groups = {}
    for r in result["plan"]:
        if r["mode"] != "stock":
            k = (r["supplier_id"], r["part_id"], r["mode"])
            groups[k] = groups.get(k, 0) + r["qty"]
    for (sid, pid, mode), qty in sorted(groups.items()):
        o = look[pid][(mode, sid)]
        nums = {"qty": qty, "arrival_day": o["arrival_day"], "unit_price": o["unit_price"]}
        part = PARTS[pid][0].lower() if pid in PARTS else pid
        text = (f"Hello {names[sid]}, {verbs[mode]} {qty} units of {part} ({pid}) "
                f"to arrive on day {o['arrival_day']}, at {o['unit_price']:.2f} per unit.")
        msgs.append({"kind": "supplier", "to": sid, "part_id": pid, "mode": mode, "text": text, "numbers": nums})

    arrival = {}
    for r in result["plan"]:
        arrival[r["order_id"]] = max(arrival.get(r["order_id"], 0), look[r["part_id"]][(r["mode"], r["supplier_id"])]["arrival_day"])
    for oid in summarize_plan(result["plan"], impact, data)["late_orders"]:
        due = impact["orders"][oid]["due_day"]
        nums = {"arrival_day": arrival[oid], "days_late": arrival[oid] - due, "due_day": due}
        text = (f"Your order {oid} will now arrive on day {nums['arrival_day']}, "
                f"{nums['days_late']} {'day' if nums['days_late'] == 1 else 'days'} after the agreed date of day {nums['due_day']}. "
                "We are sorry for the delay.")
        msgs.append({"kind": "customer", "to": oid, "part_id": None, "mode": None, "text": text, "numbers": nums})
    return msgs
