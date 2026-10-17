"""Planner agent's tools: read the alert, then check it against the master data."""
import re

from config import MIN_DELAY, MAX_DELAY

_SUPPLIER = re.compile(r"\b(S\d+)\b", re.IGNORECASE)
_PART = re.compile(r"\b(P\d+)\b", re.IGNORECASE)
_DELAY = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)[\s-]*(days?|weeks?)\b", re.IGNORECASE)


class AlertError(ValueError):
    """Raised when the alert text cannot be read at all."""


def parse_alert(text):
    """'S2 delays P4 by 10 days' -> {'supplier_id': 'S2', 'part_id': 'P4', 'delay_days': 10}

    Rule based on purpose. Day 4 can try an LLM first and fall back to this.
    The supplier, part and delay can come in any order. Weeks are turned into
    days. A negative delay is kept negative so the range check rejects it, and
    a delay that is not a whole number of days is refused rather than rounded.
    """
    text = text or ""
    s, p, d = _SUPPLIER.search(text), _PART.search(text), _DELAY.search(text)
    if not (s and p and d):
        raise AlertError(f"Could not find a supplier, a part and a number of days in {text!r}")
    days = float(d.group(1)) * (7 if d.group(2).lower().startswith("week") else 1)
    if days != int(days):
        raise AlertError(f"The delay must be a whole number of days, not {d.group(1)} {d.group(2)}")
    return {"supplier_id": s.group(1).upper(), "part_id": p.group(1).upper(), "delay_days": int(days)}


def validate_against_master(alert, data):
    """Return a list of problems. An empty list means the alert is good."""
    problems = []
    offers = data["suppliers"]
    known_suppliers = set(offers.supplier_id)
    known_parts = set(offers.part_id) | set(data["bom"].part_id)

    if alert["supplier_id"] not in known_suppliers:
        problems.append(f"There is no supplier called {alert['supplier_id']}")
    if alert["part_id"] not in known_parts:
        problems.append(f"There is no part called {alert['part_id']}")
    if not (MIN_DELAY <= alert["delay_days"] <= MAX_DELAY):
        problems.append(f"A delay of {alert['delay_days']} days is outside the allowed range of {MIN_DELAY} to {MAX_DELAY} days")
    if not problems:
        pair = offers[(offers.supplier_id == alert["supplier_id"]) & (offers.part_id == alert["part_id"])]
        if pair.empty:
            problems.append(f"{alert['supplier_id']} does not supply {alert['part_id']}")
    return problems


def normalize_alerts(alerts):
    """Accept one alert or a list. If the same supplier and part are alerted twice, the newest wins.

    The key is (supplier, part), not just the part: a backup supplier being late
    on a part must not wipe out the main supplier's alert for the same part.
    """
    if isinstance(alerts, dict):
        alerts = [alerts]
    latest = {}
    for a in alerts:
        k = (a["supplier_id"], a["part_id"])
        latest.pop(k, None)                  # re-insert so the newest sits last
        latest[k] = a
    return list(latest.values())


def extra_delay(alerts, supplier_id, part_id):
    """Days a supplier is late on a part according to the alerts, 0 if it is not alerted.

    Used for backup suppliers: if a backup is late too, its offer arrives later.
    """
    for a in normalize_alerts(alerts or []):
        if a["supplier_id"] == supplier_id and a["part_id"] == part_id:
            return a["delay_days"]
    return 0


def read_alerts(texts, data):
    """Parse and validate a list of alert texts. Returns (alerts, problems)."""
    alerts, problems = [], []
    for t in texts:
        try:
            a = parse_alert(t)
        except AlertError as e:
            problems.append(str(e))
            continue
        bad = validate_against_master(a, data)
        problems += bad
        if not bad:
            alerts.append(a)
    return normalize_alerts(alerts), problems
