"""Critic's tools: recompute_cost(), check_plan(), check_message_numbers().

The Critic never reads the Replanner's option table or totals. It goes back
to the raw tables and works everything out again, so a wrong number cannot
vouch for itself.

Rules
  R1  No negative stock: stock used is at most what is on hand, no negative quantities
  R2  Supplier capacity respected, and every source in the plan really exists
  R3  Every affected order is fully covered, and the late-order list is right
  R4  Recomputed cost matches the reported cost
  R5  Every number in a message matches the plan
"""
import math
import numbers
import re

from tools.alerts import normalize_alerts, extra_delay
from config import SPOT_PREMIUM, EXPEDITE_PREMIUM, EXPEDITE_CAPACITY, STOCK, MONEY_TOL

RULES = ("R1", "R2", "R3", "R4", "R5")


def _ctx(data, alert, alerts):
    """Work out the situation again from the raw tables."""
    pid, sid, delay = alert["part_id"], alert["supplier_id"], alert["delay_days"]
    offers = data["suppliers"][data["suppliers"].part_id == pid]
    prim = offers[offers.is_primary]
    mine = (not prim.empty) and prim.iloc[0].supplier_id == sid

    need = {}
    if mine:
        bom = data["bom"][data["bom"].part_id == pid]
        od = data["orders"][data["orders"].status == "open"].merge(bom, on="product_id")
        for r in od.itertuples():
            need[r.order_id] = {"need": int(r.quantity) * int(r.qty_per_unit),
                                "due": int(r.due_day), "pen": int(r.late_penalty_per_day)}
    inv = data["inventory"][data["inventory"].part_id == pid]
    on_hand = max(0, int(inv.on_hand.iloc[0])) if len(inv) else 0
    in_transit = max(0, sum(v["need"] for v in need.values()) - on_hand)
    return {"pid": pid, "sid": sid, "delay": delay, "offers": offers, "need": need, "mine": mine, "alerts": alerts,
            "on_hand": on_hand, "in_transit": in_transit,
            "names": data["suppliers"].drop_duplicates("supplier_id").set_index("supplier_id")["supplier_name"].to_dict()}


def _ctxs(data, alerts):
    """One context per late part. The main supplier's alert decides it; an alert
    on a backup supplier only changes that backup's arrival day."""
    out = {}
    for a in normalize_alerts(alerts):
        c = _ctx(data, a, alerts)
        if c["mine"] or a["part_id"] not in out:
            out[a["part_id"]] = c
    return {pid: c for pid, c in out.items() if c["mine"]}


def _terms(c, mode, supplier):
    """(unit price, arrival day, capacity) for a source, or None if it is not real."""
    if mode == "stock":
        return (0.0, 0, c["on_hand"]) if supplier == STOCK else None
    row = c["offers"][c["offers"].supplier_id == supplier]
    if row.empty:
        return None
    row = row.iloc[0]
    if mode in ("wait", "expedite"):
        if supplier != c["sid"]:
            return None
        if mode == "wait":
            return float(row.unit_price), int(row.lead_days) + c["delay"], c["in_transit"]
        return (round(float(row.unit_price) * EXPEDITE_PREMIUM, 2),
                int(row.lead_days) + math.ceil(c["delay"] / 2),
                min(c["in_transit"], int(row.capacity * EXPEDITE_CAPACITY)))
    if mode == "alternate":
        if supplier == c["sid"]:
            return None
        return (round(float(row.unit_price) * SPOT_PREMIUM, 2),
                int(row.lead_days) + extra_delay(c["alerts"], supplier, c["pid"]), int(row.capacity))
    return None


def recompute_cost(plan, data, alerts):
    ctxs = _ctxs(data, alerts)
    purchase, arrival, bad = 0.0, {}, []
    due = {}
    for c in ctxs.values():
        for oid, v in c["need"].items():
            due[oid] = v
    for r in plan:
        c = ctxs.get(r["part_id"])
        t = _terms(c, r["mode"], r["supplier_id"]) if c else None
        if t is None or r["order_id"] not in c["need"]:
            bad.append(r)
            continue
        purchase += r["qty"] * t[0]
        arrival[r["order_id"]] = max(arrival.get(r["order_id"], 0), t[1])
    penalty, late, late_days = 0.0, [], 0
    for oid, arr in arrival.items():
        d = max(0, arr - due[oid]["due"])
        if d:
            late.append(oid)
            late_days += d
            penalty += d * due[oid]["pen"]
    return {"purchase_cost": round(purchase, 2), "penalty_cost": round(penalty, 2),
            "total_cost": round(purchase + penalty, 2), "late_orders": sorted(late),
            "late_days": late_days, "invalid_rows": bad, "arrivals": arrival}


def _whole(q):
    """True for any whole number type (int, numpy int), but not for bools or floats."""
    return isinstance(q, numbers.Integral) and not isinstance(q, bool)


def _rule(issues):
    return {"ok": not issues, "issues": issues}


