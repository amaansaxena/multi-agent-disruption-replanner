"""Day 2 checks.   python test_tools.py"""
import copy

from tools.data_loader import load_data
from tools.alerts import parse_alert, validate_against_master, AlertError
from tools.impact import analyse_impact, check_stock
from tools.replanner import solve_plan, fcfs_baseline, draft_message, build_options
from tools.critic import review, check_plan, check_message_numbers, recompute_cost
from tools.pipeline import run_alert

data = load_data()


def raises(fn, *a):
    try:
        fn(*a)
    except AlertError:
        return True
    return False


# ---- data store ----
assert data["suppliers"].supplier_id.nunique() == 4
assert data["suppliers"].part_id.nunique() == 8
assert data["bom"].product_id.nunique() == 3
assert len(data["orders"]) == 25 and (data["orders"].status == "shipped").sum() == 4
assert data["suppliers"].groupby("part_id")["is_primary"].sum().eq(1).all()
assert set(data["bom"].part_id) == set(data["suppliers"].part_id)
assert check_stock(data, "P8") == 0, "missing stock record must count as zero"

# ---- Planner: parse_alert and validate_against_master (exception: bad alert) ----
assert parse_alert("S2 delays P4 by 10 days") == {"supplier_id": "S2", "part_id": "P4", "delay_days": 10}
assert parse_alert("Supplier s2 is delaying part p4 by 7 days.")["delay_days"] == 7
assert raises(parse_alert, "the shipment will be late")
assert raises(parse_alert, "S2 delays P4 by ten days")
assert parse_alert("S2 delays P4 by -10 days")["delay_days"] == -10, "a negative delay must stay negative"
assert validate_against_master(parse_alert("S2 delays P4 by -10 days"), data)
assert raises(parse_alert, "S2 delays P4 by 1.5 days"), "a fractional delay must not be read as 5"
assert parse_alert("P4 from S2 is 10 days late") == {"supplier_id": "S2", "part_id": "P4", "delay_days": 10}
assert parse_alert("S2 delays P4 by 2 weeks")["delay_days"] == 14
assert parse_alert("S2 reports a 12-day delay on P4")["delay_days"] == 12
assert validate_against_master({"supplier_id": "S9", "part_id": "P4", "delay_days": 5}, data)
assert validate_against_master({"supplier_id": "S2", "part_id": "P99", "delay_days": 5}, data)
assert validate_against_master({"supplier_id": "S2", "part_id": "P4", "delay_days": 0}, data)
assert validate_against_master({"supplier_id": "S2", "part_id": "P4", "delay_days": 61}, data)
offered = set(zip(data["suppliers"].supplier_id, data["suppliers"].part_id))
missing = next((s_, p_) for s_ in ("S1", "S2", "S3", "S4") for p_ in (f"P{i}" for i in range(1, 9)) if (s_, p_) not in offered)
probs = validate_against_master({"supplier_id": missing[0], "part_id": missing[1], "delay_days": 5}, data)
assert probs and "does not supply" in probs[0]
assert validate_against_master({"supplier_id": "S2", "part_id": "P4", "delay_days": 10}, data) == []
for bad in ("hello", "S9 delays P4 by 5 days", "S2 delays P4 by 99 days"):
    assert run_alert(bad, data)["status"] == "bad_alert", bad

# ---- Impact Analyst (exception: no impact) ----
quiet = copy.deepcopy(data)
quiet["orders"]["status"] = "shipped"
assert run_alert("S2 delays P4 by 10 days", quiet)["status"] == "no_impact"
backup = data["suppliers"][~data["suppliers"].is_primary].iloc[0]       # a backup supplier is not in transit
assert run_alert(f"{backup.supplier_id} delays {backup.part_id} by 10 days", data)["status"] == "no_impact"
assert run_alert("S2 delays P4 by 1 days", data)["status"] == "no_shortfall"

# ---- sweep: every primary supplier and part, many delays ----
better = same = skipped = 0
for row in data["suppliers"][data["suppliers"].is_primary].itertuples():
    for delay in (3, 7, 10, 15, 25, 40, 60):
        r = run_alert(f"{row.supplier_id} delays {row.part_id} by {delay} days", data)
        if r["status"] != "ok":
            skipped += 1
            continue
        assert r["critic"]["verdict"] == "PASS", (row.supplier_id, row.part_id, delay, r["critic"]["issues"])
        base = recompute_cost(r["baseline"]["plan"], data, r["alerts"])
        assert not base["invalid_rows"]
        opt = r["critic"]["totals"]["total_cost"]
        assert opt <= base["total_cost"] + 0.01, (row.supplier_id, row.part_id, delay, opt, base["total_cost"])
        if opt < base["total_cost"] - 0.01:
            better += 1
        else:
            same += 1
