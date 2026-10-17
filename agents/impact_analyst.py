"""Impact Analyst agent: which orders slip, and by how much."""
from tools.impact import analyse_impact
from agents.state import entry


def make_impact_analyst(data):
    def node(state):
        impact = analyse_impact(data, state["alerts"])
        if not impact["parts"]:
            return {"impact": impact, "status": "no_impact", "reason": "The part affects no open orders",
                    "log": [entry("Impact Analyst", "no impact", "no open order is waiting on that shipment")]}
        if impact["shortfall_total"] == 0:
            return {"impact": impact, "status": "no_shortfall",
                    "reason": "Stock and the delayed shipment still meet every due date",
                    "log": [entry("Impact Analyst", "no shortfall", "stock and the delayed shipment still arrive before every due date")]}
        return {"impact": impact, "status": "working",
                "log": [entry("Impact Analyst", "impact found",
                              f"{len(impact['orders_at_risk'])} orders will ship late, {impact['shortfall_total']:,} units will not "
                              f"arrive in time, {impact['penalty_if_nothing_done']:,} in penalties if nobody acts")]}
    return node
