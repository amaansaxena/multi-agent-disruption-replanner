"""Day 1: build the synthetic dataset.

    python data/generate_data.py

Matches the data store on the architecture slide: suppliers, BOM,
inventory, orders (scenarios.json comes on Day 3).
Small on purpose: 4 suppliers, 8 parts, 3 products, 25 orders.
"""
import os
import sys
import random

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SEED

OUT = os.path.dirname(os.path.abspath(__file__))

SUPPLIER_NAMES = {"S1": "Apex Metals", "S2": "Brightline Electronics",
                  "S3": "Cobalt Fasteners", "S4": "Delta Plastics"}

# part_id: (name, rough base price, primary supplier)
# Each supplier is the primary for two parts. P4 sits with S2 so the
# slide example "S2 delays P4 by 10 days" is a real case.
PARTS = {
    "P1": ("Steel Frame", 55, "S1"), "P2": ("Motor Housing", 38, "S3"),
    "P3": ("Control Board", 60, "S4"), "P4": ("Wiring Harness", 22, "S2"),
    "P5": ("Bolt Set", 6, "S1"), "P6": ("Gear Assembly", 31, "S3"),
    "P7": ("Plastic Casing", 14, "S4"), "P8": ("Sensor Module", 27, "S2"),
}
PRODUCTS = ["PR1", "PR2", "PR3"]


def build(seed=SEED):
    rnd = random.Random(seed)

    # suppliers.csv: one row per (supplier, part) offer
    offers = []
    for pid, (_, base, primary) in PARTS.items():
        backups = rnd.sample([s for s in SUPPLIER_NAMES if s != primary], rnd.randint(1, 2))
        for sid in [primary] + backups:
            is_primary = sid == primary
            offers.append({
                "supplier_id": sid, "supplier_name": SUPPLIER_NAMES[sid], "part_id": pid,
                "is_primary": is_primary,
                "unit_price": round(base * rnd.uniform(0.9, 1.2), 2),
                "lead_days": rnd.randint(3, 8) if is_primary else rnd.randint(4, 12),
                "capacity": 1000 if is_primary else rnd.randint(150, 400),
            })
    suppliers = pd.DataFrame(offers)

    # bom.csv: each product uses 5 parts; make sure no part is orphaned
    bom_rows = []
    for prod in PRODUCTS:
        for pid in rnd.sample(list(PARTS), 5):
            bom_rows.append({"product_id": prod, "part_id": pid, "qty_per_unit": rnd.randint(1, 3)})
    used = {r["part_id"] for r in bom_rows}
    for pid in PARTS:
        if pid not in used:
            bom_rows.append({"product_id": rnd.choice(PRODUCTS), "part_id": pid, "qty_per_unit": rnd.randint(1, 3)})
    bom = pd.DataFrame(bom_rows)

    # orders.csv: 25 orders, a few already shipped (not "open")
    shipped = set(rnd.sample(range(25), 4))
    orders = pd.DataFrame([{
        "order_id": f"O{n + 1:02d}",
        "product_id": rnd.choice(PRODUCTS),
        "quantity": rnd.randint(5, 40),
        "due_day": rnd.randint(8, 28),
        "late_penalty_per_day": rnd.randrange(200, 950, 50),
        "status": "shipped" if n in shipped else "open",
    } for n in range(25)])

    # inventory.csv: stock covers 15 to 50 percent of each part's open demand.
    # P8 has no record on purpose, to exercise "missing stock counts as zero".
    open_orders = orders[orders.status == "open"].merge(bom, on="product_id")
    open_orders["need"] = open_orders.quantity * open_orders.qty_per_unit
    demand = open_orders.groupby("part_id")["need"].sum()
    inv = [{"part_id": pid, "on_hand": int(demand.get(pid, 0) * rnd.uniform(0.15, 0.5))}
           for pid in PARTS if pid != "P8"]
    inventory = pd.DataFrame(inv)

    return {"suppliers": suppliers, "bom": bom, "inventory": inventory, "orders": orders}


if __name__ == "__main__":
    for name, df in build().items():
        df.to_csv(os.path.join(OUT, f"{name}.csv"), index=False)
        print(f"{name:10s} {len(df):3d} rows")