print(f"sweep: optimizer cheaper in {better}, equal in {same}, nothing to replan in {skipped}")
assert better > 0

# ---- Critic catches planted errors ----
alert = [parse_alert("S2 delays P4 by 25 days")]
imp = analyse_impact(data, alert)
good = solve_plan(imp, data)
msgs = draft_message(good, imp, data)
assert review(good, msgs, data, alert)["verdict"] == "PASS"


def fails(result, messages, rule):
    v = review(result, messages, data, alert)
    return v["verdict"] == "FAIL" and not v["rules"][rule]["ok"]


bad = copy.deepcopy(good); bad["claimed_total"] += 500
assert fails(bad, msgs, "R4"), "wrong total"

bad = copy.deepcopy(good); bad["plan"] = bad["plan"][1:]
assert fails(bad, msgs, "R3"), "an order left uncovered"

bad = copy.deepcopy(good); bad["plan"][0]["qty"] = -5
assert fails(bad, msgs, "R1"), "negative quantity"

bad = copy.deepcopy(good); bad["plan"].append({"order_id": bad["plan"][0]["order_id"], "part_id": "P4",
                                              "supplier_id": "STOCK", "mode": "stock", "qty": 10_000})
assert fails(bad, msgs, "R1"), "more stock than on hand"

bad = copy.deepcopy(good)
alt = next(r for r in bad["plan"] if r["mode"] == "alternate")
alt["qty"] += 10_000
assert fails(bad, msgs, "R2"), "supplier capacity breached"

bad = copy.deepcopy(good); bad["plan"][0].update(supplier_id="S99", mode="alternate")
assert fails(bad, msgs, "R2"), "source that does not exist"

bad_msgs = copy.deepcopy(msgs); bad_msgs[0]["numbers"]["qty"] += 1
assert fails(good, bad_msgs, "R5"), "message dict quotes the wrong quantity"

bad_msgs = copy.deepcopy(msgs); bad_msgs[0]["text"] = bad_msgs[0]["text"].replace(str(msgs[0]["numbers"]["qty"]), "999", 1)
assert fails(good, bad_msgs, "R5"), "message text quotes the wrong quantity"

assert fails(good, msgs[1:], "R5"), "a supplier with no message"

# ---- two late parts at once: one joint plan, lateness is the max across parts ----
two = run_alert(["S2 delays P4 by 25 days", "S1 delays P1 by 35 days"], data)
assert two["status"] == "ok" and two["critic"]["verdict"] == "PASS", two["critic"]["issues"]
assert set(two["impact"]["parts"]) == {"P4", "P1"}
solo = [run_alert(t, data) for t in ("S2 delays P4 by 25 days", "S1 delays P1 by 35 days")]
joint_cost = two["critic"]["totals"]["total_cost"]
apart_cost = sum(s_["critic"]["totals"]["total_cost"] for s_ in solo)
assert joint_cost <= apart_cost + 0.01, "a joint plan should never cost more than two separate ones"
# the same part alerted twice: the newest alert wins
dup = run_alert(["S2 delays P4 by 5 days", "S2 delays P4 by 25 days"], data)
assert dup["alerts"] == [{"supplier_id": "S2", "part_id": "P4", "delay_days": 25}]
print(f"two late parts: joint {joint_cost:.0f} vs separate {apart_cost:.0f}")
# a backup supplier's alert must not replace the main supplier's alert for the same part
mixed = run_alert(["S2 delays P4 by 25 days", "S4 delays P4 by 5 days"], data)
assert mixed["status"] == "ok" and mixed["critic"]["verdict"] == "PASS", mixed.get("critic", {}).get("issues")
s4 = next(o for o in build_options(mixed["impact"], data, "P4") if o["supplier_id"] == "S4")
assert s4["arrival_day"] == 6 + 5, "a late backup supplier arrives later"
# whole-number quantities from numpy are fine for R1
import numpy as np
np_plan = copy.deepcopy(good)
for r_ in np_plan["plan"]:
    r_["qty"] = np.int64(r_["qty"])
assert review(np_plan, msgs, data, alert)["verdict"] == "PASS"

# ---- a Critic check that crashes counts as FAIL ----
broken = copy.deepcopy(good); broken["plan"] = [{"oops": 1}]
v = review(broken, msgs, data, alert)
assert v["verdict"] == "FAIL" and any("crashed" in i for i in v["issues"])

# ---- solver finds no plan: fall back to baseline, marked unoptimized ----
stub = lambda impact, d: {"plan": [], "claimed_total": None, "claimed_late_orders": [], "optimized": False, "status": "Infeasible"}
r = run_alert("S2 delays P4 by 25 days", data, solver=stub)
assert r["status"] == "ok" and r["plan"]["optimized"] is False and "unoptimized" in r["plan"]["status"]
assert r["critic"]["verdict"] == "PASS" and r["note"]

print("all checks passed")
