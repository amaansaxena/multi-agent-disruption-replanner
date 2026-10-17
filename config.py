"""Shared constants. Change a number here and every tool picks it up."""

SEED = 42

# How each way of covering a late part is priced and limited.
SPOT_PREMIUM = 1.10        # backup supplier charges 10% over list price
EXPEDITE_PREMIUM = 1.35    # rushing the delayed supplier costs 35% more
EXPEDITE_CAPACITY = 0.5    # a rush can cover at most half of that supplier's capacity

# Planner's alert check (slide 8: "a delay outside 1 to 60 days").
MIN_DELAY = 1
MAX_DELAY = 60

STOCK = "STOCK"            # supplier_id used in plans for units taken from inventory
MONEY_TOL = 0.01
MAX_RETRIES = 2            # re-plans allowed before the case goes to a human
