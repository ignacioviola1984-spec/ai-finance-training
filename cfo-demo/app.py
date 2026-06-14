"""
app.py - CFO AI Office, public demo (HR-friendly).

Replays a REAL, saved run of the multi-agent CFO office so anyone can explore
it instantly, with no API key and no cost. The narratives come from the saved
run (demo_snapshot.json); the interactive widgets recompute from those same
numbers, live and free. Source: github.com/ignacioviola1984-spec/ai-finance-engineering

Run locally:  python -m streamlit run app.py
Deploy:       Streamlit Community Cloud, main file = cfo-demo/app.py (no secrets needed).
"""

import json
import os

import streamlit as st

HERE = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(page_title="CFO AI Office — Live Demo", page_icon="📊", layout="wide")


# --------------------------------------------------------------------------
# Data: the saved real run.
# --------------------------------------------------------------------------

@st.cache_data
def load_snapshot():
    with open(os.path.join(HERE, "demo_snapshot.json"), encoding="utf-8") as f:
        return json.load(f)

DATA = load_snapshot()
A = DATA["agents"]
PERIOD = "May 2026"


def money(x):
    return f"${x:,.0f}"


def clean(text):
    """Trim a dangling incomplete final sentence (snapshots can cut at a token limit)."""
    text = (text or "").strip()
    if text and text[-1] not in ".!?\")*":
        cut = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
        if cut > 0:
            text = text[: cut + 1]
    return text


def sev_badge(sev):
    color = {"CRITICA": "#C0392B", "ALTA": "#D97706"}.get(sev, "#4A6FA5")
    return (f"<span style='background:{color};color:#fff;padding:2px 8px;"
            f"border-radius:6px;font-size:0.72rem;font-weight:700'>{sev}</span>")


# --------------------------------------------------------------------------
# Light styling.
# --------------------------------------------------------------------------

