# Arquitectura del repositorio

Este repo está pensado para crecer de forma ordenada. Cubre tanto **planificar y generar** artefactos de QA (plan de pruebas, análisis de historias, casos manuales, BDD, casos de API, datos de prueba, reportes de bug) como **ejecutar** pruebas (end-to-end en el navegador y de API) y **reportar** los resultados (reporte de cada corrida e informe de cierre de la ronda). Para que cada capacidad nueva entre sin romper lo que ya funciona, todo se organiza en piezas, cada una con su lugar.

## Las piezas

![Cómo se relacionan las piezas](docs/assets/img/relaciones.png)

El agente es el centro: carga **skills** (el cómo), respeta las **plantillas** (el formato), ejecuta **scripts** (lo mecánico) y **herramientas** (por terminal), y usa **conectores MCP** para hablar con sistemas externos; lee de `input/` y deja todo en `output/`. El diagrama se edita en `docs/diagramas/relaciones.html` y se regenera con `node docs/generar.js`.

### Agentes — el *quién* (`.claude/agents/`)

Cada agente es un subagente de Claude Code con su rol, su proceso y sus reglas. Es a quién se le delega una tarea entera. Hoy hay cuarenta y dos, agrupados en documentación del proyecto, análisis y diseño (con el triage de bugs, las consultas sobre el producto y el onboarding), ejecución en vivo (incluidas las pruebas exploratorias, de accesibilidad, de rendimiento web, de permisos por rol, de resiliencia, la regresión visual, el cross-browser, los correos y las traducciones), reportes (con el análisis de fallos, la cobertura y el tablero de calidad), automatización con k0lmena (con la reparación de locators), la selección de casos por cambio, seguridad y gestión (el catálogo, con los skills, herramientas y conectores de cada uno, está en `AGENTES.md`). Como corren como subagentes, no pueden hacerle preguntas a la persona a mitad del trabajo: si les falta un dato, terminan devolviendo "Necesito que confirmes" y la conversación principal pregunta y los continúa. La clave de cada uno está en el `description` de su frontmatter: es lo que usa Claude Code para saber cuándo invocarlo.

### Skills — el *cómo* (`.claude/skills/`)

Conocimiento empaquetado que Claude Code carga **on-demand** (solo cuando hace falta). Encapsula el "cómo" de una capacidad reutilizable, para que varios agentes lo aprovechen sin repetir instrucciones. Cada skill es una carpeta con un `SKILL.md` (ver `.claude/skills/README.md`).

> Lo que un agente usa para **actuar** viene en tres formas: conexiones MCP, herramientas externas y scripts internos.

### MCP — conexiones a sistemas externos (`.mcp.json`)

Para tocar sistemas de afuera (Jira, Xray, un navegador…), un agente usa un **server MCP**. **Es un solo archivo, pero escala a todas las conexiones que quieras**: `.mcp.json` es un *registro* de servers, donde agregás una entrada por cada integración.

```json
{
  "mcpServers": {
    "atlassian":  { "type": "http", "url": "https://mcp.atlassian.com/v2/mcp" },
    "qtm4j":      { "type": "stdio", "command": "node", "args": ["scripts/mcp/con-env.js", "qtm4j", "--requeridas", "QTM4J_API_KEY", "--", "@smartbear/mcp"], "env": { "MCP_CLIENTS": "QTM4J" } },
    "playwright": { "type": "stdio", "command": "node", "args": ["scripts/mcp/playwright.js"] }
  }
}
```

En este repo, `.mcp.json` viene **versionado con los conectores que todos usan** (Playwright headed y headless, y Atlassian para Jira y Confluence), todos habilitados en `.claude/settings.json`: así Claude Code arranca directo, sin pedir aprobaciones. Los opcionales (Azure DevOps, Figma, GitHub, GitLab, QMetry, AIO Tests, k0lmenaTMT, Appium) están en `scripts/mcp/catalogo.json` y cada persona los activa con `npm run conector -- activar <nombre>`, que los registra con alcance local de Claude Code (solo para esa persona, sin tocar archivos versionados). **Ninguno lleva secretos**: los que necesitan token arrancan con un script de `scripts/mcp/` que lo lee del `.env`.

