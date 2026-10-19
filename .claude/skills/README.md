# Skills

Los **skills** son conocimiento empaquetado que Claude Code carga **on-demand** (solo cuando hace falta, sin pesar en el contexto si no se usan). Sirven para encapsular el "cómo" de una capacidad reutilizable que varios agentes pueden aprovechar.

## Skills disponibles

- **`tecnicas-de-diseno/`** — técnicas formales de diseño de casos de caja negra (clases de equivalencia, valores límite, tabla de decisión, transición de estados, pairwise). Sirve para derivar casos más completos al generar pruebas manuales, BDD o de API.
- **`ejecucion-e2e/`** — cómo ejecutar pruebas E2E en el navegador con Playwright MCP (modo headed/headless, ubicar elementos por accesibilidad, esperas para evitar flakiness, evidencia). Lo usa el agente `ejecutor-e2e`.
- **`ejecucion-api/`** — cómo ejecutar pruebas de API con Newman (la CLI de Postman): correr una colección, escribir validaciones, manejar base_url y token, e interpretar los resultados. Lo usa el agente `ejecutor-api`.
- **`investigacion-contexto/`** — cómo investigar a fondo una historia antes de trabajarla (primero la documentación del proyecto de `input/documentacion/` que arma el `documentador-proyecto`; después Jira con comentarios, subtareas, épica e issues vinculados; Confluence; Figma; contratos; `input/`) y cómo registrar lo que falta como **Falta información** (`FI-XX`) en la ficha `output/contexto/contexto-HU-XXX.md`. Lo usan el analista, el estratega, los generadores de casos, los mappers y el `documentador-proyecto`.
- **`guia-performance/`** — guía paso a paso para planificar una prueba de performance con la persona (tipo de prueba, herramienta, ambiente, usuarios, rampa, duración, tiempo de pensamiento y umbrales, con sugerencias y cálculos) y dejar el plan confirmado para el `performance-mapper`. Lo usa la conversación principal, porque los subagentes no pueden hacerle preguntas a la persona.
- **`relevamiento-proyecto/`** — cómo relevar un proyecto **entero** por MCP (Jira, Azure DevOps, Confluence, repo, Figma): barrer cada herramienta con consultas acotadas, muestrear backlogs grandes, extraer módulos, flujos, integraciones y equipo, y clasificar ambigüedades, contradicciones y vacíos en preguntas priorizadas. Lo usa el `investigador-proyecto`.
- **`pruebas-salesforce/`** — cómo probar una org de Salesforce: ambientes y sandboxes, acceso (perfiles, permission sets, OWD, FLS), automatización (validaciones, flows, triggers, orden de ejecución, límites de gobierno, bulk de 200), datos (record types, picklists, duplicados), Lightning con Playwright, APIs, tests de Apex y releases. Lo usa el `probador-salesforce`.
- **`pruebas-tokens/`** — cómo probar tokens de autenticación (JWT, OAuth 2.0/OIDC, sesión, API keys) y la tokenización de tarjetas (PCI): ciclo de vida, firma y claims, ataques típicos (alg none, replay, scope), manejo seguro y qué no hacer con datos reales. Lo usan el `probador-billeteras`, el `probador-salesforce` y el `pentester-web`.
- **`pruebas-billeteras/`** — cómo probar billeteras virtuales y pagos: saldo y libro mayor (conservación del dinero), transacciones y estados, idempotencia y reintentos, doble gasto y concurrencia, redondeo y moneda, límites, KYC/AML, conciliación con la pasarela y webhooks. Lo usa el `probador-billeteras`.
- **`automatizacion-k0lmena/`** — convenciones para generar automatización en k0lmena (`herramientas/k0lmena`): estructura web/api/mobile, nombres y tags, reutilización de steps, helpers, steps genéricos de API y validación con `npm`, más las plantillas de performance (k6, Artillery y JMeter). Incluye los steps de verificación en base de datos (que se agregan solo cuando se piden). Lo usan `web-mapper`, `api-mapper`, `mobile-mapper`, `performance-mapper` y `verificador-datos`.

## Cómo agregar uno

Creá una carpeta en `.claude/skills/` con un `SKILL.md` adentro:

```
.claude/skills/
└── mi-skill/
    ├── SKILL.md          # obligatorio: frontmatter (name, description) + instrucciones
    ├── references/       # opcional: detalle que se carga solo si hace falta
    └── scripts/          # opcional: scripts que el skill ejecuta
```

El `description` del frontmatter es lo que usa Claude Code para decidir cuándo cargar el skill. Más detalle en [`../../ARQUITECTURA.md`](../../ARQUITECTURA.md).
