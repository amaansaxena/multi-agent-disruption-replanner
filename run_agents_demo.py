"""Run the four agents on one case and print what each one did.

    python run_agents_demo.py "S2 delays P4 by 25 days"
    python run_agents_demo.py "S2 delays P4 by 20 days" --late "S1 delays P1 by 35 days"
"""
import argparse

from tools.data_loader import load_data
from agents.graph import build_graph, run_agents

ap = argparse.ArgumentParser()
ap.add_argument("alerts", nargs="+")
ap.add_argument("--late", nargs="*", default=[])
args = ap.parse_args()

data = load_data()
state = run_agents(build_graph(data), args.alerts, args.late)
for e in state["log"]:
    print(f"{e['agent']:15s} {e['event']:28s} {e['detail']}")
print(f"\nFinal status: {state['status']}   retries used: {state.get('attempt', 0)}")
if state["status"] == "released":
    t, b = state["critic"]["totals"], state["baseline_totals"]
    print(f"Optimizer total {t['total_cost']:.0f} ({len(t['late_orders'])} late)   baseline total {b['total_cost']:.0f} ({len(b['late_orders'])} late)")
