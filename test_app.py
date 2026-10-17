"""Click through the app without a browser.   python test_app.py"""
import json
import os

from streamlit.testing.v1 import AppTest

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN = json.load(open(os.path.join(HERE, "scenarios", "scenarios.json")))


def fresh():
    at = AppTest.from_file(os.path.join(HERE, "app.py"), default_timeout=120).run()
    assert not at.exception, at.exception
    return at


def press(at, key):
    at.button(key=key).click().run()
    assert not at.exception, at.exception


def scenario(at, sid):
    at.selectbox(key="scenario_pick").select_index(next(i for i, s in enumerate(SCEN) if s["id"] == sid)).run()
    press(at, "run_scenario")


def example(at, label):
    at.button_group(key="example").set_value(label).run()
    assert not at.exception, at.exception


def page(at):
    return " ".join(m.value for m in at.markdown) + " " + " ".join(c.value for c in at.caption)


# opening state explains what to do, and the test-case results are there
at = fresh()
assert "Nothing has run yet" in page(at)
assert "20 of 20</b> test cases ended the way they should" in page(at)

# report a delay, run, approve
press(at, "run_build")
assert "A recovery plan is ready for your decision" in page(at)
assert "less than the manual fix" in page(at)
press(at, "approve")
assert "Plan approved" in page(at) and "You</span> <span class=\"e\">approved the plan" in page(at)

# reject once: the simpler plan is offered with an honest cost line, then approve it
at = fresh()
press(at, "run_build")
at.text_input(key="note_0").set_value("too many rush orders").run()
press(at, "reject")
p = page(at)
assert "The manual fix is ready for your decision" in p
assert "more than the optimized plan" in p and "0 less than" not in p
press(at, "approve")
assert "Plan approved" in page(at)

# reject twice: no third plan, so it goes to a person, and the page says the person rejected it
at = fresh()
press(at, "run_build")
press(at, "reject")
press(at, "reject")
p = page(at)
assert "Both plans were rejected" in p and "Critic kept finding" not in p
assert not any(b.key == "approve" for b in at.button)

# the day-by-day view can switch to what happens if nobody acts
at = fresh()
press(at, "run_build")
at.button_group(key="view").set_value("If nobody acts").run()
assert not at.exception and "days late" in page(at)

# examples
at = fresh()
example(at, "A mistake the Critic catches")
assert "The Critic kept finding mistakes" in page(at) and "never approved" in page(at)
assert not any(b.key == "approve" for b in at.button)
at = fresh()
example(at, "Two delays at once")
assert "received a second alert" in page(at) and "ready for your decision" in page(at)

# exception paths through the test-case picker
for sid, words in (("S13", "could not be used"), ("S12", "only a backup source"), ("S11", "every order still ships on time")):
    at = fresh()
    scenario(at, sid)
    assert words in page(at), (sid, page(at)[:300])

# second supplier toggle builds two alerts
at = fresh()
at.toggle(key="second").set_value(True).run()
press(at, "run_build")
assert "received a second alert" in page(at)

# planted fault from the testing options
at = fresh()
at.selectbox(key="fault_pick").select_index(2).run()
press(at, "run_build")
assert "The Critic kept finding mistakes" in page(at)

print("app checks passed")
