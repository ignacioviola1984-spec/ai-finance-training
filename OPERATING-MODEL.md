# The operating model — stages, controls & human-in-the-loop

This is the canonical description of *how the close actually runs*. It is not "a
pipeline with some reviews bolted on": the month-end close is modelled as an
explicit, end-to-end sequence of **stages**, and every stage is a first-class
object with its own controls. The engine is [`cfo-office/stages.py`](cfo-office/stages.py);
the maker-checker layer is [`cfo-office/review.py`](cfo-office/review.py); the
final consolidation is [`cfo-office/cfo_orchestrator.py`](cfo-office/cfo_orchestrator.py).

## Why a staged model (the design principle)

A single generalist CFO **cannot** competently approve the entire operational
flow of a finance function. A CFO plays by ear on technical accounting, on tax,
on revenue recognition, on controls. Delegating eight agents to do all the work
and then asking one human to rubber-stamp it is a *vision of the future*, not
something that survives contact with a real company or a real auditor.

So the model that actually works is **two-tier human-in-the-loop (maker-checker)**:

1. **First line — one domain expert per function.** The agent is the *maker*; the
   person with deep expertise in that area is the *checker* who validates with
   real judgment and signs. The Tax Manager signs tax. The Treasurer signs
   treasury. Technical Accounting signs the financial statements. Nobody signs
   something they don't understand.
2. **Second line — the CFO's final sign-off.** Once every function is signed off
   *and* the numbers reconcile across agents, the CFO signs off on the
   **consolidated** board pack and the **material / cross-cutting** items — not a
   pseudo-review of every line (that's what the first line is for).

Underneath both human tiers sits a **deterministic control layer in code**: hard
gates that do not depend on anyone's opinion (the books reconcile, the statements
articulate and foot, there are zero integrity failures, the audit opinion is not
adverse). The model cannot pass a stage just because someone clicked "approve".

## Each stage has four parts

| Part | What it is | Where |
|---|---|---|
| **Maker** | The agent(s) that do the work | the function's `*_agent.py` |
| **Deterministic control** | A code-level gate that must hold (not the model) | `_ctrl_*` in `stages.py` |
| **Checker (HITL)** | Sign-off by the domain expert for that function | `review.review()` |
| **On reject** | **Rework** (re-run + re-review, capped) → then **block** | `run_stage()` |

`MAX_ATTEMPTS = 2`: a stage gets one run plus one rework cycle. If it still can't
pass its control *and* get signed off, the stage is **BLOCKED** — and a blocked
stage halts the **whole close**. You do not build a board pack on top of an
un-controlled, un-reviewed stage. The CFO's final gate is contingent on every
stage having passed.

## The stages, end to end

| # | Stage | Maker (agent) | Deterministic control (code) | Checker — first-line sign-off |
|---|---|---|---|---|
| 1 | Controllership review | Controller | — (no code gate; numbers re-checked downstream) | Accounting Manager |
| 2 | Treasury & liquidity | Treasury | — | Treasurer |
| 3 | Working capital & tax | Accounts Receivable, Accounts Payable, Tax | — | Collections / AR Manager · AP Manager · Tax Manager |
| 4 | Close & financial statements | Accounting & Close, Financial Reporting | **subledgers tie to the GL, the balance sheet balances (\|A−L−E\| ≤ 1), and the cash-flow statement foots to ΔCash** | Accounting Manager · Technical Accounting / Reporting Manager |
| 5 | Planning & analysis (FP&A) | FP&A | — | FP&A Director |
| 6 | Strategic finance | Strategic Finance | — | VP Finance / Head of Strategic Finance |
| 7 | Internal controls | Internal Controls | **zero integrity-control failures** (trial balance, FX, cutoff, authorizations) | Internal Controls Manager |
| 8 | Independent audit | Audit | **audit opinion is not adverse** | Internal Audit Lead |

Stages 1–3, 5 and 6 have no code-level gate of their own: their numbers are
re-derived and cross-checked by the close (stage 4), the controls testing (stage
7) and the independent audit (stage 8), so a bad number there cannot reach the
board without tripping a later hard gate. Every stage, with or without a code
gate, still requires its domain-expert sign-off.

## After the stages: consolidation and the CFO gate

Once all eight stages pass, the orchestrator runs the second tier:

1. **Cross-checks (deterministic, global).** Six checks prove the agents agree on
   the shared numbers — they all derive from `finance_core`, so they *must*
   match, and this catches future drift before it reaches the board:
   - Controller operating income = FP&A's actual operating income
   - Treasury burn = −operating income (when there's an operating loss)
   - Strategic Finance run-rate ÷ 12 = Controller revenue
   - Administration's AR = Controller's AR
   - Financial Reporting net income = Controller operating income
   - Financial Reporting balance-sheet cash = Treasury cash
2. **Escalations** are consolidated from all eight top-level agents and ordered by
   severity (CRITICAL → HIGH). Each risk has a **single owner** — no
   double-counting (e.g. the operating loss is owned by the Controller, not also
   re-escalated by FP&A).
3. **CFO final sign-off.** Precondition: the first line must be 100% signed off.
   The CFO does **not** re-review each operational detail; the CFO confirms the
   first line cleared, reviews the material / cross-cutting items, and signs the
   consolidated board pack. Only then are the board pack and actions written.

## What is recorded (governance / audit trail)

Every stage transition (`running`, `stage REWORK`, `stage PASS`, `stage BLOCKED`)
and every sign-off (reviewer, decision, free-text correction note, timestamp,
and **mode**) is written to the shared state and the audit trail. Each review
records `mode = "human"` or `mode = "auto"`: when there is no reviewer at the
console (snapshot generation, CI, piped input) the workflow auto-approves so it
never hangs, **but the record is explicitly marked `auto`** and is never passed
off as a real human sign-off. The block-on-reject behaviour is the same in both
modes — only the keystroke is simulated, not the control.

## What this is and isn't

- **Is:** a realistic, production-shaped operating model — staged, with
  deterministic controls and a domain expert accountable for each function, and a
  CFO accountable for the consolidated result.
- **Isn't (yet):** wired to production data (the figures are synthetic), and the
  public demo auto-approves the human steps. Materiality-based routing of the
  HITL, regulatory compliance, payroll and AgentOps/CI are deliberately out of
  scope for this build.
