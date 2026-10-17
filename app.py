"""Streamlit front end for the multi-agent disruption replanner.

    streamlit run app.py
"""
import html

import streamlit as st

from tools.data_loader import load_data
from app_logic import (FAULTS, RULE_TEXT, CATEGORY, OUTCOME, MANUAL_EXPLAINED, describe_alert, log_line, execute, load_scenarios, supplier_label, part_label,
                       supplier_name, part_name, parts_supplied_by, has_plan, plan_kind, compare, nothing_only,
                       verdict, summary, next_step, action_summary, action_sentence, plan_table, impact_tables,
                       timeline_svg, cost_svg, results, results_svg, results_table, plural, money)

st.set_page_config(page_title="Disruption Replanner", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root { --ink:#1C2830; --steel:#3E6A8A; --signal:#F2B705; --late:#C23B22; --ok:#2E7D5B;
        --rule:#D3D9D5; --faint:#E7EBE8; --muted:#66737C; --paper:#F5F6F3; --card:#FFFFFF;
        --stripes: repeating-linear-gradient(-45deg, var(--signal) 0 7px, var(--ink) 7px 12px); }
header[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
[data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
.block-container { max-width:1060px; padding-top:2.2rem; padding-bottom:5rem; }

.mast { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; flex-wrap:wrap;
        padding-bottom:.9rem; border-bottom:1px solid var(--rule); margin-bottom:2.2rem; }
.mast .brand { font-weight:700; font-stretch:85%; font-size:1.02rem; color:var(--ink); }
.mast .meta { font-size:.85rem; color:var(--muted); }

h1.hero { font-stretch:70%; font-weight:800; font-size:clamp(2.6rem, 6vw, 4.4rem); line-height:.92;
          letter-spacing:-.005em; margin:0 0 .9rem; padding:0; color:var(--ink); }
.hz { height:10px; width:132px; background:var(--stripes); border-radius:2px; margin-bottom:1.1rem; }
.lede { font-size:1.08rem; line-height:1.55; max-width:62ch; color:#33424C; margin:0 0 2rem; }

.st-key-composer { background:var(--card); border:1px solid var(--rule); border-radius:6px; padding:1.3rem 1.4rem 1.1rem; }
h3.ch { font-stretch:80%; font-weight:750; font-size:1.35rem; margin:0 0 .2rem; padding:0; }
.st-key-composer .hint { color:var(--muted); font-size:.92rem; margin:0 0 .4rem; }
.st-key-run_build button { background:var(--ink); border-color:var(--ink); font-weight:650; }
.st-key-run_build button:hover { background:#2C3D48; border-color:#2C3D48; }

.alerts { margin:.5rem 0 0; color:var(--muted); font-size:.9rem; }
.alerts b { color:var(--ink); font-weight:600; }

.empty { margin-top:2.4rem; color:var(--muted); font-size:1rem; max-width:60ch; }

.verdict { margin-top:2.6rem; }
.verdict .vbar { height:6px; width:64px; border-radius:2px; margin-bottom:.9rem; background:var(--muted); }
.verdict.wait .vbar { background:var(--stripes); animation: draw .7s ease-out both; }
.verdict.ok .vbar { background:var(--ok); }
.verdict.stop .vbar { background:var(--late); }
@keyframes draw { from { width:0; } to { width:64px; } }
@media (prefers-reduced-motion: reduce) { .verdict.wait .vbar { animation:none; } }
.verdict h2 { font-stretch:75%; font-weight:780; font-size:clamp(1.8rem, 3.4vw, 2.5rem); line-height:1.02; margin:0 0 .8rem; padding:0; }
.verdict p { font-size:1.04rem; line-height:1.6; max-width:64ch; margin:0 0 .6rem; }
.verdict p.next { color:var(--muted); font-size:.95rem; }

.st-key-decide { margin-top:2.6rem; background:var(--card); border:1px solid var(--rule); border-radius:6px; padding:1.1rem 1.2rem; }
.st-key-decide h4 { font-stretch:85%; font-weight:700; font-size:1.1rem; margin:0 0 .3rem; padding:0; }
.st-key-approve button { background:var(--ok); border-color:var(--ok); font-weight:650; }
.st-key-approve button:hover { background:#256A4C; border-color:#256A4C; }

h3.sec { font-stretch:80%; font-weight:750; font-size:1.55rem; margin:3rem 0 .3rem; padding:0; }
p.sub { color:var(--muted); font-size:.95rem; margin:0 0 .8rem; max-width:70ch; }
.legend { display:flex; flex-wrap:wrap; gap:1.2rem; font-size:.86rem; color:var(--muted); margin:.2rem 0 .6rem; }
.legend span { display:inline-flex; align-items:center; gap:.45rem; }
.legend i { display:inline-block; }
.legend .due { width:3px; height:13px; background:var(--ink); }
.legend .dot { width:10px; height:10px; border-radius:50%; }
.legend .band { width:26px; height:10px; background:var(--stripes); border-radius:2px; }
.legend .sw { width:14px; height:10px; }

svg text { font-family:inherit; font-variant-numeric:tabular-nums; }
svg .ax { font-size:11px; fill:var(--muted); }
svg .bl { font-size:12px; font-weight:600; fill:var(--ink); }
svg .oid { font-size:12px; fill:var(--ink); }
svg .lt { font-size:11.5px; font-weight:650; fill:var(--late); }
svg .row .hit { fill:transparent; }
svg .row:hover .hit { fill:rgba(62,106,138,.08); }
svg .cl { font-size:15px; font-weight:500; fill:var(--ink); }
svg .cl.on { font-weight:750; }
svg .cs { font-size:12px; fill:var(--muted); }
svg .cv { font-size:16px; font-weight:600; fill:var(--muted); }
svg .cv.on { font-weight:800; fill:var(--ink); }
svg .ct { font-size:12px; font-weight:650; fill:var(--steel); }
svg .rn { font-size:12.5px; fill:var(--ink); }
svg .rv { font-size:12px; font-weight:700; fill:var(--ink); }

ul.acts { list-style:none; padding:0; margin:.4rem 0 1rem; }
ul.acts li { display:grid; grid-template-columns:8.5rem 1fr auto; gap:1rem; align-items:baseline;
             padding:.65rem 0; border-top:1px solid var(--faint); margin:0; }
ul.acts li:first-child { border-top:none; }
ul.acts .m { font-size:.82rem; font-weight:650; }
ul.acts .m.stock { color:var(--ok); } ul.acts .m.alternate { color:var(--steel); }
ul.acts .m.expedite { color:#A86F00; } ul.acts .m.wait { color:var(--late); }
ul.acts .c { color:var(--muted); font-size:.88rem; font-variant-numeric:tabular-nums; }

.msg { background:var(--card); border:1px solid var(--rule); border-radius:4px; padding:.8rem 1rem; margin-bottom:.6rem; }
.msg .to { font-size:.85rem; font-weight:650; color:var(--steel); margin-bottom:.25rem; }

ol.log { padding-left:1.6rem; margin:.4rem 0 1rem; }
ol.log li { padding:.28rem 0; line-height:1.45; }
ol.log li::marker { color:var(--muted); font-size:.85rem; font-variant-numeric:tabular-nums; }
ol.log .a { font-weight:650; }
ol.log .d { color:var(--muted); }
ol.log li.bad .a, ol.log li.bad .e { color:var(--late); }

p.ct { font-weight:650; margin:1.6rem 0 .4rem; }
.facts p { font-size:1.08rem; line-height:1.6; max-width:66ch; margin:0 0 .7rem; }
.facts b { font-weight:750; }
ul.checks { list-style:none; padding:0; margin:.3rem 0 0; }
ul.checks li { display:flex; justify-content:space-between; gap:1rem; padding:.55rem 0; border-top:1px solid var(--faint); margin:0; }
ul.checks li:first-child { border-top:none; }
ul.checks .n { font-weight:700; font-variant-numeric:tabular-nums; white-space:nowrap; }
ul.checks .w { color:var(--muted); font-size:.88rem; }

[data-testid="stTabs"] button[role="tab"] p { font-size:.98rem; font-weight:550; }
[data-testid="stExpander"] summary p { font-weight:550; }
.chart { overflow-x:auto; }
@media (max-width: 640px) { ul.acts li { grid-template-columns:1fr; gap:.15rem; } .chart svg { min-width:760px; } }
</style>
""", unsafe_allow_html=True)


def esc(x):
    return html.escape(str(x))


def log_html(state):
    items = []
    for e in state["log"]:
        who, what, detail, bad = log_line(e)
        tail = f': <span class="d">{esc(detail)}</span>' if detail else ""
        items.append(f'<li class="{"bad" if bad else ""}"><span class="a">{esc(who)}</span> '
                     f'<span class="e">{esc(what)}</span>{tail}</li>')
    return f'<ol class="log">{"".join(items)}</ol>'


def chart(svg):
    """Inline SVG. On a phone it keeps a readable size and scrolls sideways instead of shrinking."""
    st.markdown(f'<div class="chart">{svg}</div>', unsafe_allow_html=True)


@st.cache_data
def get_data():
    return load_data()


@st.cache_data
def get_scenarios():
    return load_scenarios()


@st.cache_data(show_spinner="Running all 20 test cases through the agents...")
def get_results():
    return results(load_data())


data, scenarios = get_data(), get_scenarios()
ss = st.session_state
ss.setdefault("run", None)
SCEN = {s["id"]: s for s in scenarios}
EXAMPLES = {"One late supplier": "S02", "Two delays at once": "S18", "A mistake the Critic catches": "S20"}


# ------------------------------------------------------------------ actions (run as button callbacks)

def start(alerts, late, fault):
    ss.run = {"alerts": alerts, "late": late, "fault": fault, "decisions": []}
    ss.run["state"] = execute(data, alerts, late, fault, [])


def start_scenario(sid):
    sc = SCEN[sid]
    start(sc["alerts"], [sc["late_alert"]] if sc.get("late_alert") else [], sc.get("fault"))


def run_from_form():
    alerts = [f"{ss.sup} delays {ss.part} by {ss.delay} days"]
    late = [f"{ss.sup2} delays {ss.part2} by {ss.delay2} days"] if ss.get("second") else []
    start(alerts, late, FAULTS[ss.get("fault_pick", "No planted mistake")])


def run_example():
    pick = ss.get("example")
    if pick:
        start_scenario(EXAMPLES[pick])
        ss.example = None


def decide(choice):
    run = ss.run
    note = ss.get(f"note_{len(run['decisions'])}", "") or "no reason given"
    run["decisions"].append((choice, note if choice == "reject" else ""))
    run["state"] = execute(data, run["alerts"], run["late"], run["fault"], run["decisions"])


# ------------------------------------------------------------------ masthead and intro
st.markdown('<div class="mast"><span class="brand">Disruption Replanner</span>'
            '<span class="meta">A test plant with made-up data: 4 suppliers, 8 parts, 25 customer orders</span></div>'
            '<h1 class="hero">When a supplier<br>runs late</h1><div class="hz"></div>'
            '<p class="lede">Report the delay. Four agents work out which customer orders slip, find the cheapest '
            'way to recover, check every number again from scratch, and then wait for you. Nothing is sent '
            'until you approve it.</p>', unsafe_allow_html=True)

# ------------------------------------------------------------------ composer
sup_ids = sorted(data["suppliers"].supplier_id.unique())
with st.container(key="composer"):
    st.markdown('<h3 class="ch">Report a delay</h3>'
                '<p class="hint">The part list only shows parts this supplier normally sends us. Those are the '
                'only shipments that can actually be late.</p>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1.15, 1.15, 1.3], gap="medium")
    sup = c1.selectbox("Late supplier", sup_ids, index=1, format_func=supplier_label, key="sup")
    c2.selectbox("Which part is late", parts_supplied_by(data, sup), format_func=part_label, key="part")
    c3.slider("Days late", 1, 60, 25, key="delay")

    if st.toggle("Another supplier slips while the agents are still planning", key="second"):
        d1, d2, d3 = st.columns([1.15, 1.15, 1.3], gap="medium")
        sup2 = d1.selectbox("Second late supplier", sup_ids, index=0, format_func=supplier_label, key="sup2")
        d2.selectbox("Part", parts_supplied_by(data, sup2), format_func=part_label, key="part2")
        d3.slider("Days late", 1, 60, 35, key="delay2")

    b1, _, b3 = st.columns([1, 2.3, .9], vertical_alignment="center", gap="medium")
    b1.button("Plan the recovery", type="primary", key="run_build", on_click=run_from_form, width="stretch")
    with b3.popover("Testing", width="stretch"):
        st.selectbox("Plant a mistake to see if the Critic catches it", list(FAULTS), key="fault_pick")
        st.caption("Only used when you press Plan the recovery. The examples and test cases set this themselves.")
    st.pills("Or run a ready-made example", list(EXAMPLES), key="example", on_change=run_example)

run = ss.run
state = run["state"] if run else None

# ------------------------------------------------------------------ result
if not state:
    st.markdown('<p class="empty">Nothing has run yet. Pick a supplier, a part and how late they are, then press '
                'Plan the recovery. Or run one of the ready-made examples below it.</p>', unsafe_allow_html=True)
else:
    status = state["status"]
    headline, tone = verdict(state)
    plan_ready = has_plan(state)
    has_impact = bool(state.get("impact") and state["impact"]["parts"])
    cmp = compare(state, data) if plan_ready else (nothing_only(state, data) if has_impact else None)

    left, right = st.columns([1.75, 1], gap="large")
    with left:
        nxt = next_step(state)
        st.markdown(f'<div class="verdict {tone}"><div class="vbar"></div><h2>{esc(headline)}</h2>'
                    f'<p>{esc(summary(state, data, cmp if plan_ready else None))}</p>'
                    + (f'<p class="next">{esc(nxt)}</p>' if nxt else "") + '</div>', unsafe_allow_html=True)
    with right:
        with st.container(key="decide"):
            if status == "awaiting_approval":
                st.markdown("<h4>Your decision</h4>", unsafe_allow_html=True)
                st.text_input("Reason, if you reject", key=f"note_{len(run['decisions'])}",
                              placeholder="For example: too many rush orders")
                a1, a2 = st.columns(2)
                a1.button("Approve", type="primary", key="approve", on_click=decide, args=("approve",), width="stretch")
                a2.button("Reject", key="reject", on_click=decide, args=("reject",), width="stretch")
            else:
                st.markdown("<h4>" + {"released": "Approved", "escalated": "Handed to a person"}.get(status, "No decision needed")
                            + "</h4>", unsafe_allow_html=True)
            got = "".join(f"<br><b>{esc(describe_alert(a))}</b>" for a in run["alerts"])
            late = "".join(f"<br><b>{esc(describe_alert(a))}</b>" for a in run["late"])
            st.markdown(f'<p class="alerts">The alert:{got}' + (f'<br><br>Then, while planning:{late}' if late else "") + "</p>",
                        unsafe_allow_html=True)

    if has_impact:
        st.markdown('<h3 class="sec">Every affected order, day by day</h3>', unsafe_allow_html=True)
        if plan_ready:
            view = st.segmented_control("Show", ["With the plan", "If nobody acts"], default="With the plan",
                                        key="view", label_visibility="collapsed") or "With the plan"
        else:
            view = "If nobody acts"
        st.markdown('<div class="legend"><span><i class="band"></i>the late shipment, from its old to its new arrival day</span>'
                    '<span><i class="due"></i>due day</span>'
                    '<span><i class="dot" style="background:var(--ok)"></i>ships on time</span>'
                    '<span><i class="dot" style="background:var(--late)"></i>ships late</span></div>',
                    unsafe_allow_html=True)
        chart(timeline_svg(state, data, "nothing" if view == "If nobody acts" else "plan", cmp))

    if plan_ready:
        st.markdown('<h3 class="sec">What each option costs</h3>'
                    f'<p class="sub">Parts plus late penalties, worked out the same way for all three. {MANUAL_EXPLAINED} '
                    'The darker bar is the plan the agents put forward.</p>'
                    '<div class="legend"><span><i class="sw" style="background:var(--steel)"></i>parts</span>'
                    '<span><i class="sw" style="background:var(--late)"></i>late penalties</span></div>',
                    unsafe_allow_html=True)
        chart(cost_svg(cmp, status))

        st.write("")
        t_do, t_send, t_how, t_orders = st.tabs(["What to do", "What to send", "How the agents worked", "Order details"])
        with t_do:
            if status == "escalated":
                st.caption("This plan was never approved. It is shown so whoever takes over can see where things stood.")
            items = "".join(f'<li><span class="m {a["mode"]}">{esc(a["label"])}</span><span>{esc(action_sentence(a))}</span>'
                            f'<span class="c">{money(a["cost"]) if a["cost"] else "already paid for"}</span></li>'
                            for a in action_summary(state, data))
            st.markdown(f'<ul class="acts">{items}</ul>', unsafe_allow_html=True)
            with st.expander("Every unit, order by order"):
                st.dataframe(plan_table(state), hide_index=True, width="stretch")
        with t_send:
            if state.get("messages"):
                for m in state["messages"]:
                    to = (f"To {supplier_name(m['to'])} ({m['to']})" if m["kind"] == "supplier"
                          else f"To the customer for order {m['to']}")
                    st.markdown(f'<div class="msg"><div class="to">{esc(to)}</div>{esc(m["text"])}</div>', unsafe_allow_html=True)
                st.caption("Customers only hear from us if their order will be late. The Critic checks every number "
                           "in these messages against the plan." + (" These were not sent." if status == "escalated" else ""))
            else:
                st.caption("No messages are needed for this plan.")
        with t_how:
            st.markdown(log_html(state), unsafe_allow_html=True)
            v = state.get("critic")
            if v:
                st.markdown("**The Critic's checks on this plan**")
                st.dataframe([{"Check": RULE_TEXT[r], "Result": "passed" if x["ok"] else "failed",
                               "What it found": "; ".join(x["issues"])[:200]} for r, x in v["rules"].items()],
                             hide_index=True, width="stretch")
        with t_orders:
            imp = state["impact"]
            for pid, rows in impact_tables(state).items():
                p = imp["parts"][pid]
                st.markdown(f"**{part_name(pid)}** from {supplier_name(p['supplier_id'])}: stock covers {p['on_hand']} of "
                            f"the {p['total_need']} units needed, and the shipment now lands on day "
                            f"{p['delayed_arrival']} instead of day {p['normal_arrival']}.")
                st.dataframe(rows, hide_index=True, width="stretch")
    elif state.get("log"):
        with st.expander("How the agents got here"):
            st.markdown(log_html(state), unsafe_allow_html=True)

# ------------------------------------------------------------------ results across the test cases
st.markdown('<h3 class="sec" style="margin-top:4.5rem">How it does across 20 test cases</h3>'
            '<p class="sub">Worked out again every time the app starts, so these numbers always match the current data.</p>',
            unsafe_allow_html=True)
res = get_results()
cost = res["cost"]
big = res["big"]
facts = [f"<b>{res['as_expected']} of {res['n']}</b> test cases ended the way they should.",
         f"<b>{len(cost)}</b> of them needed a new plan. The optimized plan was cheaper than the manual fix "
         + ("<b>every time</b>" if res["cheaper"] == len(cost) else f"in <b>{res['cheaper']}</b> of them")
         + f". The typical saving was <b>{res['median']:.0%}</b>, and it ranged from {res['low']:.0%} to {res['high']:.0%}."
         + (f" The {plural(len(big), 'case')} that saved more than half were long delays, where the manual fix ends up "
            "waiting for the late shipment and paying heavy penalties." if big else ""),
         f"Across those cases, <b>{res['opt_late']}</b> orders shipped late with the optimized plan and "
         f"<b>{res['base_late']}</b> with the manual fix."
         + (f" In {plural(len(res['more_late']), 'case')} the optimized plan let more orders run late, because paying "
            "those penalties cost less than rushing the parts or buying them elsewhere." if res["more_late"] else ""),
         MANUAL_EXPLAINED]
r1, r2 = st.columns([1.7, 1], gap="large")
with r1:
    st.markdown('<div class="facts">' + "".join(f"<p>{f}</p>" for f in facts) + "</div>", unsafe_allow_html=True)
with r2:
    st.markdown('<ul class="checks">' + "".join(
        f'<li><span>{esc(CATEGORY[k][0])}<br><span class="w">{esc(CATEGORY[k][1])}</span></span>'
        f'<span class="n">{g["ok"]} of {g["n"]}</span></li>'
        for k, g in res["groups"].items()) + "</ul>", unsafe_allow_html=True)

st.markdown("<p class='ct'>How much cheaper the optimized plan was than the manual fix, one bar per test case. "
            f"The dashed line marks the typical saving of {res['median']:.0%}.</p>", unsafe_allow_html=True)
chart(results_svg(res))

with st.expander("Run one test case yourself"):
    t1, t2 = st.columns([3, 1], vertical_alignment="bottom")
    pick = t1.selectbox("Test case", scenarios, format_func=lambda x: f"{x['id']}: {x['name']}", key="scenario_pick")
    t2.button("Run it", key="run_scenario", on_click=start_scenario, args=(pick["id"],), width="stretch")
    want = pick.get("expect_faulted", pick["expect"])
    st.caption("The alert: " + "; ".join(describe_alert(a) for a in pick["alerts"])
               + (f". Then, while planning: {describe_alert(pick['late_alert'])}" if pick.get("late_alert") else "")
               + f". Expected result: {OUTCOME.get(want, want)}. The result appears at the top of the page.")
with st.expander("Every test case in one table"):
    st.dataframe(results_table(res), hide_index=True, width="stretch")
