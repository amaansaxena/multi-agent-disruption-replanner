"""Impact Analyst's tools.

Plain language version of the model:
  - Every open order that uses the late part needs some units of it.
  - Stock on hand is handed out first-come-first-served by due date.
  - Whatever stock cannot cover was going to arrive on the delayed shipment.
  - If that shipment lands after the due date, those units are the shortfall.
"""
from tools.alerts import normalize_alerts


def _primary_row(data, part_id):
    s = data["suppliers"]
    rows = s[(s.part_id == part_id) & (s.is_primary)]
    return rows.iloc[0] if len(rows) else None


def find_affected_orders(data, alert):
    """Open orders that need the late part from the late supplier's shipment."""
    prim = _primary_row(data, alert["part_id"])
    if prim is None or prim.supplier_id != alert["supplier_id"]:
        return []   # that supplier is only a backup for this part, nothing of theirs is in transit
    bom = data["bom"]
    qpu = bom[bom.part_id == alert["part_id"]].set_index("product_id")["qty_per_unit"].to_dict()
    o = data["orders"]
    o = o[(o.status == "open") & (o.product_id.isin(qpu))]
    rows = [{"order_id": r.order_id, "product_id": r.product_id,
             "need": int(r.quantity) * int(qpu[r.product_id]),
             "due_day": int(r.due_day), "penalty_per_day": int(r.late_penalty_per_day)}
            for r in o.itertuples()]
    return sorted(rows, key=lambda r: (r["due_day"], r["order_id"]))


def check_stock(data, part_id):
    """Units on hand. A missing record counts as zero so the shortage shows up."""
    inv = data["inventory"]
    row = inv[inv.part_id == part_id]
    return max(0, int(row.on_hand.iloc[0])) if len(row) else 0


def compute_shortfall(orders, on_hand, alert, data):
    """Build the impact report: per order, what happens if nobody acts."""
    prim = _primary_row(data, alert["part_id"])
    lead = int(prim.lead_days) if prim is not None else 0
    delayed = lead + alert["delay_days"]

    stock_left = on_hand
    out = []
    for o in orders:                       # already sorted by due date
        from_stock = min(o["need"], stock_left)
        stock_left -= from_stock
        incoming = o["need"] - from_stock
        late_days = max(0, delayed - o["due_day"]) if incoming > 0 else 0
        out.append({**o, "stock_default": from_stock, "incoming_default": incoming,
                    "days_late_default": late_days,
                    "shortfall_units": incoming if late_days > 0 else 0})

    total_need = sum(o["need"] for o in orders)
    return {
        "alert": alert, "part_id": alert["part_id"], "supplier_id": alert["supplier_id"],
        "delay_days": alert["delay_days"], "normal_arrival": lead, "delayed_arrival": delayed,
        "on_hand": on_hand, "total_need": total_need,
        "incoming": max(0, total_need - on_hand),     # units still in transit from the late supplier
        "orders": out,
        "shortfall_total": sum(o["shortfall_units"] for o in out),
        "orders_at_risk": [o["order_id"] for o in out if o["shortfall_units"] > 0],
        "penalty_if_nothing_done": sum(o["days_late_default"] * o["penalty_per_day"] for o in out),
    }


def analyse_impact(data, alerts):
    """Run the three tools for every alert, then combine them.

    An order that waits on two late parts is as late as the later one, so the
    combined report works out lateness per order, not per part.
    """
    parts, orders, days_late = {}, {}, {}
    for alert in normalize_alerts(alerts):
        rows = find_affected_orders(data, alert)
        if not rows:
            continue
        rep = compute_shortfall(rows, check_stock(data, alert["part_id"]), alert, data)
        parts[alert["part_id"]] = rep
        for o in rep["orders"]:
            orders.setdefault(o["order_id"], {"product_id": o["product_id"], "due_day": o["due_day"],
                                              "penalty_per_day": o["penalty_per_day"]})
            days_late[o["order_id"]] = max(days_late.get(o["order_id"], 0), o["days_late_default"])
    return {
        "alerts": normalize_alerts(alerts),
        "parts": parts,                      # part_id -> per-part report
        "orders": orders,                    # order_id -> due day and penalty
        "shortfall_total": sum(p["shortfall_total"] for p in parts.values()),
        "orders_at_risk": sorted({oid for p in parts.values() for oid in p["orders_at_risk"]}),
        "penalty_if_nothing_done": sum(d * orders[o]["penalty_per_day"] for o, d in days_late.items()),
    }