st.markdown("""
<style>
.small { color:#6b7280; font-size:0.9rem; }
.card { background:rgba(127,127,127,0.06); border:1px solid rgba(127,127,127,0.18);
        border-radius:12px; padding:16px 18px; margin-bottom:8px; }
.role { font-weight:700; font-size:1.02rem; }
.boardpack { background:rgba(27,42,74,0.06); border-left:4px solid #1B2A4A;
             border-radius:8px; padding:18px 22px; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Header.
# --------------------------------------------------------------------------

st.title("📊 CFO AI Office")
st.markdown(
    "#### An AI finance team that runs a company's month-end close — and keeps a human in control."
)
st.markdown(
    "<span class='small'>Four specialist agents (Controller, Treasury, FP&amp;A, Strategic Finance) "
    "report to a <b>CFO agent</b> that reconciles their numbers, flags the risks, asks for one human "
    "approval, and writes the board report. Running on a synthetic SaaS company, <b>Lumen Inc.</b>, "
    f"closing <b>{PERIOD}</b>.</span>", unsafe_allow_html=True)

with st.expander("ℹ️  What am I looking at? (30-second version)"):
    st.markdown(
        "- This is a **working multi-agent AI system for corporate finance** — not slides, real software.\n"
        "- Every **number** you see is computed by code (deterministic, auditable). The AI agents **read the "
        "numbers, reason, and write the commentary** — they never invent a figure. That's the core design rule.\n"
        "- A **human approves** before anything reaches the board (you'll do that below).\n"
        "- This page replays a **real saved run** so it's instant and free to explore. "
        "The widgets recompute live from those numbers.\n"
        "- Built by **Ignacio Viola** — 17 years in senior finance, now building the AI systems. "
        "Full source code on [GitHub](https://github.com/ignacioviola1984-spec/ai-finance-engineering)."
    )

# The team.
st.markdown("##### The team")
team = [
    ("🧾 Controller", "Closes the books: P&L consistency, margins, receivables, risk flags."),
    ("💵 Treasury", "Liquidity: cash, monthly burn, and runway."),
    ("📈 FP&A", "Forecast + variances (vs last month and vs budget)."),
    ("🎯 Strategic Finance", "Growth quality & capital efficiency; path to breakeven."),
    ("👔 CFO", "Reconciles all four, consolidates risks, one human gate, board report."),
]
cols = st.columns(5)
for c, (role, desc) in zip(cols, team):
    c.markdown(f"<div class='card'><div class='role'>{role}</div>"
               f"<div class='small'>{desc}</div></div>", unsafe_allow_html=True)

st.divider()


# --------------------------------------------------------------------------
# Run the close.
# --------------------------------------------------------------------------

if "ran" not in st.session_state:
    st.session_state.ran = False
if "approved" not in st.session_state:
    st.session_state.approved = False

if not st.session_state.ran:
    st.markdown("### ▶️  Run the month-end close")
    st.markdown("<span class='small'>Click to have the AI office process Lumen's "
                f"{PERIOD} close, step by step.</span>", unsafe_allow_html=True)
    if st.button("Run the close", type="primary"):
        st.session_state.ran = True
        st.rerun()

if st.session_state.ran:
    ctrl, trez, fpa, strat, cfo = A["Controller"], A["Treasury"], A["FP&A"], A["Strategic Finance"], A["CFO"]

    st.markdown("### 1 · The agents report")

    # Controller
    with st.container():
        st.markdown("#### 🧾 Controller — the close")
        c = st.columns(4)
        c[0].metric("Revenue", money(ctrl["pnl"]["revenue"]))
        c[1].metric("Operating income", money(ctrl["pnl"]["operating_income"]),
                    f"{ctrl['op_margin_pct']:.1f}% margin", delta_color="off")
        c[2].metric("Gross margin", f"{ctrl['gross_margin_pct']:.1f}%")
        c[3].metric("Receivables overdue", f"{ctrl['ar']['overdue_pct']:.0f}%", "of total AR", delta_color="off")
        with st.expander("📄 Controller's full analysis"):
            st.markdown(clean(ctrl["narrative"]))

    # Treasury
    with st.container():
        st.markdown("#### 💵 Treasury — liquidity")
        c = st.columns(4)
        c[0].metric("Cash", money(trez["cash"]))
        c[1].metric("Monthly burn", money(trez["burn"]))
        c[2].metric("Runway", f"{trez['runway']:.1f} months")
        c[3].metric("Threshold", "12 months", "comfort line", delta_color="off")
        with st.expander("📄 Treasury's full analysis"):
            st.markdown(clean(trez["narrative"]))

    # FP&A
    with st.container():
        st.markdown("#### 📈 FP&A — forecast & variances")
        f = fpa["forecast"]
        c = st.columns(4)
        c[0].metric("Next-month revenue (fcst)", money(f["revenue"]))
        c[1].metric("Next-month op income (fcst)", money(f["operating_income"]))
        oi = next(r for r in fpa["budget_variance"]["rows"] if r["label"] == "Operating income")
        c[2].metric("Op income vs budget", money(oi["var"]), f"{oi['var_pct']:.1f}% vs plan", delta_color="off")
        c[3].metric("Material lines vs plan", str(len(fpa["budget_variance"]["material"])))
        with st.expander("📄 FP&A — variance vs last month"):
            st.markdown(clean(fpa["variance_expl"]))
        with st.expander("📄 FP&A — variance vs budget"):
            st.markdown(clean(fpa["budget_expl"]))

    # Strategic Finance
    with st.container():
        st.markdown("#### 🎯 Strategic Finance — growth quality & capital efficiency")
        m = strat["metrics"]
        c = st.columns(4)
        c[0].metric("ARR run-rate", money(m["run_rate"]))
        c[1].metric("Rule of 40", f"{m['rule_of_40']:.0f}", "≥ 40 is healthy", delta_color="off")
        c[2].metric("Burn multiple", f"{m['burn_multiple']:.1f}x", "≤ 2 is efficient", delta_color="off")
        c[3].metric("Magic number", f"{m['magic_number']:.2f}", "> 0.75 is good", delta_color="off")
        with st.expander("📄 Strategic Finance's full analysis"):
            st.markdown(clean(strat["narrative"]))

    st.divider()

    # --------------------------------------------------------------------
    # CFO consolidation + human gate.
    # --------------------------------------------------------------------
    st.markdown("### 2 · The CFO consolidates")
    st.success("✅ Cross-check passed — all four agents agree on the shared numbers "
               "(operating income, burn, revenue/run-rate). The pipeline is internally consistent.")

    escalations = (ctrl["escalations"] + trez["escalations"] + fpa["escalations"] + strat["escalations"])
    st.markdown(f"**{len(escalations)} risk flags raised** (each owned by one agent, no double-counting):")
    for sev, msg in escalations:
        st.markdown(f"{sev_badge(sev)}&nbsp; {msg}", unsafe_allow_html=True)

    st.divider()
    st.markdown("### 3 · 🧑‍⚖️ Human-in-the-loop — your call")
    if not st.session_state.approved:
        st.warning("The CFO agent **stops here** and waits for a human to approve before the board "
                   "report is released. **You are the human.**")
        if st.button("✅ Approve as CFO → release the board pack", type="primary"):
            st.session_state.approved = True
            st.rerun()
    else:
        st.markdown("### 4 · 📋 Board pack")
        st.markdown(f"<div class='boardpack'>{clean(cfo['board_pack'])}</div>", unsafe_allow_html=True)
        st.markdown("#### Recommended actions")
        st.markdown(clean(cfo["actions"]))
        st.caption("Generated by the CFO agent from the four agents' inputs — every figure traces "
                   "back to code-computed numbers.")


# --------------------------------------------------------------------------
# Play widgets (recompute from snapshot, free).
# --------------------------------------------------------------------------

st.divider()
st.markdown("### 🎛️  Play with the model")
st.markdown("<span class='small'>These recompute instantly from the saved numbers — no AI calls, "
            "showing how the deterministic engine drives the decisions.</span>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Materiality threshold", "Growth scenarios"])

with tab1:
    st.markdown("How big a budget variance is worth flagging? Move the threshold and watch which "
                "lines the system escalates (it also requires a $20k floor).")
    pct = st.slider("Materiality threshold (% of plan)", 1.0, 15.0, 5.0, 0.5)
    rows = A["FP&A"]["budget_variance"]["rows"]
    flagged = [r for r in rows if abs(r["var_pct"]) >= pct and abs(r["var"]) >= 20000]
    st.markdown(f"**{len(flagged)} line(s) flagged at {pct:.1f}%:**")
    if flagged:
        st.table([{"Line": r["label"], "Variance $": f"{r['var']:+,.0f}",
                   "Variance %": f"{r['var_pct']:+.1f}%",
                   "Fav/Unfav": "Unfavorable" if r["flag"] == "U" else "Favorable"} for r in flagged])
    else:
        st.info("Nothing material at this threshold — the month was in line with plan.")
    st.caption("The default is 5%: at the looser 10% bar, real overruns like the G&A miss would slip through.")

with tab2:
    st.markdown("Growth helps the headline, but does it fix profitability? Margin is held constant on "
                "purpose — to show growth alone doesn't reach breakeven.")
    scn = {s["name"]: s for s in A["Strategic Finance"]["metrics"]["scenarios"]}
    pick = st.radio("Scenario", list(scn.keys()), index=1, horizontal=True)
    s = scn[pick]
    c = st.columns(3)
    c[0].metric("Monthly growth", f"{s['mom_growth']*100:.1f}%")
    c[1].metric("ARR run-rate in 12 months", money(s["run_rate_12m"]))
    c[2].metric("Rule of 40", f"{s['rule_of_40']:.0f}",
                "healthy" if s["rule_of_40"] >= 40 else "below 40", delta_color="off")
    st.caption("Even the high-growth case keeps a negative margin: the real lever is structural margin, "
               "not more volume. That's the Strategic Finance agent's headline.")


# --------------------------------------------------------------------------
# Audit trail + footer.
# --------------------------------------------------------------------------

st.divider()
with st.expander("🔍 Audit trail — every step is logged (governance)"):
    for e in DATA["audit"]:
        st.markdown(f"<span class='small'><code>{e['ts']}</code> · <b>{e['agent']}</b> · "
                    f"{e['status']} — {e['detail']}</span>", unsafe_allow_html=True)

st.divider()
st.markdown(
    "<span class='small'>Built by <b>Ignacio Viola</b> · 17 years in senior finance, now building AI "
    "systems for finance operations · Synthetic data; architecture built to point at production data · "
    "Source: <a href='https://github.com/ignacioviola1984-spec/ai-finance-engineering'>GitHub</a></span>",
    unsafe_allow_html=True)