def check_plan(result, data, alerts):
    """R1 to R4."""
    ctxs = _ctxs(data, alerts)
    plan = result["plan"]
    r1, r2, r3, r4 = [], [], [], []

    for r in plan:
        if not _whole(r["qty"]) or r["qty"] < 0:
            r1.append(f"{r['order_id']}: quantity {r['qty']} is not a whole, non-negative number")
    for pid, c in ctxs.items():
        used = sum(r["qty"] for r in plan if r["part_id"] == pid and r["mode"] == "stock"
                   and _whole(r["qty"]) and r["qty"] > 0)
        if used > c["on_hand"]:
            r1.append(f"{pid}: stock used {used} exceeds {c['on_hand']} on hand")

    usage = {}
    for r in plan:
        c = ctxs.get(r["part_id"])
        t = _terms(c, r["mode"], r["supplier_id"]) if c else None
        if t is None or r["order_id"] not in c["need"]:
            r2.append(f"{r['order_id']}/{r['part_id']}: {r['mode']} from {r['supplier_id']} is not a valid source")
            continue
        k = (r["part_id"], r["mode"], r["supplier_id"])
        usage[k] = usage.get(k, 0) + r["qty"]
        if usage[k] > t[2]:
            r2.append(f"{k[1]} from {k[2]} for {k[0]}: {usage[k]} units exceeds capacity {t[2]}")
    for pid, c in ctxs.items():
        shipped = usage.get((pid, "wait", c["sid"]), 0) + usage.get((pid, "expedite", c["sid"]), 0)
        if shipped > c["in_transit"]:
            r2.append(f"{pid}: {shipped} units taken from the delayed shipment but only {c['in_transit']} are in transit")

    got = {}
    for r in plan:
        got[(r["order_id"], r["part_id"])] = got.get((r["order_id"], r["part_id"]), 0) + r["qty"]
    for pid, c in ctxs.items():
        for oid, v in c["need"].items():
            if got.get((oid, pid), 0) != v["need"]:
                r3.append(f"{oid}/{pid}: covered {got.get((oid, pid), 0)} of {v['need']} units")
    totals = recompute_cost(plan, data, alerts)
    if sorted(result.get("claimed_late_orders") or []) != totals["late_orders"]:
        r3.append(f"late orders reported {result.get('claimed_late_orders')} but recomputed {totals['late_orders']}")

    claimed = result.get("claimed_total")
    if claimed is None:
        r4.append("no reported total to compare against")
    elif abs(claimed - totals["total_cost"]) > MONEY_TOL:
        r4.append(f"reported total {claimed} but recomputed {totals['total_cost']}")

    return {"rules": {"R1": _rule(r1), "R2": _rule(r2), "R3": _rule(r3), "R4": _rule(r4)}, "totals": totals}


_ID = re.compile(r"\b[A-Z]{1,3}\d+\b")
_NUM = re.compile(r"\d+(?:\.\d+)?")


def _expected_facts(plan, data, alerts):
    ctxs = _ctxs(data, alerts)
    sup, arrival, due = {}, {}, {}
    for c in ctxs.values():
        due.update({oid: v["due"] for oid, v in c["need"].items()})
    for r in plan:
        c = ctxs.get(r["part_id"])
        t = _terms(c, r["mode"], r["supplier_id"]) if c else None
        if t is None or r["order_id"] not in c["need"]:
            continue
        arrival[r["order_id"]] = max(arrival.get(r["order_id"], 0), t[1])
        if r["mode"] != "stock":
            k = (r["supplier_id"], r["part_id"], r["mode"])
            s = sup.setdefault(k, {"qty": 0, "arrival_day": t[1], "unit_price": t[0]})
            s["qty"] += r["qty"]
    cust = {oid: {"arrival_day": arr, "days_late": arr - due[oid], "due_day": due[oid]}
            for oid, arr in arrival.items() if arr > due[oid]}
    return sup, cust


def check_message_numbers(messages, result, data, alerts):
    """R5: the messages say what the plan says, and nothing else."""
    sup, cust = _expected_facts(result["plan"], data, alerts)
    issues, seen = [], set()
    for m in messages:
        key = (m["to"], m.get("part_id"), m["mode"]) if m["kind"] == "supplier" else m["to"]
        want = sup.get(key) if m["kind"] == "supplier" else cust.get(key)
        seen.add((m["kind"], key))
        if want is None:
            issues.append(f"message to {m['to']} is not backed by the plan")
            continue
        for name, val in want.items():
            if abs(float(m["numbers"].get(name, -1)) - float(val)) > 1e-9:
                issues.append(f"message to {m['to']}: {name} is {m['numbers'].get(name)}, plan says {val}")
        in_text = [float(x) for x in _NUM.findall(_ID.sub("", m["text"]))]
        allowed = [float(v) for v in want.values()]
        for x in in_text:
            if not any(abs(x - a) < 1e-9 for a in allowed):
                issues.append(f"message to {m['to']}: text contains {x:g}, which is not in the plan")
        for a in allowed:
            if not any(abs(x - a) < 1e-9 for x in in_text):
                issues.append(f"message to {m['to']}: text is missing {a:g}")
    for key in sup:
        if ("supplier", key) not in seen:
            issues.append(f"no message for supplier {key[0]} about {key[1]} ({key[2]})")
    for oid in cust:
        if ("customer", oid) not in seen:
            issues.append(f"no message for late order {oid}")
    return {"R5": _rule(issues)}


def review(result, messages, data, alerts):
    """Run every check. A check that crashes counts as a FAIL, never a PASS."""
    rules, totals = {}, None
    try:
        out = check_plan(result, data, alerts)
        rules.update(out["rules"])
        totals = out["totals"]
    except Exception as e:                                   # noqa: BLE001
        for r in ("R1", "R2", "R3", "R4"):
            rules[r] = _rule([f"check crashed: {e!r}"])
    try:
        rules.update(check_message_numbers(messages, result, data, alerts))
    except Exception as e:                                   # noqa: BLE001
        rules["R5"] = _rule([f"check crashed: {e!r}"])
    issues = [f"{r}: {i}" for r in RULES for i in rules[r]["issues"]]
    return {"verdict": "FAIL" if issues else "PASS", "rules": rules, "issues": issues, "totals": totals}
