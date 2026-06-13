\# Progreso del training



Bitacora de avance, fase por fase.



\## Hecho



\### Fase 0 — Entorno de constructor  \[OK]

\- Instalado y configurado: Python, Git, GitHub.

\- Git configurado (user.name, user.email, init.defaultBranch=main).

\- Repo ai-finance-training creado y conectado.

\- Ciclo completo: editar -> git add -> git commit -m -> git push.

\- hello\_finance.py: primer script (calculo de margen).



\### Fase 1.1 — Primera llamada a una API  \[OK]

\- api\_fx.py y fx\_rates.py: tipos de cambio reales (Frankfurter).

\- Tabla multi-moneda, conversion, manejo de errores.

\- Conceptos: REST API, JSON, funciones, f-strings, try/except.



\### Fase 1.2 — Tool use / function calling  \[OK]

\- agent\_fx.py: primer agente. Claude decide usar get\_rate, el codigo

&#x20; la ejecuta, Claude redacta la respuesta.

\- Seguridad: API key en .env, protegida por .gitignore.

\- Conceptos: tool use, tool schema, loop pedir-ejecutar-devolver,

&#x20; Claude decide / el codigo ejecuta.



\## Siguiente



\### Fase 2 — MCP: construir un connector propio

\- Conectar un MCP server existente (QuickBooks, ya disponible).

\- Construir un MCP server propio que exponga get\_balance, get\_aging, get\_pnl.

\- Conectarlo a Claude, manejo de errores y validaciones.



\## Notas

\- Background: 17 anios en finanzas senior. Plan Max 5x.

\- Regla: sin repo, no aprendiste. Pedir el "por que" de cada decision.

\- Human-in-the-loop: validar entre etapas como control de calidad.

