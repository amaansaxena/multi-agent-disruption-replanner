"""Run all 20 scenarios and print the numbers for slide 9.

    python run_scenarios.py --mode tools    # Day 3: tools only, faults and late timing ignored
    python run_scenarios.py --mode graph    # Day 4: the four agents, faults switched on
"""
import argparse
import csv
import json
import os

from tools.data_loader import load_data
from tools.pipeline import run_alert
from agents.graph import build_graph, run_agents
from agents.faults import apply_fault
from tools.replanner import solve_plan, draft_message

HERE = os.path.dirname(os.path.abspath(__file__))


def run_tools(sc, data):
    texts = sc["alerts"] + ([sc["late_alert"]] if sc.get("late_alert") else [])
    r = run_alert(texts, data)
    if r["status"] != "ok":
        return {"status": r["status"], "retries": 0, "critic_fails": 0, "totals": None, "base": None, "impact": r.get("impact")}
    status = "released" if r["critic"]["verdict"] == "PASS" else "critic_fail"
    return {"status": status, "retries": 0, "critic_fails": 0 if status == "released" else 1,
            "totals": r["critic"]["totals"], "base": r["baseline_totals"], "impact": r["impact"]}


def run_graph(sc, data):
    solver, drafter = apply_fault(sc.get("fault"), solve_plan, draft_message)
    state = run_agents(build_graph(data, solver=solver, drafter=drafter), sc["alerts"],
                       [sc["late_alert"]] if sc.get("late_alert") else [])
    fails = sum(1 for e in state["log"] if e["agent"] == "Critic" and e["event"] == "FAIL")
    released = state["status"] == "released"
    return {"status": state["status"], "retries": state.get("attempt", 0), "critic_fails": fails,
            "totals": state["critic"]["totals"] if released else None,
            "base": state.get("baseline_totals") if released else None, "impact": state.get("impact")}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["tools", "graph"], default="graph")
    mode = ap.parse_args().mode

    data = load_data()
    scenarios = json.load(open(os.path.join(HERE, "scenarios", "scenarios.json")))
    rows = []
    for sc in scenarios:
        out = (run_tools if mode == "tools" else run_graph)(sc, data)
        want = sc.get("expect_faulted", sc["expect"]) if (mode == "graph" and sc.get("fault")) else sc["expect"]
        t, b = out["totals"], out["base"]
        rows.append({
            "id": sc["id"], "category": sc["category"], "name": sc["name"], "expected": want, "got": out["status"],
            "match": out["status"] == want, "retries": out["retries"], "critic_fails": out["critic_fails"],
            "optimizer_total": t["total_cost"] if t else "", "baseline_total": b["total_cost"] if b else "",
            "optimizer_late": len(t["late_orders"]) if t else "", "baseline_late": len(b["late_orders"]) if b else "",
            "do_nothing_penalty": out["impact"]["penalty_if_nothing_done"] if out["impact"] and out["status"] in ("released", "escalated") else "",
        })

    print(f"{'id':4s}{'category':14s}{'expected':13s}{'got':13s}{'ok':4s}{'retry':6s}{'opt cost':>10s}{'base cost':>11s}{'opt late':>9s}{'base late':>10s}")
    for r in rows:
        print(f"{r['id']:4s}{r['category']:14s}{r['expected']:13s}{r['got']:13s}{'yes' if r['match'] else 'NO':4s}{r['retries']:<6d}"
              f"{r['optimizer_total']:>10}{r['baseline_total']:>11}{r['optimizer_late']:>9}{r['baseline_late']:>10}")

    done = [r for r in rows if r["optimizer_total"] != ""]
    opt, base = sum(r["optimizer_total"] for r in done), sum(r["baseline_total"] for r in done)
    print(f"\nMode: {mode}.  Scenarios matching expectation: {sum(r['match'] for r in rows)} of {len(rows)}")
    print(f"Replanned and released: {len(done)}.  Optimizer cheaper in {sum(r['optimizer_total'] < r['baseline_total'] for r in done)}, "
          f"equal in {sum(r['optimizer_total'] == r['baseline_total'] for r in done)}, dearer in {sum(r['optimizer_total'] > r['baseline_total'] for r in done)}")
    print(f"Total cost, baseline {base:,.0f} vs optimizer {opt:,.0f}  ({100 * (base - opt) / base:.1f}% lower)")
    print(f"Late orders, baseline {sum(r['baseline_late'] for r in done)} vs optimizer {sum(r['optimizer_late'] for r in done)}.  "
          f"Optimizer had more late orders in {sum(r['optimizer_late'] > r['baseline_late'] for r in done)} scenarios, fewer in {sum(r['optimizer_late'] < r['baseline_late'] for r in done)}")
    if mode == "graph":
        faulty = [s for s in scenarios if s.get("fault")]
        caught = [r for r in rows if r["id"] in {s['id'] for s in faulty} and r["critic_fails"] > 0]
        print(f"Planted faults: {len(faulty)}.  Critic caught {len(caught)}.")
    path = os.path.join(HERE, "scenarios", f"results_{mode}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {path}")
