"""Run one or two alerts through every tool (no agents).

    python run_tools_demo.py "S2 delays P4 by 10 days"
    python run_tools_demo.py "S2 delays P4 by 25 days" "S1 delays P1 by 15 days"
"""
import sys

from tools.data_loader import load_data
from tools.pipeline import run_alert

texts = sys.argv[1:] or ["S2 delays P4 by 25 days"]
r = run_alert(texts, load_data())
print("Alerts:", " | ".join(texts))
if r["status"] != "ok":
    print(f"Result: {r['status']} ({r['reason']})")
    sys.exit()

imp, base, t = r["impact"], r["baseline_totals"], r["critic"]["totals"]
for pid, p in imp["parts"].items():
    print(f"  {pid}: {len(p['orders'])} orders, stock {p['on_hand']} of {p['total_need']} units, {p['shortfall_total']} short")
print(f"At risk: {', '.join(imp['orders_at_risk'])}.  Doing nothing costs {imp['penalty_if_nothing_done']} in late penalties\n")
print(f"{'':10s}{'purchase':>10s}{'penalty':>10s}{'total':>10s}{'late orders':>13s}")
print(f"{'baseline':10s}{base['purchase_cost']:>10.0f}{base['penalty_cost']:>10.0f}{base['total_cost']:>10.0f}{len(base['late_orders']):>13d}")
print(f"{'optimizer':10s}{t['purchase_cost']:>10.0f}{t['penalty_cost']:>10.0f}{t['total_cost']:>10.0f}{len(t['late_orders']):>13d}")
print(f"\nCritic: {r['critic']['verdict']}  " + "  ".join(f"{k}={'ok' if v['ok'] else 'FAIL'}" for k, v in r["critic"]["rules"].items()))
print("\nMessages:")
for m in r["messages"]:
    print(" -", m["text"])