> **Regla de oro de los secretos:** tokens y credenciales van en el `.env` local (gitignored) o en variables de entorno, **nunca** con el valor real en `.mcp.json` ni en otro archivo versionado. Hay una plantilla `.env.example` con los nombres de variable; se copia a `.env` y se completan los valores reales. Si se commitea un secreto, rotalo de inmediato.

### Herramientas — herramientas externas de testing (`herramientas/`)

Herramientas que el agente **ejecuta** por línea de comandos, con sus plantillas y configuraciones. Hay cuatro integradas: **Mailpit**, el buzón de prueba que usa `verificador-correos` para atrapar los mails de la app; **Newman** (la CLI de Postman), que usa `ejecutor-api` para correr pruebas de API; **OWASP ZAP**, que usa `analista-seguridad` para el escaneo de seguridad pasivo; y **k0lmena**, el framework de automatización (web, api, mobile y performance con k6, Artillery y JMeter, más verificaciones en bases de datos PostgreSQL, MySQL / MariaDB, SQL Server y MongoDB, el recorrido exploratorio `npm run explorar` que usa `explorador-web` la auditoría de accesibilidad `npm run accesibilidad` que usa `analista-accesibilidad` la de rendimiento `npm run rendimiento` (Lighthouse) que usa `auditor-rendimiento-web`, la regresión visual `npm run pixel-perfect` que usa `pixel-perfect`, las pruebas en Chromium, Firefox y WebKit `npm run cross-browser` que usa `cross-browser` la reparación de locators `npm run reparar` que usa `reparador-automatizacion`, la revisión de correos `npm run correos` que usa `verificador-correos` y la de idiomas `npm run traductor` que usa `analista-traductor`). A esas se suman **streaming** (ffprobe/ffmpeg y ONVIF) para los agentes de video y cámaras, y **Salesforce** (la CLI `sf`) que usa `probador-salesforce` para relevar una org en solo lectura. Todas guardan sus últimas 5 corridas en `historial/` para compararlas. En k0lmena los agentes *mapper* escriben la automatización una sola vez y después corre con `npm test`, **sin agentes ni tokens**. Cada herramienta va en su **propia subcarpeta**, así escala: sumar una herramienta = sumar una carpeta (ver `herramientas/README.md`).

### Scripts — utilidades internas (`scripts/`)

Código Python propio del repo para tareas mecánicas (generar la planilla `.xlsx`, normalizar tablas). Incluye `scripts/gestion/`, la integración con Xray, QMetry (QTM4J) y AIO Tests sobre sus APIs oficiales: los agentes deciden qué hacer y el script lo ejecuta, sin depender de servers MCP. Las utilidades internas nuevas viven acá.

### Evals — la calidad de los agentes (`evals/`)

Los tests (`tests/`) cubren los scripts; los **evals** miden la calidad de lo que generan los agentes. Cada caso trae insumos con trampas deliberadas y chequeos determinísticos versionados; `scripts/evaluar_agentes.py` los corre en un workspace aislado con `claude -p` y arma un informe con las regresiones contra la corrida anterior. Al cambiar un agente o un skill, se corren antes y después.

## En resumen

- **Agente** = a quién le pido la tarea.
- **Skill** = el conocimiento de cómo hacerla.
- **MCP** = conexiones a sistemas externos (un archivo, muchas conexiones: Jira, Confluence, Figma, QMetry, AIO Tests, Azure DevOps, Playwright…).
- **Herramientas** = herramientas externas que se ejecutan por CLI (Newman y k0lmena).
- **Script** = utilidad interna determinística.

Hoy ya están en uso las cinco piezas: **agentes**, **skills** (investigación de contexto, técnicas de diseño, ejecución E2E y de API, automatización con k0lmena), la **conexión MCP** con Playwright (para el navegador), las **herramientas** Newman (para API) y k0lmena (automatización sin tokens) y los **scripts** de formato, reporte y conversión. Sumar capacidades nuevas es repetir el patrón: un agente nuevo en `.claude/agents/`, un skill en `.claude/skills/`, una conexión en `.mcp.json`, una herramienta en `herramientas/` o un script en `scripts/`.
