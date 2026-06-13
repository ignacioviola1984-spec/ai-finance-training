# Progreso del training

Bitacora de avance, fase por fase.

## Hecho

### Fase 0 — Entorno de constructor  [OK]
- Instalado y configurado: Python, Git, GitHub.
- Git configurado (user.name, user.email, init.defaultBranch=main).
- Repo ai-finance-training creado y conectado.
- Ciclo completo: editar -> git add -> git commit -m -> git push.
- hello_finance.py: primer script (calculo de margen).

### Fase 1.1 — Primera llamada a una API  [OK]
- api_fx.py y fx_rates.py: tipos de cambio reales (Frankfurter).
- Tabla multi-moneda, conversion, manejo de errores.
- Conceptos: REST API, JSON, funciones, f-strings, try/except.

### Fase 1.2 — Tool use / function calling  [OK]
- agent_fx.py: primer agente. Claude decide usar get_rate, el codigo
  la ejecuta, Claude redacta la respuesta.
- Seguridad: API key en .env, protegida por .gitignore.
- Conceptos: tool use, tool schema, loop pedir-ejecutar-devolver.

### Fase 2.1 — Operar un MCP existente  [OK concepto]
- Visto el handshake cliente/servidor en vivo (QuickBooks pidio auth).
- Conceptos: MCP, server/client, tools vs resources, auth como control.
- Sandbox de QuickBooks descartado (onboarding de Intuit, no aporta skill).

### Fase 2.2 — Construir un MCP server propio  [OK]
- finance-mcp/: server MCP de "Lumen Inc.", SaaS post-seed, 6 entidades,
  6 monedas. Herramientas: list_entities, get_pnl, get_balance_sheet,
  get_ar_aging, get_cash_position.
- Consolidacion multi-moneda con FX de cierre. Balance cuadra (check=0).
- Datos sinteticos reproducibles (generate_data.py).
- Conceptos: FastMCP, definir tools, capa de datos, validaciones.

## Siguiente

### Fase 2.3 — Conectar el server a Claude y endurecerlo
- Conectar finance-mcp a un cliente (MCP Inspector / Claude Desktop).
- Mas manejo de errores y validaciones, decidir que exponer y que no.

## Notas
- Background: 17 anios en finanzas senior. Plan Max 5x.
- Modo CFO grade: rigor contable, decisiones defendibles, validar antes
  de entregar, nada inflado.
- Regla: sin repo, no aprendiste. Pedir el "por que" de cada decision.
- Human-in-the-loop: validar entre etapas como control de calidad.
