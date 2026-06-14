"""
strategic_finance_agent.py - Strategic Finance Agent del CFO office.

Mira el negocio con lente estrategica, no de cierre: calidad del crecimiento,
eficiencia del capital y camino a la rentabilidad. Calcula (por codigo) las
metricas SaaS canonicas y un set de escenarios, levanta flags estrategicos, y
deja todo en el estado compartido para el CFO.

Metricas (todas deterministicas, reusa finance_core):
  - Run-rate (ARR proxy) y crecimiento anualizado del run-rate.
  - Rule of 40 = crecimiento anualizado (%) + margen operativo (%).
  - Burn multiple = burn mensual / revenue nuevo mensual (eficiencia de capital).
  - Magic number = revenue nuevo / S&M del periodo previo (eficiencia comercial).
  - Mix de gasto (COGS/S&M/R&D/G&A como % del revenue).
  - Gap de margen a breakeven (pp) y 3 escenarios de crecimiento.

Lentes propias (sin pisar a los demas): Controller ve la perdida del periodo,
Treasury el runway, FP&A la varianza vs plan; Strategic ve la TRAYECTORIA y la
EFICIENCIA (si crecer alcanza, y a que costo de capital).

Nota de honestidad: el crecimiento se anualiza componiendo el promedio MoM
(proxy; no hay historico YoY con 5 meses). Se documenta como proxy.

Numeros por codigo; el modelo razona y redacta, nunca inventa una cifra.

Requisitos: ANTHROPIC_API_KEY en el .env de la raiz.
Correr:  python strategic_finance_agent.py
"""

import os
import sys

from dotenv import load_dotenv
from anthropic import Anthropic

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "orchestration"))   # finance_core
sys.path.insert(0, HERE)                                  # shared_state

import finance_core as fc
from shared_state import CFOContext

load_dotenv(os.path.join(ROOT, ".env"))
client = Anthropic()
MODEL = "claude-sonnet-4-6"

BURN_MULTIPLE_MAX = 2.0   # Bessemer: >2 es ineficiente
MAGIC_MIN = 0.75          # >0.75 es buen retorno comercial


def agent(system, prompt, max_tokens=600):
    resp = client.messages.create(
        model=MODEL, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def _money(x):
    return f"USD {x:,.0f}"


# --- Capa deterministica: las metricas las calcula finance_core ---------
# (numeros sin cliente, testeables por el eval harness; el agente solo narra)

def strategic_escalations(m):
    """Flags estrategicos por severidad. Lista de [sev, mensaje].

    Solo riesgos de eficiencia/trayectoria que ningun otro agente cubre
    (Controller ve la perdida del periodo; Treasury el runway). Aca: eficiencia
    de capital y si el modelo llega a breakeven creciendo.
    """
    out = []
    bm = m["burn_multiple"]
    if bm is not None and bm > BURN_MULTIPLE_MAX:
        out.append(["ALTA", f"burn multiple {bm:.1f}x (> {BURN_MULTIPLE_MAX:.0f}): por cada USD "
                            f"de revenue nuevo se queman {bm:.1f}; baja eficiencia de capital"])
    if m["op_margin"] < 0:
        out.append(["ALTA", f"crecer no alcanza el breakeven: el margen operativo "
                            f"({m['op_margin']*100:.0f}%) no mejora solo con volumen; se necesitan "
                            f"~{m['breakeven_gap_pp']:.0f} pp de mejora de margen, no mas crecimiento"])
    return out


# --- Orquestacion del agente -------------------------------------------

def run(ctx=None):
    own = ctx is None
    ctx = ctx or CFOContext()
    ctx.audit("Strategic Finance", "inicio", "run-rate, eficiencia de capital, camino a breakeven")

    m = fc.strategic_metrics()
    esc = strategic_escalations(m)

    bm_txt = f"{m['burn_multiple']:.1f}x" if m["burn_multiple"] is not None else "n/d"
    mg_txt = f"{m['magic_number']:.2f}" if m["magic_number"] is not None else "n/d"
    scen_txt = "\n".join(
        f"  {s['name']}: crec MoM {s['mom_growth']*100:.1f}% -> run-rate 12m {_money(s['run_rate_12m'])}, "
        f"Rule of 40 {s['rule_of_40']:.0f}" for s in m["scenarios"])
    facts = (
        f"Metricas estrategicas (cierre {fc.LATEST}, USD):\n"
        f"  Run-rate (ARR proxy): {_money(m['run_rate'])}\n"
        f"  Crecimiento anualizado (proxy de MoM): {m['ann_growth']*100:.0f}%\n"
        f"  Margen operativo: {m['op_margin']*100:.0f}%\n"
        f"  Rule of 40: {m['rule_of_40']:.0f} (umbral 40)\n"
        f"  Burn multiple: {bm_txt} (umbral <= {BURN_MULTIPLE_MAX:.0f})\n"
        f"  Magic number: {mg_txt} (bueno > {MAGIC_MIN})\n"
        f"  Mix de gasto (% revenue): COGS {m['mix']['cogs']*100:.0f}, S&M {m['mix']['sm']*100:.0f}, "
        f"R&D {m['mix']['rd']*100:.0f}, G&A {m['mix']['ga']*100:.0f}\n"
        f"  Gap de margen a breakeven: {m['breakeven_gap_pp']:.0f} pp\n"
        f"Escenarios de crecimiento (margen constante):\n{scen_txt}"
    )
    narrative = agent(
        "Sos el lead de Strategic Finance. Con las metricas que te dan, escribi 3-5 bullets, "
        "tono CFO: calidad del crecimiento (Rule of 40, magic number), eficiencia de capital "
        "(burn multiple) y el camino a la rentabilidad (gap de margen, escenarios). Cerra con "
        "la palanca estrategica principal. Usa solo los numeros dados; no inventes cifras.",
        facts,
    )

    ctx.put("Strategic Finance", {
        "metrics": m, "narrative": narrative, "escalations": esc,
    })
    ctx.audit("Strategic Finance", "ok",
              f"run-rate {_money(m['run_rate'])}, Rule of 40 {m['rule_of_40']:.0f}, "
              f"burn multiple {bm_txt}; {len(esc)} escalamiento(s)")

    if own:
        print("\n--- STRATEGIC FINANCE ---\n" + narrative)
        path = ctx.save()
        print(f"\nEstado compartido guardado en: {os.path.basename(path)}")
    return ctx


if __name__ == "__main__":
    run()
