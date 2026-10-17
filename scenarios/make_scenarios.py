"""Day 3: write scenarios/scenarios.json.

Twenty alerts, picked from real runs so each one does what its label says:
10 normal replans, 1 slack case, 1 no-impact case, 4 bad alerts,
2 with a second alert arriving mid-run, 2 with a planted fault.

    expect          outcome of a clean run
    late_alert      a second alert that arrives while the first is being planned
    fault           something deliberately broken, to see if the Critic catches it
    expect_faulted  outcome when the fault is switched on
"""
import json
import os

S = [
    # ---- normal replans, small to large, one with a missing stock record (P8) ----
    ("S01", "Small delay, one order at risk", "normal", ["S2 delays P4 by 10 days"], "released"),
    ("S02", "Medium delay on the wiring harness", "normal", ["S2 delays P4 by 25 days"], "released"),
    ("S03", "Long delay on the wiring harness", "normal", ["S2 delays P4 by 40 days"], "released"),
    ("S04", "Steel frame, many orders at risk", "normal", ["S1 delays P1 by 35 days"], "released"),
    ("S05", "Cheap part, bolt set", "normal", ["S1 delays P5 by 25 days"], "released"),
    ("S06", "Motor housing, short delay", "normal", ["S3 delays P2 by 12 days"], "released"),
    ("S07", "Gear assembly, large shortfall", "normal", ["S3 delays P6 by 30 days"], "released"),
    ("S08", "Control board, most expensive part", "normal", ["S4 delays P3 by 30 days"], "released"),
    ("S09", "Plastic casing, very long delay", "normal", ["S4 delays P7 by 45 days"], "released"),
    ("S10", "Sensor module, none in stock, 60-day delay", "normal", ["S2 delays P8 by 60 days"], "released"),
    # ---- exceptions from the architecture slide ----
    ("S11", "Delay too short to matter", "no_shortfall", ["S2 delays P4 by 1 days"], "no_shortfall"),
    ("S12", "Alert about a backup supplier", "no_impact", ["S2 delays P1 by 10 days"], "no_impact"),
    ("S13", "Unknown supplier", "bad_alert", ["S9 delays P4 by 5 days"], "bad_alert"),
    ("S14", "Unknown part", "bad_alert", ["S2 delays P99 by 5 days"], "bad_alert"),
    ("S15", "Delay longer than 60 days", "bad_alert", ["S2 delays P4 by 75 days"], "bad_alert"),
    ("S16", "Alert with no supplier, part or delay in it", "bad_alert", ["Our supplier says the shipment is running late"], "bad_alert"),
    # ---- a second alert arrives mid-run ----
    ("S17", "Second delay on a different part", "second_alert", ["S2 delays P4 by 20 days"], "released",
     {"late_alert": "S1 delays P1 by 35 days"}),
    ("S18", "Two big delays hitting the same orders", "second_alert", ["S3 delays P2 by 25 days"], "released",
     {"late_alert": "S4 delays P3 by 30 days"}),
    # ---- planted faults: does the Critic catch them? ----
    ("S19", "Solver reports a wrong total on its first try", "fault", ["S1 delays P5 by 25 days"], "released",
     {"fault": "wrong_total_once", "expect_faulted": "released"}),
    ("S20", "Messages always quote a wrong quantity", "fault", ["S3 delays P6 by 30 days"], "released",
     {"fault": "wrong_message_always", "expect_faulted": "escalated"}),
]

rows = []
for item in S:
    sid, name, cat, alerts, expect = item[:5]
    extra = item[5] if len(item) > 5 else {}
    rows.append({"id": sid, "name": name, "category": cat, "alerts": alerts, "expect": expect, **extra})

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios.json")
with open(out, "w") as f:
    json.dump(rows, f, indent=2)
print(f"wrote {len(rows)} scenarios to {out}")
