"""Deliberate faults, used to prove the Critic catches them (slide 9)."""
import copy


def wrong_total_once(solver):
    """The solver reports a total that is 500 too high on its first call only."""
    calls = {"n": 0}

    def wrapped(impact, data):
        res = copy.deepcopy(solver(impact, data))
        calls["n"] += 1
        if calls["n"] == 1 and res.get("claimed_total") is not None:
            res["claimed_total"] += 500
        return res
    return wrapped


def wrong_message_always(drafter):
    """The drafter quotes one unit too many to the first supplier, every time."""
    def wrapped(result, impact, data, feedback=None):
        msgs = copy.deepcopy(drafter(result, impact, data, feedback=feedback))
        for m in msgs:
            if m["kind"] == "supplier":
                old = m["numbers"]["qty"]
                m["numbers"]["qty"] = old + 1
                m["text"] = m["text"].replace(f" {old} units", f" {old + 1} units", 1)
                break
        return msgs
    return wrapped


def apply_fault(name, solver, drafter):
    if name == "wrong_total_once":
        return wrong_total_once(solver), drafter
    if name == "wrong_message_always":
        return solver, wrong_message_always(drafter)
    return solver, drafter
