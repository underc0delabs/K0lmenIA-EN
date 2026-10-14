# Catálogo de agentes

Los 41 agentes de k0lmenIA: para qué sirve cada uno, cómo pedírselo, qué skills, scripts, herramientas y conectores usa, y qué entrega. No hace falta nombrar al agente: Claude Code elige el que corresponde según el pedido (también se lo podés pedir por su nombre).

**Leyenda**
- **Tokens**: *en cada uso* = trabaja con el modelo cada vez que lo pedís; *una vez* = genera algo que después corre solo, sin agentes ni tokens (`npm test`, `npm run perf`).
- **Confirma**: el agente no hace la acción sin tu ok explícito (por ejemplo, escribir en una base o crear casos en Xray). Como los agentes no pueden preguntar a mitad del trabajo, devuelven **"Necesito que confirmes"** y Claude te pregunta.
- **Conectores**: los que vienen activos (`playwright`, `atlassian`) no necesitan nada; los demás se activan con `npm run conector -- activar <nombre>` (ver `CONECTORES.md`).

## Resumen

| Agente                   | Familia                                       | Para qué                                                                          | Skills                                                             | Herramientas y scripts                                             | Conectores                                                                | Salida                                                  |
| ------------------------ | --------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| documentador-proyecto    | Análisis y diseño                             | Documentación del proyecto: repo, historias, links y web                          | investigacion-contexto, ejecucion-e2e                              | npm run mapa-funcional, indice_documentacion.py                    | github, gitlab, azure-devops, atlassian, playwright-headless              | input/documentacion/                                    |
| analista-historias       | Análisis y diseño                             | Ambigüedades, riesgos y preguntas de una historia                                 | investigacion-contexto                                             | formatear_tablas.py                                                | atlassian, azure-devops, figma                                            | output/analisis-historias/                              |
| estratega-pruebas        | Análisis y diseño                             | Plan de pruebas (alcance, riesgos, criterios)                                     | investigacion-contexto                                             | generar_plan.py                                                    | atlassian, azure-devops, figma                                            | output/planes-de-prueba/                                |
| generador-casos-manuales | Análisis y diseño                             | Casos manuales en Excel, Markdown y cobertura                                     | investigacion-contexto, tecnicas-de-diseno                         | generar_casos.py, formatear_tablas.py                              | atlassian, azure-devops, figma                                            | output/casos-de-prueba/manuales/                        |
| generador-casos-bdd      | Análisis y diseño                             | Escenarios Gherkin y cobertura                                                    | investigacion-contexto, tecnicas-de-diseno                         | formatear_tablas.py                                                | atlassian, azure-devops, figma                                            | output/casos-de-prueba/bdd/                             |
| generador-casos-api      | Análisis y diseño                             | Casos de API desde un contrato                                                    | investigacion-contexto, tecnicas-de-diseno                         | formatear_tablas.py                                                | atlassian, azure-devops                                                   | output/casos-api/                                       |
| generador-datos-prueba   | Análisis y diseño                             | Datos válidos, inválidos y de borde                                               | investigacion-contexto                                             | formatear_tablas.py                                                | atlassian, azure-devops                                                   | output/datos-de-prueba/                                 |
| selector-casos-de-prueba | Análisis y diseño                             | Qué casos correr para un cambio (por riesgo)                                      | investigacion-contexto                                             | seleccionar_casos.py, generar_informe_seleccion.py                 | atlassian, azure-devops                                                   | output/seleccion-casos/                                 |
| revisor-casos            | Análisis y diseño                             | Calidad de los casos, duplicados y tiempo de ejecución                            | investigacion-contexto, tecnicas-de-diseno                         | revisar_casos.py, generar_informe_revision.py, estimacion.py       | atlassian, azure-devops                                                   | output/revision-casos/                                  |
| generador-charters       | Análisis y diseño                             | Charters y sesiones exploratorias con su informe                                  | ejecucion-e2e, investigacion-contexto, tecnicas-de-diseno          | generar_charters.py                                                | atlassian, azure-devops, playwright, playwright-headless                  | output/charters/                                        |
| generador-reportes-bug   | Análisis y diseño                             | Reporte de bug desde una observación                                              | —                                                                  | formatear_tablas.py, plantilla de bug                              | atlassian, azure-devops                                                   | output/reportes-bug/                                    |
| triador-bugs             | Análisis y diseño                             | Duplicados, regresiones y clasificación de bugs antes de cargarlos                | —                                                                  | buscar_duplicados.py, avisar.py                                    | atlassian, azure-devops, github, gitlab                                   | output/triage/                                          |
| consultor-proyecto       | Análisis y diseño                             | Responde preguntas del producto con la documentación, citando fuentes             | investigacion-contexto                                             | formatear_tablas.py                                                | —                                                                         | Respuesta en el chat (+ output/consultas/)              |
| ejecutor-e2e             | Ejecución en vivo                             | Corre casos en el navegador con evidencia                                         | ejecucion-e2e                                                      | Playwright MCP, generar_reporte.py                                 | playwright, playwright-headless                                           | output/ejecuciones/                                     |
| ejecutor-api             | Ejecución en vivo                             | Corre una colección de Postman                                                    | ejecucion-api                                                      | Newman, correr_newman.py                                           | —                                                                         | output/ejecuciones/                                     |
| analista-seguridad       | Ejecución en vivo                             | Escaneo de seguridad web pasivo e informe                                         | —                                                                  | OWASP ZAP (Docker), escanear.py, generar_informe_seguridad.py      | —                                                                         | output/seguridad/                                       |
| explorador-web           | Ejecución en vivo                             | Exploratorias: links, imágenes, errores y responsive                              | ejecucion-e2e                                                      | npm run explorar, generar_informe_exploratorio.py                  | playwright, playwright-headless                                           | output/exploratorias/                                   |
| analista-accesibilidad   | Ejecución en vivo                             | Accesibilidad WCAG 2.2: axe, teclado y revisión manual                            | ejecucion-e2e                                                      | npm run accesibilidad (axe-core), generar_informe_accesibilidad.py | playwright, playwright-headless                                           | output/accesibilidad/                                   |
| auditor-rendimiento-web  | Ejecución en vivo                             | Velocidad de carga: Lighthouse y Core Web Vitals                                  | —                                                                  | npm run rendimiento (Lighthouse), generar_informe_rendimiento.py   | —                                                                         | output/rendimiento/                                     |
| pixel-perfect            | Ejecución en vivo                             | Regresión visual: qué se corrió o cambió                                          | ejecucion-e2e                                                      | npm run pixel-perfect, generar_informe_pixel_perfect.py            | playwright, playwright-headless, figma                                    | output/pixel-perfect/                                   |
| cross-browser            | Ejecución en vivo                             | Chromium, Firefox y WebKit (Safari)                                               | ejecucion-e2e                                                      | npm run cross-browser, generar_informe_cross_browser.py            | playwright, playwright-headless                                           | output/cross-browser/                                   |
| verificador-correos      | Ejecución en vivo                             | Correos de la app con Mailpit: llegan, contenido, links                           | investigacion-contexto, ejecucion-e2e, automatizacion-k0lmena      | npm run correos (Mailpit), generar_informe_correos.py              | playwright, playwright-headless                                           | output/correos/                                         |
| analista-traductor       | Ejecución en vivo                             | Traducciones e idiomas: sin traducir, cortados, formatos                          | investigacion-contexto, ejecucion-e2e                              | npm run traductor, generar_informe_traductor.py                    | playwright, playwright-headless                                           | output/traductor/                                       |
| evaluador-ux             | Ejecución en vivo                             | Usabilidad con las 10 heurísticas de Nielsen                                      | ejecucion-e2e, investigacion-contexto                              | npm run ux, generar_informe_ux.py                                  | playwright, playwright-headless                                           | output/ux/                                              |
| probador-formularios     | Ejecución en vivo                             | Validaciones de cada campo sin enviar el formulario                               | ejecucion-e2e, investigacion-contexto                              | npm run formularios, generar_informe_formularios.py                | playwright, playwright-headless                                           | output/formularios/                                     |
| probador-permisos        | Ejecución en vivo                             | Matriz de permisos: qué ve y abre cada rol                                        | investigacion-contexto, ejecucion-e2e                              | npm run permisos, generar_informe_permisos.py                      | playwright, playwright-headless, atlassian, azure-devops                  | output/permisos/                                        |
| probador-resiliencia     | Ejecución en vivo                             | Qué ve la persona cuando la API, la red o los recursos fallan                     | ejecucion-e2e, investigacion-contexto                              | npm run resiliencia, generar_informe_resiliencia.py                | playwright, playwright-headless                                           | output/resiliencia/                                     |
| generador-reporte-html   | Reportes                                      | Reporte HTML de una corrida                                                       | —                                                                  | generar_reporte.py                                                 | —                                                                         | output/ejecuciones/                                     |
| generador-reporte-cierre | Reportes                                      | Informe de cierre y go/no-go de la ronda                                          | —                                                                  | recolectar_resultados.py, generar_informe_cierre.py                | —                                                                         | output/informes-cierre/                                 |
| analista-cobertura       | Reportes                                      | Matriz de trazabilidad y qué falta probar                                         | investigacion-contexto                                             | analizar_cobertura.py, generar_informe_cobertura.py                | atlassian, azure-devops                                                   | output/cobertura/                                       |
| tablero-calidad          | Reportes                                      | Tablero de calidad por sprint o release: aprobados, automatizado, cobertura, bugs | —                                                                  | tablero_calidad.py, portal_informes.py, avisar.py                  | —                                                                         | output/tablero/                                         |
| web-mapper               | Automatización (k0lmena)                      | Automatiza casos web                                                              | automatizacion-k0lmena, ejecucion-e2e, investigacion-contexto      | k0lmena (Playwright + Cucumber)                                    | playwright, playwright-headless                                           | herramientas/k0lmena/web/ + output/mapeos/              |
| api-mapper               | Automatización (k0lmena)                      | Automatiza APIs desde Postman o Swagger                                           | automatizacion-k0lmena, investigacion-contexto, tecnicas-de-diseno | k0lmena (axios + Cucumber)                                         | —                                                                         | herramientas/k0lmena/api/ + output/mapeos/              |
| mobile-mapper            | Automatización (k0lmena)                      | Automatiza casos mobile                                                           | automatizacion-k0lmena, investigacion-contexto                     | k0lmena (WebdriverIO + Appium)                                     | linear · clickup · monday · asana · trello · notion · youtrack · shortcut | No                                                      | los mismos que atlassian, si tu equipo usa esa herramienta: todos los que investigan una historia (skill investigacion-contexto), documentador-proyecto |
| appium-mcp               | herramientas/k0lmena/mobile/ + output/mapeos/ |
| performance-mapper       | Automatización (k0lmena)                      | Carga, estrés, soak y picos con informe                                           | automatizacion-k0lmena, guia-performance                           | k6, Artillery, JMeter, generar_informe_performance.py              | —                                                                         | herramientas/k0lmena/performance/ + output/performance/ |
| verificador-datos        | Automatización (k0lmena)                      | Consulta y verifica datos en bases                                                | automatizacion-k0lmena                                             | k0lmena tools/bd (npm run bd)                                      | —                                                                         | chat (+ output/verificaciones-datos/)                   |
| analista-fallos          | Automatización (k0lmena)                      | Clasifica las fallas de npm test y detecta inestables                             | ejecucion-e2e                                                      | analizar_fallos.py, generar_informe_fallos.py                      | playwright, playwright-headless                                           | output/fallos/ + output/reportes-bug/                   |
| reparador-automatizacion | Automatización (k0lmena)                      | Repara locators y esperas rotos y lo verifica                                     | automatizacion-k0lmena, ejecucion-e2e                              | npm run reparar, generar_informe_reparacion.py                     | playwright, playwright-headless                                           | herramientas/k0lmena/web/ + output/reparaciones/        |
| analista-logs            | Automatización (k0lmena)                      | Errores del servidor cruzados con la corrida                                      | —                                                                  | analizar_logs.py, generar_informe_logs.py                          | —                                                                         | output/logs/                                            |
| gestor-pruebas           | Gestión                                       | Carpetas, casos y ciclos en la herramienta de gestión                             | —                                                                  | gestion.py, para_azure_devops.py                                   | azure-devops (para Azure Test Plans)                                      | Xray / QMetry / AIO / Azure DevOps + output/gestion/    |
| publicador-resultados    | Gestión                                       | Sube resultados de npm test con evidencias                                        | —                                                                  | gestion.py                                                         | —                                                                         | Xray / QMetry / AIO                                     |

---

## Análisis y diseño

### documentador-proyecto
- **Cuándo**: al empezar con un proyecto (para armar la base de contexto) y antes de trabajar una historia o épica (para juntar todo lo que hay sobre ella), así los demás agentes escriben casos con contexto real.
- **Pedido de ejemplo**: *"Documentá el proyecto"* · *"Juntá todo el contexto de PROJ-12 antes de escribir los casos"* · *"Actualizá la documentación del proyecto"*.
- **Entradas**: el repositorio de la aplicación (bloque *Repositorio de la aplicación* del `.env`: `REPO_PROVEEDOR`, `REPO_NOMBRE`, `REPO_RAMA`, opcional `REPO_RUTA_LOCAL`), la historia o épica (key de Jira, work item de Azure DevOps o `HU-XXX`) y la URL de la app (`APP_URL`).
- **Usa**: conector del repositorio en solo lectura (`github`, `gitlab`, `azure-devops` para Azure Repos o `atlassian` para Bitbucket Cloud): README y docs, validaciones, límites, mensajes, estados, roles y permisos, rutas, contratos de API y los PRs y commits de la historia; skill `investigacion-contexto` (historia, comentarios, subtareas, épica, vínculos, Confluence, Wiki, Figma) y links públicos; `npm run mapa-funcional` (páginas, menús, formularios con sus campos, botones y mensajes, sin enviar nada) y, puntualmente, Playwright MCP con el skill `ejecucion-e2e`; `scripts/indice_documentacion.py` y `scripts/formatear_tablas.py`.
- **Entrega**: en `input/documentacion/` (no se versiona), `INDICE.md`; `proyecto/` con resumen, repositorio, reglas de negocio, mensajes, estados y permisos, mapa funcional y links; `api/` con los contratos; y `historias/<HU o key>/dossier.md` (historia, decisiones, links, PRs y código tocado, pantallas, contradicciones y pistas para probar). Cada dato con su fuente. El skill `investigacion-contexto` lo lee primero, así que lo aprovechan todos los agentes que investigan una historia.
- **Tokens**: en cada uso (el recorrido de la web y el índice los hacen scripts; con `REPO_RUTA_LOCAL` el código se lee sin el conector).

### analista-historias
- **Cuándo**: antes de diseñar pruebas, para encontrar huecos y ambigüedades en una historia.
- **Pedido de ejemplo**: *"Analizá la historia HU-001"* · *"Revisá PROJ-12 de Jira y decime qué falta definir"*.
- **Entradas**: la historia (en `input/historias/`, una key de Jira o un work item de Azure DevOps) y su documentación.
- **Usa**: skill `investigacion-contexto` (comentarios, subtareas, épica, Confluence, Figma); `scripts/formatear_tablas.py`.
- **Entrega**: `output/analisis-historias/analisis-HU-XXX.md` con ambigüedades, riesgos, casos no contemplados y preguntas para el PO; la ficha `output/contexto/contexto-HU-XXX.md` con los `FI-XX`.
- **Tokens**: en cada uso.

### estratega-pruebas
- **Cuándo**: al empezar una historia, feature o release, para acordar qué se prueba y cómo.
- **Pedido de ejemplo**: *"Armá el plan de pruebas de HU-001"*.
- **Usa**: skill `investigacion-contexto`; `scripts/generar_plan.py`.
- **Entrega**: `output/planes-de-prueba/plan-HU-XXX-<fecha>.html` (dashboard): objetivos, alcance, tipos de prueba, riesgos, datos y entorno, criterios de entrada y salida, supuestos y preguntas.
- **Tokens**: en cada uso.

### generador-casos-manuales
- **Cuándo**: para escribir los casos de prueba de una historia.
- **Pedido de ejemplo**: *"Generá los casos de prueba de HU-001"*.
- **Usa**: skills `investigacion-contexto` y `tecnicas-de-diseno` (equivalencia, valores límite, tabla de decisión, estados, pairwise); `scripts/generar_casos.py` y `scripts/formatear_tablas.py`.
- **Entrega**: en `output/casos-de-prueba/manuales/`, `casos-HU-XXX.xlsx` + `casos-HU-XXX.md` + `casos-HU-XXX-cobertura.md` (cobertura por criterio, ambigüedades y preguntas). Los casos con información faltante quedan resaltados y con su `FI-XX`.
- **Tokens**: en cada uso.

### generador-casos-bdd
- **Cuándo**: para tener los escenarios en Gherkin (por ejemplo, para automatizarlos después).
- **Pedido de ejemplo**: *"Pasá HU-001 a BDD"*.
- **Usa**: skills `investigacion-contexto` y `tecnicas-de-diseno`; `scripts/formatear_tablas.py`.
- **Entrega**: en `output/casos-de-prueba/bdd/`, `HU-XXX-<tema>.feature` (keywords en inglés, contenido en español, cada escenario con `@CP-XXX`) + `HU-XXX-cobertura.md`.
- **Tokens**: en cada uso.

### generador-casos-api
- **Cuándo**: para diseñar las pruebas de una API desde su contrato.
- **Pedido de ejemplo**: *"Generá los casos de API de input/api/auth-endpoints.md"*.
- **Usa**: skills `investigacion-contexto` (si sale de una historia) y `tecnicas-de-diseno`; `scripts/formatear_tablas.py`.
- **Entrega**: `output/casos-api/casos-api-<tema>.md`: tabla resumen y detalle de cada caso con método, endpoint, headers, body y respuesta esperada (positivos, negativos, schema y autorización).
- **Tokens**: en cada uso. Para correrlos, `ejecutor-api`; para automatizarlos, `api-mapper`.

### generador-datos-prueba
- **Cuándo**: para tener datos realistas con los que probar.
- **Pedido de ejemplo**: *"Generá datos de prueba para el registro de HU-001, en CSV"*.
- **Usa**: skill `investigacion-contexto` (las reglas de cada campo); `scripts/formatear_tablas.py`.
- **Entrega**: `output/datos-de-prueba/datos-HU-XXX.md` o `.csv` con datos válidos, inválidos y de borde. No toca ninguna base (para eso, `verificador-datos`).
- **Tokens**: en cada uso.

### selector-casos-de-prueba
- **Cuándo**: antes de probar un cambio (un PR, una release, un sprint), para saber qué casos correr sin hacer toda la regresión.
- **Pedido de ejemplo**: *"¿Qué casos corro para el PR #42?"* · *"Armá la regresión de la release 2.4 (main..release/2.4 en ../mi-app), tengo una hora"*.
- **Entradas**: el cambio —rango de git del repositorio de la aplicación, archivos de un PR, historias o issues de Jira/Azure DevOps o las notas de la release— y el inventario de casos (manuales, BDD y automatizados en k0lmena, con su último resultado, los inestables y los bugs).
- **Usa**: skill `investigacion-contexto` (para leer los issues); `scripts/seleccionar_casos.py` (cruza el cambio con los casos, con sinónimos en español e inglés, y les da un puntaje) y `scripts/generar_informe_seleccion.py`. Opcional: `input/mapa-componentes.json` (carpetas del código → historias).
- **Entrega**: en `output/seleccion-casos/<nombre>/`, `informe-seleccion.html` (riesgo, imprescindibles, recomendados y regresión mínima con el porqué de cada uno, tiempo y ahorro, comandos `npm test` con los tags listos para copiar, cambios sin cobertura), `seleccion.csv` (lo manual, para ejecutar) y `seleccion.json`.
- **Tokens**: en cada uso (el cruce y el puntaje los hace el script).

### revisor-casos
- **Cuándo**: para revisar casos que ya existen antes de ejecutarlos, subirlos a la herramienta de gestión o automatizarlos.
- **Pedido de ejemplo**: *"Revisá los casos de HU-001"* · *"¿Hay casos duplicados en la regresión?"* · *"¿Cuánto lleva ejecutar a mano los casos del sprint?"*.
- **Usa**: skills `investigacion-contexto` y `tecnicas-de-diseno`; `scripts/revisar_casos.py`, `scripts/generar_informe_revision.py` y `scripts/estimacion.py`.
- **Entrega**: en `output/revision-casos/<HU o nombre>/`, `informe-revision.html` (puntaje de cada caso, problemas con su sugerencia, duplicados, historias sin negativos, tiempo de ejecución manual y la versión mejorada que propone) y, si lo pedís, la planilla corregida en un archivo nuevo.
- **Confirma**: actualizar casos en la herramienta de gestión.
- **Tokens**: en cada uso (la revisión mecánica la hace el script).

### generador-charters
- **Cuándo**: para planificar pruebas exploratorias con objetivo (session-based testing) y documentar lo que se encontró.
- **Pedido de ejemplo**: *"Armá charters para explorar el checkout de la release 2.4"* · *"Generá el informe de las sesiones de HU-003"*.
- **Usa**: skills `investigacion-contexto`, `tecnicas-de-diseno` (heurísticas) y `ejecucion-e2e` (si explora él); `scripts/generar_charters.py`.
- **Entrega**: en `output/charters/<HU o nombre>/`, las hojas de sesión (`charters.html` y `.md`), una plantilla de notas por sesión (`sesiones/CH-XX.md`) y, con las notas, `informe-sesiones.html` (bugs, preguntas, riesgos, reparto del tiempo y áreas cubiertas).
- **Tokens**: en cada uso.

### generador-reportes-bug
- **Cuándo**: cuando encontraste un error y tenés notas sueltas.
- **Pedido de ejemplo**: *"Armá el reporte de bug de input/bugs/observacion.md"* o pegale la observación.
- **Usa**: `plantillas/plantilla-reporte-bug.md`, `scripts/formatear_tablas.py`; la ficha de contexto si existe.
- **Entrega**: `output/reportes-bug/BUG-XXX.md` (el número siguiente al más alto) con historia, estado, severidad y prioridad justificadas; lo que falta queda marcado, nunca inventado.
- **Tokens**: en cada uso.

### triador-bugs
- **Cuándo**: antes de cargar un bug en la herramienta, o para revisar un lote de bugs del sprint, para que no entren duplicados y cada bug llegue con severidad, componente e historia.
- **Pedido de ejemplo**: *"¿BUG-008 ya está cargado en Jira?"* · *"Triá los bugs de output/reportes-bug"* · *"Buscá duplicados de 'el pago rechaza tarjetas válidas'"*.
- **Entradas**: el bug (`output/reportes-bug/`, `input/bugs/`, texto, key de Jira o ID de Azure DevOps) y el proyecto donde buscar.
- **Usa**: conectores `atlassian` (JQL) o `azure-devops` (WIQL) para traer candidatos, incluidos los cerrados; `github` o `gitlab` para issues del repositorio y `CODEOWNERS`/commits para sugerir responsable; `scripts/buscar_duplicados.py` (similitud con los mismos sinónimos que el selector de casos); `scripts/avisar.py` para avisar un bug crítico, solo si se pide.
- **Entrega**: veredicto (nuevo, duplicado, posible regresión de un bug cerrado o relacionado), severidad y prioridad con su criterio, componente, responsable sugerido (solo el usuario de la herramienta) e historia a vincular; `output/triage/<nombre>/` con `candidatos.json`, `triage.json` y `triage.md`.
- **Tokens**: en cada uso (el puntaje lo hace el script).
- **Confirma**: crear, vincular, comentar, reabrir o cambiar campos en Jira o Azure DevOps.

### consultor-proyecto
- **Cuándo**: para consultar cómo funciona algo del producto o ponerse al día con un proyecto, sin releer toda la documentación.
- **Pedido de ejemplo**: *"¿Qué pasa si un usuario bloqueado intenta pagar?"* · *"¿Cuál es el largo máximo del nombre en el registro?"* · *"¿Qué roles pueden aprobar un pedido?"*.
- **Entradas**: la pregunta; `input/documentacion/` (empieza por el índice), `output/contexto/` y los artefactos generados.
- **Usa**: solo lectura de esa documentación (no navega la app ni lee el repositorio o Jira, salvo pedido explícito); el skill `investigacion-contexto` para proponer `FI-XX`.
- **Entrega**: la respuesta en el chat con la fuente original de cada afirmación, separando lo que dice la historia o una decisión de lo que hace el código hoy; lo que no está documentado lo dice y propone `FI-XX`. Si se pide, `output/consultas/<tema>.md`.
- **Tokens**: en cada uso.

## Ejecución en vivo

Gastan tokens en cada corrida: sirven para casos sueltos. Lo que se repite conviene automatizarlo con los mappers.

### ejecutor-e2e
- **Cuándo**: para correr en el navegador casos o escenarios que no están automatizados.
- **Pedido de ejemplo**: *"Ejecutá CP-001 y CP-002 de HU-001 contra https://tu-app.com en headless"*.
- **Usa**: skill `ejecucion-e2e`; conectores `playwright` (headed, ves el navegador) o `playwright-headless`; `scripts/generar_reporte.py`.
- **Entrega**: en `output/ejecuciones/`, `reporte-HU-XXX-<fecha-hora>.html` + `_resultados-HU-XXX-<fecha-hora>.json`, y capturas en `evidencia/`.
- **Confirma**: el modo (headed o headless) si no lo dijiste. Las credenciales salen del `.env`.
- **Tokens**: en cada uso.

### ejecutor-api
- **Cuándo**: para correr una colección de Postman contra una API.
- **Pedido de ejemplo**: *"Corré la colección de input/api para HU-001"*.
- **Usa**: skill `ejecucion-api`; Newman, con `scripts/correr_newman.py` (token y URL del `.env`, en cualquier sistema).
- **Entrega**: en `output/ejecuciones/`, `reporte-HU-XXX-<fecha-hora>.html` + `_resultados-HU-XXX-<fecha-hora>.json`.
- **Tokens**: en cada uso.

### analista-seguridad
- **Cuándo**: para revisar la seguridad de una web propia o autorizada.
- **Pedido de ejemplo**: *"Revisá la seguridad de https://staging.tu-app.com para HU-001"*.
- **Usa**: OWASP ZAP en modo pasivo (Docker), `herramientas/zap/escanear.py` y `scripts/generar_informe_seguridad.py`.
- **Entrega**: en `output/seguridad/<HU>/<fecha>/`, `informe-seguridad.html` (hallazgos por riesgo, evidencia, cómo corregir, recomendaciones), `zap.json` y `analisis.json`.
- **Confirma**: la URL (tiene que estar en `SEGURIDAD_URLS_AUTORIZADAS`) y la duración del escaneo. Nunca escanea en modo activo.
- **Tokens**: en cada uso.

### explorador-web
- **Cuándo**: para hacer pruebas exploratorias de un sitio: buscar links e imágenes rotas, errores de JavaScript y de consola, y revisar el responsive en varias resoluciones.
- **Pedido de ejemplo**: *"Hacé pruebas exploratorias del sitio del .env"* · *"Buscá links rotos y problemas de responsive en https://staging.tu-app.com"*.
- **Usa**: skill `ejecucion-e2e`; `npm run explorar` (recorrido automático con Playwright, `herramientas/k0lmena/tools/explorador/explorar.js`), conectores `playwright` o `playwright-headless` para la exploración manual y `scripts/generar_informe_exploratorio.py`.
- **Entrega**: en `output/exploratorias/<HU o host>/` (cada corrida reemplaza a la anterior), `informe-exploratorio.html` (indicadores, gráficos, hallazgos por severidad con su captura, tiempos de carga, matriz de responsive, videos, galerías, links rotos, detalle por página y recomendaciones), `exploracion.json`, `analisis.json`, `capturas/` y `videos/`.
- **Confirma**: el modo (headed o headless) si no lo dijiste. No envía formularios ni cambia datos sin tu ok; en producción pide confirmación antes de explorar.
- **Tokens**: en cada uso (el recorrido de páginas lo hace el script, sin tokens por página).

### analista-accesibilidad
- **Cuándo**: para auditar la accesibilidad de un sitio contra WCAG 2.2 (AA por defecto): contraste, textos alternativos, etiquetas, navegación con teclado, lectores de pantalla.
- **Pedido de ejemplo**: *"Revisá la accesibilidad del sitio del .env"* · *"Auditá WCAG AA del registro de HU-001"*.
- **Usa**: skill `ejecucion-e2e`; `npm run accesibilidad` (axe-core en cada página, navegación con Tab y reflow a 320px, `herramientas/k0lmena/tools/accesibilidad/auditar.js`), conectores `playwright` o `playwright-headless` para la revisión manual (snapshot de accesibilidad) y `scripts/generar_informe_accesibilidad.py`.
- **Entrega**: en `output/accesibilidad/<HU o host>/` (cada corrida reemplaza a la anterior), `informe-accesibilidad.html` (cumplimiento, criterios WCAG incumplidos, cada problema con su captura y cómo corregirlo, teclado y orden del foco, revisión manual y recomendaciones), `auditoria.json`, `analisis.json`, `capturas/` y `videos/`.
- **Confirma**: el modo (headed o headless) si no lo dijiste. No envía formularios sin tu ok. Nunca afirma que el sitio "cumple": la parte automática detecta solo una parte de los problemas.
- **Tokens**: en cada uso (las reglas automáticas las corre el script, sin tokens por página).

### auditor-rendimiento-web
- **Cuándo**: para saber qué tan rápido carga cada página para una persona y por qué (no es una prueba de carga: eso es el performance-mapper).
- **Pedido de ejemplo**: *"Revisá la velocidad del sitio del .env"* · *"¿Por qué carga lenta la home en mobile?"*.
- **Usa**: `npm run rendimiento` (Lighthouse en mobile y desktop, con los textos en español, `herramientas/k0lmena/tools/rendimiento/auditar.js`) y `scripts/generar_informe_rendimiento.py`.
- **Entrega**: en `output/rendimiento/<HU o host>/` (cada corrida reemplaza a la anterior), `informe-rendimiento.html` (puntajes, Core Web Vitals con sus umbrales, oportunidades con el ahorro estimado, peso por tipo de recurso, elemento LCP, terceros y secuencia de carga), `rendimiento.json`, `capturas/` y el reporte nativo de Lighthouse de cada página.
- **Confirma**: nada con efecto (solo carga las páginas). Necesita Node 22.19 o superior.
- **Tokens**: en cada uso (las mediciones las hace el script).

### pixel-perfect
- **Cuándo**: para detectar si algo se corrió o cambió visualmente (después de un deploy, de un cambio de estilos o contra el diseño).
- **Pedido de ejemplo**: *"Corré una regresión visual de qarmy.ar"* · *"¿Se corrió algo en el checkout después del deploy?"* · *"Compará la home contra el diseño de Figma"*.
- **Usa**: skill `ejecucion-e2e`; `npm run pixel-perfect` (captura estable de cada página en cada resolución, comparación píxel a píxel y elemento por elemento, `herramientas/k0lmena/tools/pixel-perfect/` y `tools/visual/`) y `scripts/generar_informe_pixel_perfect.py`. Con el conector `figma`, la referencia puede ser el diseño.
- **Entrega**: en `output/pixel-perfect/<HU o host>/`, `informe-pixel-perfect.html` (comparador deslizable referencia/actual, mapa de diferencias, matriz de pantallas, qué se corrió y cuántos píxeles, bloques desplazados con su causa, faltantes, nuevos, textos y estilos cambiados, con el antes y después de cada uno). La referencia (`referencia/`) se conserva entre corridas.
- **Confirma**: aceptar los cambios como nueva referencia (`--aceptar`).
- **Tokens**: en cada uso (la comparación la hace el script).

### cross-browser
- **Cuándo**: para saber si algo funciona o se ve distinto en Chrome/Edge, Firefox o Safari.
- **Pedido de ejemplo**: *"Probá HU-003 en Chrome, Firefox y Safari"* · *"¿Por qué el menú no anda en Safari?"* · *"Revisá qarmy.ar en todos los navegadores"*.
- **Usa**: skill `ejecucion-e2e`; `npm run cross-browser` (modo suite: la suite web de k0lmena en cada navegador; modo páginas: recorre y compara contra el navegador base, `herramientas/k0lmena/tools/cross-browser/`) y `scripts/generar_informe_cross_browser.py`.
- **Entrega**: en `output/cross-browser/<HU, host o suite>/`, `informe-cross-browser.html` (navegadores y versiones, matriz escenario o página × navegador con capturas, comparador contra el navegador base, hallazgos exclusivos de un navegador y recomendaciones).
- **Confirma**: el modo suite (corre contra el ambiente) e instalar navegadores que falten.
- **Tokens**: en cada uso.

### verificador-correos
- **Cuándo**: para verificar los mails que manda la aplicación: registro, confirmación, recuperar contraseña, pedidos, notificaciones.
- **Pedido de ejemplo**: *"Verificá que llegue el mail de bienvenida a ana@test.com"* · *"Revisá los correos de HU-004"*.
- **Usa**: skills `investigacion-contexto` (qué tiene que decir cada mail), `ejecucion-e2e` (disparar el envío) y `automatizacion-k0lmena` (steps de correo en los `.feature`); **Mailpit** como buzón de prueba (`herramientas/mailpit/`), `npm run correos` y `scripts/generar_informe_correos.py`.
- **Entrega**: en `output/correos/<HU o buzón>/`, `informe-correos.html` (lo que tenía que llegar y si cumple, variables sin reemplazar, links rotos o a localhost, imágenes, texto plano, compatibilidad con Outlook y Gmail, vista desktop y mobile de cada correo) y el `.eml` original.
- **Confirma**: disparar envíos (crea datos) y vaciar el buzón. Solo usa buzones de prueba.
- **Tokens**: en cada uso; los steps de correo en los `.feature`, una vez.

### analista-traductor
- **Cuándo**: para revisar la traducción de la web en todos sus idiomas.
- **Pedido de ejemplo**: *"Revisá las traducciones del sitio en inglés y portugués"* · *"¿Quedó algo sin traducir en la versión en inglés?"*.
- **Usa**: skills `investigacion-contexto` (glosario) y `ejecucion-e2e`; `npm run traductor` (recorre cada página en cada idioma y resolución, `herramientas/k0lmena/tools/traductor/`) y `scripts/generar_informe_traductor.py`.
- **Entrega**: en `output/traductor/<HU o host>/`, `informe-traductor.html` (porcentaje traducido por idioma, textos sin traducir con la traducción propuesta, claves a la vista, caracteres rotos, textos cortados, formatos de número y fecha, atributo lang, páginas lado a lado).
- **Tokens**: en cada uso.

### evaluador-ux
- **Cuándo**: para revisar la usabilidad de un sitio o de un flujo (qué confunde, frena o hace equivocar a la persona).
- **Pedido de ejemplo**: *"Evaluá la usabilidad del checkout"* · *"Revisá las heurísticas de Nielsen en qarmy.ar"*.
- **Usa**: skills `ejecucion-e2e` (recorre los flujos a mano) e `investigacion-contexto`; `npm run ux` (`herramientas/k0lmena/tools/ux/`) y `scripts/generar_informe_ux.py`.
- **Entrega**: en `output/ux/<HU o host>/`, `informe-ux.html` (puntaje por heurística, hallazgos automáticos y manuales con su captura, la página 404, desktop y mobile, recomendaciones).
- **Confirma**: avanzar en un flujo que crea datos.
- **Tokens**: en cada uso.

### probador-formularios
- **Cuándo**: para probar las validaciones de un formulario campo por campo (obligatorios, largos, formatos, límites, mensajes).
- **Pedido de ejemplo**: *"Probá las validaciones del formulario de registro"* · *"¿Qué acepta el campo email?"*.
- **Usa**: skills `ejecucion-e2e` e `investigacion-contexto` (las reglas de la historia); `npm run formularios` (`herramientas/k0lmena/tools/formularios/`) y `scripts/generar_informe_formularios.py`.
- **Entrega**: en `output/formularios/<HU o host>/`, `informe-formularios.html` (matriz campo × prueba con el valor, lo esperado, lo que hizo y el mensaje; capturas con los errores a la vista; valores inválidos aceptados y válidos rechazados).
- **Confirma**: enviar el formulario vacío (`--enviar-vacio`). Nunca envía otra cosa.
- **Tokens**: en cada uso (las pruebas las hace el script).

### probador-permisos
- **Cuándo**: para verificar que cada rol vea y pueda hacer solo lo que le corresponde (antes de una release, al sumar un rol o una pantalla protegida).
- **Pedido de ejemplo**: *"Probá los permisos de admin, operador e invitado en https://staging.mi-app.com"* · *"¿Un operador puede entrar al panel de administración escribiendo la URL?"*.
- **Entradas**: la URL (`APP_URL`), los roles y sus credenciales en el `.env` (`PERMISOS_ROLES`, `PERMISOS_<ROL>_USUARIO`/`_CLAVE`/`_TOKEN`), endpoints opcionales y la regla esperada (`input/documentacion/proyecto/estados-y-permisos.md`, el dossier o la historia).
- **Usa**: `npm run permisos` (inicia sesión con cada rol más el anónimo, recorre el sitio, abre cada ruta con cada rol por URL directa y pide los endpoints con la sesión y el token de cada rol; solo GET) y `scripts/generar_informe_permisos.py`; skills `investigacion-contexto` (la regla esperada) y `ejecucion-e2e` (revisión puntual con Playwright MCP).
- **Entrega**: en `output/permisos/<HU o host>/`, `informe-permisos.html` (matriz rol × ruta y rol × endpoint, diferencias con lo esperado, hallazgos con captura, qué menús y botones ve cada rol, Falta información y evolución de las corridas), `permisos.json` y `capturas/`. No guarda credenciales.
- **Tokens**: en cada uso (el recorrido y la matriz los hace el script).
- **Confirma**: cualquier clic en botones con efecto y correr contra producción.

### probador-resiliencia
- **Cuándo**: para saber cómo reacciona la interfaz cuando algo falla abajo: la API se cae o tarda, la red se corta o no cargan los recursos.
- **Pedido de ejemplo**: *"Probá qué pasa en el listado de productos si la API se cae"* · *"Pruebas de resiliencia de https://staging.mi-app.com con red lenta y sin conexión"*.
- **Entradas**: la URL o las páginas (`APP_URL` por defecto), los escenarios (todos por defecto) y, opcional, el patrón de la API y la historia.
- **Usa**: `npm run resiliencia` (Playwright intercepta la red desde el navegador: API con 500, 503 o 404, timeout, red lenta, sin conexión, respuestas vacías, JSON roto o campos en null, y estáticos que no cargan), la exploración manual con Playwright MCP (skill `ejecucion-e2e`), el skill `investigacion-contexto` para saber qué se espera ante cada falla y `scripts/generar_informe_resiliencia.py`.
- **Entrega**: en `output/resiliencia/<HU o host>/`, `informe-resiliencia.html` (matriz página × escenario, pantallas en blanco, fallas silenciosas, spinners infinitos, mensajes técnicos, errores de JavaScript, reintentos y recuperación, con captura de cada escenario), `resiliencia.json` y `capturas/`. No envía formularios ni genera carga contra el servidor.
- **Tokens**: en cada uso (la simulación y la observación las hace el script).

## Reportes

### generador-reporte-html
- **Cuándo**: para regenerar el reporte de una corrida desde su JSON (los ejecutores ya lo generan solos).
- **Pedido de ejemplo**: *"Rearmá el reporte de output/ejecuciones/_resultados-HU-001-20261010-1030.json"*.
- **Usa**: `scripts/generar_reporte.py`.
- **Entrega**: `output/ejecuciones/reporte-HU-XXX-<fecha-hora>.html`.
- **Tokens**: en cada uso (poco: el script hace el trabajo).

### generador-reporte-cierre
- **Cuándo**: al terminar una ronda o historia, para decidir si sale.
- **Pedido de ejemplo**: *"Armá el informe de cierre de HU-001"*.
- **Usa**: `scripts/recolectar_resultados.py` (junta ejecuciones en vivo, `npm test`, bugs, performance y seguridad) y `scripts/generar_informe_cierre.py`.
- **Entrega**: `output/informes-cierre/cierre-HU-XXX-<fecha>.html` con la recomendación (Apto / Apto con observaciones / No apto), resultados, bugs por severidad, alcance, riesgos y falta información.
- **Tokens**: en cada uso.

### analista-cobertura
- **Cuándo**: para saber qué falta probar de una historia o de la ronda.
- **Pedido de ejemplo**: *"¿Qué nos falta probar de HU-001?"* · *"Armá la matriz de trazabilidad de la ronda"*.
- **Usa**: skill `investigacion-contexto` (los criterios de Jira o Azure DevOps si no están en archivos); `scripts/analizar_cobertura.py` y `scripts/generar_informe_cobertura.py`.
- **Entrega**: en `output/cobertura/<HU o todas>/`, `informe-cobertura.html` (embudo de la historia al resultado, cobertura por criterio, matriz de trazabilidad caso por caso y huecos priorizados) y `cobertura.json`.
- **Confirma**: nada (solo lee).
- **Tokens**: en cada uso (el cruce lo hace el script).

### tablero-calidad
- **Cuándo**: para saber cómo viene un sprint o una release, o para un resumen para gerencia.
- **Pedido de ejemplo**: *"Armá el tablero de calidad del sprint 12 (del 1 al 14 de octubre)"*.
- **Usa**: `scripts/tablero_calidad.py` (lee ejecuciones, `npm test` y su historial, el inventario de casos, cobertura, bugs, fallos, accesibilidad, rendimiento, performance y seguridad); opcional `scripts/avisar.py` para publicar el resumen en Slack o Teams.
- **Entrega**: `output/tablero/<nombre>/` con `informe-tablero.html` y `tablero.json`: aprobados y tendencia, % automatizado, cobertura, bugs por severidad e historia, inestables, minutos de ejecución manual, alertas, resumen ejecutivo, riesgos y recomendaciones. Lo que no tiene datos dice "Sin datos". Historial de 5 corridas.
- **Tokens**: en cada uso (el cruce lo hace el script).

## Automatización con k0lmena

Escriben la automatización **una vez**; después corre sin agentes ni tokens con `npm test` o `npm run perf`.

### web-mapper
- **Cuándo**: para automatizar casos web.
- **Pedido de ejemplo**: *"Automatizá en k0lmena los casos de HU-001 contra https://tu-app.com"*.
- **Usa**: skills `automatizacion-k0lmena`, `ejecucion-e2e` e `investigacion-contexto`; conectores `playwright` / `playwright-headless`; k0lmena web (Playwright + Cucumber).
- **Entrega**: `herramientas/k0lmena/web/features/HU-XXX-<tema>.feature`, `steps/HU-XXX.steps.ts`, `locators/HU-XXX.locators.ts` y `output/mapeos/mapeo-HU-XXX-web.md`. Se corre con `npm run test:web`.
- **Confirma**: headed o headless, si no lo dijiste.
- **Tokens**: una vez.

### api-mapper
- **Cuándo**: para automatizar pruebas de API desde una colección de Postman o un Swagger/OpenAPI.
- **Pedido de ejemplo**: *"Automatizá los endpoints de /pet de https://petstore.swagger.io/v2/swagger.json"*.
- **Usa**: skills `automatizacion-k0lmena`, `investigacion-contexto` y `tecnicas-de-diseno`; k0lmena api (axios + Cucumber, steps genéricos).
- **Entrega**: `herramientas/k0lmena/api/features/*.feature` y `output/mapeos/mapeo-<HU o contrato>-api.md`. Se corre con `npm run test:api`.
- **Confirma**: el alcance y los métodos con efecto (POST, PUT, PATCH, DELETE) antes de llamarlos.
- **Tokens**: una vez.

### mobile-mapper
- **Cuándo**: para automatizar casos de una app Android o iOS.
- **Pedido de ejemplo**: *"Automatizá los casos de HU-005 en el emulador de Android"*.
- **Usa**: skills `automatizacion-k0lmena` e `investigacion-contexto`; conector `appium-mcp` (se activa con `npm run conector -- activar appium-mcp`); k0lmena mobile (WebdriverIO + Appium).
- **Entrega**: `herramientas/k0lmena/mobile/features`, `steps` y `locators` de la historia, y `output/mapeos/mapeo-HU-XXX-mobile.md`. Se corre con `npm run test:mobile`.
- **Tokens**: una vez.

### performance-mapper
- **Cuándo**: para pruebas de carga, estrés, resistencia o picos.
- **Pedido de ejemplo**: *"Quiero hacer una prueba de carga del login"*. Antes, Claude te guía paso a paso con el skill `guia-performance` (tipo de prueba, herramienta, usuarios, rampa, duración, umbrales).
- **Usa**: skills `guia-performance` y `automatizacion-k0lmena`; k6, Artillery + Playwright o JMeter; `scripts/generar_informe_performance.py`.
- **Entrega**: el script en `herramientas/k0lmena/performance/`, el plan y el informe (métricas, gráficos, hallazgos, recomendaciones) en `output/performance/HU-XXX/`. Se vuelve a correr con `npm run perf -- <script> <perfil>`.
- **Confirma**: cada corrida con carga.
- **Tokens**: una vez (más el análisis del informe).

### verificador-datos
- **Cuándo**: para revisar qué dejaron guardado las pruebas o verificar un dato en una base.
- **Pedido de ejemplo**: *"Verificá en la base si existe el usuario ana@test.com"* · *"Sumá al escenario de registro la verificación en la base"*.
- **Usa**: skill `automatizacion-k0lmena` (steps de base de datos); `npm run bd` (PostgreSQL, MySQL/MariaDB, SQL Server, MongoDB).
- **Entrega**: la respuesta en el chat (y `output/verificaciones-datos/` si lo pedís); los steps de BD en el `.feature` solo si los pedís.
- **Confirma**: toda escritura (y nunca escribe en producción).
- **Tokens**: en cada consulta; las verificaciones en los `.feature`, una vez.

### analista-fallos
- **Cuándo**: cuando `npm test` falla, para separar los bugs reales de los tests rotos, inestables, de datos o de ambiente.
- **Pedido de ejemplo**: *"Analizá por qué falló npm test"* · *"¿Cuáles de estas fallas son bugs?"*.
- **Usa**: `scripts/analizar_fallos.py` (clasifica, rescata captura, video y trace, compara con reintentos) y `scripts/generar_informe_fallos.py`; skill `ejecucion-e2e` para reproducir a mano si hace falta.
- **Entrega**: en `output/fallos/<HU o suite>/`, `informe-fallos.html` (fallas por causa, historial de corridas, error, evidencia y qué hacer) y los bugs reales en `output/reportes-bug/`.
- **Confirma**: volver a correr los fallidos (corre contra el ambiente) y cargar bugs en Jira o Azure DevOps.
- **Tokens**: en cada uso.

### reparador-automatizacion
- **Cuándo**: cuando tests automatizados fallan porque la pantalla cambió (locators que ya no encuentran el elemento o encuentran varios) o por esperas.
- **Pedido de ejemplo**: *"Repará los tests que fallaron por locators"* · *"Arreglá la automatización de HU-001 después del rediseño"*.
- **Usa**: skills `automatizacion-k0lmena` (convenciones de locators) y `ejecucion-e2e`; `npm run reparar` (lee el error y el DOM que k0lmena guarda al fallar, diagnostica, propone un locator único y robusto, lo aplica con respaldo y diff y verifica, `herramientas/k0lmena/tools/reparador/`) y `scripts/generar_informe_reparacion.py`. Puede partir del análisis del `analista-fallos`.
- **Entrega**: los locators corregidos en `herramientas/k0lmena/web/` y, en `output/reparaciones/<HU o suite>/`, `informe-reparacion.html` (diagnóstico, cambio como diff, candidatos, capturas del elemento original y del propuesto, verificación), `cambios.diff` y `respaldo/`.
- **Confirma**: aplicar las reparaciones que no son seguras (confianza media o baja, pasos de verificación, datos del `.feature`) y volver a correr los escenarios. Nunca cambia un test para tapar un bug.
- **Tokens**: en cada uso (el diagnóstico lo hace el script).

### analista-logs
- **Cuándo**: para entender qué pasó en el servidor: errores, picos y el error que hay detrás de una prueba que falló.
- **Pedido de ejemplo**: *"Analizá los logs de la corrida de hoy"* · *"¿Por qué falló CP-004 del lado del servidor?"*.
- **Usa**: `scripts/analizar_logs.py` (logs de la app, nginx, Apache, JSON y syslog; cruza con los escenarios de `npm test`, que guardan su inicio y fin) y `scripts/generar_informe_logs.py`.
- **Entrega**: en `output/logs/<nombre>/`, `informe-logs.html` (errores y advertencias por minuto, firmas con su stack trace, cada escenario fallido con los errores del servidor mientras corría).
- **Confirma**: bajar logs de un servidor compartido.
- **Tokens**: en cada uso (el agrupado y el cruce los hace el script).

## Gestión de pruebas

### gestor-pruebas
- **Cuándo**: para llevar los casos a la herramienta del equipo y armar los ciclos.
- **Pedido de ejemplo**: *"Subí los casos de HU-001 a Xray en la carpeta 'HU-001 Registro', vinculados a PROJ-12"*.
- **Usa**: `scripts/gestion/gestion.py` (Xray Cloud, Xray Server/DC, QTM4J y AIO Tests); para Azure Test Plans, el conector `azure-devops` y `scripts/gestion/para_azure_devops.py`.
- **Entrega**: carpetas, casos, vínculos con la historia y ciclos en la herramienta, y la trazabilidad `output/gestion/HU-XXX-<herramienta>.json`.
- **Confirma**: carpeta, historia y ciclo; la primera vez, una prueba en seco (`--dry-run`).
- **Tokens**: en cada uso (poco: el script hace el trabajo).

### publicador-resultados
- **Cuándo**: después de correr `npm test`, para cargar los resultados en el ciclo.
- **Pedido de ejemplo**: *"Subí los resultados de la última corrida web al ciclo PROJ-60"*.
- **Usa**: `scripts/gestion/gestion.py` (`extraer-resultados` y `publicar-resultados`).
- **Entrega**: el estado de cada caso en el ciclo, con el error y las evidencias (captura, GIF y video si falló). Publica una historia por vez para no mezclar casos. Azure DevOps todavía no.
- **Confirma**: el ciclo, si lo propuso él.
- **Tokens**: en cada uso (poco: el script hace el trabajo).

---

## Skills: el "cómo" que usan los agentes

Los skills se cargan solo cuando hacen falta.

| Skill                  | Qué enseña                                                                                                                                                         | Lo usan                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| investigacion-contexto | Investigar la historia completa (documentación del proyecto, comentarios, subtareas, épica, Confluence, Figma, contratos) y registrar la Falta información (FI-XX) | analista-historias, estratega-pruebas, generadores de casos y datos, web-mapper, api-mapper, mobile-mapper, analista-cobertura, selector-casos-de-prueba, verificador-correos, analista-traductor, revisor-casos, generador-charters, evaluador-ux, probador-formularios, documentador-proyecto, probador-permisos, probador-resiliencia, consultor-proyecto |
| tecnicas-de-diseno     | Equivalencia, valores límite, tabla de decisión, transición de estados y pairwise                                                                                  | generador-casos-manuales, generador-casos-bdd, generador-casos-api, api-mapper, revisor-casos, generador-charters                                                                                                                                                                                                                                            |
| ejecucion-e2e          | Ejecutar en el navegador con Playwright MCP: modos, snapshots, esperas y evidencia                                                                                 | ejecutor-e2e, web-mapper, explorador-web, analista-accesibilidad, analista-fallos, pixel-perfect, cross-browser, reparador-automatizacion, verificador-correos, analista-traductor, generador-charters, evaluador-ux, probador-formularios, documentador-proyecto, probador-permisos, probador-resiliencia                                                   |
| ejecucion-api          | Correr colecciones con Newman: base_url, token, validaciones y resultados                                                                                          | ejecutor-api                                                                                                                                                                                                                                                                                                                                                 |
| automatizacion-k0lmena | Convenciones de k0lmena: features, steps, locators, tags, steps de BD y scripts de performance                                                                     | web-mapper, api-mapper, mobile-mapper, performance-mapper, verificador-datos, reparador-automatizacion, verificador-correos                                                                                                                                                                                                                                  |
| guia-performance       | Guía paso a paso para planificar una prueba de performance con la persona                                                                                          | la conversación principal (antes de performance-mapper) y performance-mapper                                                                                                                                                                                                                                                                                 |

## Herramientas y scripts: quién usa qué

| Herramienta o script                                                             | Para qué                                                                                                  | La usan                                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| k0lmena (herramientas/k0lmena)                                                   | Automatización web, API, mobile y performance; corre sin tokens                                           | web-mapper, api-mapper, mobile-mapper, performance-mapper, verificador-datos                                                                                                                                                                                                                               |
| Playwright MCP                                                                   | Navegador en vivo                                                                                         | ejecutor-e2e, web-mapper, explorador-web, analista-accesibilidad, analista-fallos, pixel-perfect, cross-browser, reparador-automatizacion, verificador-correos, analista-traductor, generador-charters, evaluador-ux, probador-formularios, documentador-proyecto, probador-permisos, probador-resiliencia |
| Newman (herramientas/newman)                                                     | Colecciones de Postman                                                                                    | ejecutor-api                                                                                                                                                                                                                                                                                               |
| OWASP ZAP (herramientas/zap)                                                     | Seguridad web pasiva                                                                                      | analista-seguridad                                                                                                                                                                                                                                                                                         |
| k6 · Artillery · JMeter                                                          | Performance                                                                                               | performance-mapper                                                                                                                                                                                                                                                                                         |
| scripts/generar_casos.py                                                         | Planilla y Markdown de casos                                                                              | generador-casos-manuales                                                                                                                                                                                                                                                                                   |
| scripts/formatear_tablas.py                                                      | Tablas alineadas en los .md                                                                               | casi todos los que escriben .md                                                                                                                                                                                                                                                                            |
| scripts/generar_plan.py                                                          | Plan de pruebas HTML                                                                                      | estratega-pruebas                                                                                                                                                                                                                                                                                          |
| scripts/generar_reporte.py                                                       | Reporte HTML de una corrida                                                                               | ejecutor-e2e, ejecutor-api, generador-reporte-html                                                                                                                                                                                                                                                         |
| scripts/correr_newman.py                                                         | Newman con el .env y su reporte                                                                           | ejecutor-api                                                                                                                                                                                                                                                                                               |
| scripts/recolectar_resultados.py · generar_informe_cierre.py                     | Informe de cierre                                                                                         | generador-reporte-cierre                                                                                                                                                                                                                                                                                   |
| scripts/generar_informe_performance.py                                           | Informe de performance                                                                                    | performance-mapper                                                                                                                                                                                                                                                                                         |
| scripts/generar_informe_seguridad.py                                             | Informe de seguridad                                                                                      | analista-seguridad                                                                                                                                                                                                                                                                                         |
| npm run explorar (k0lmena tools/explorador)                                      | Recorrido: links, imágenes, errores y responsive                                                          | explorador-web                                                                                                                                                                                                                                                                                             |
| scripts/generar_informe_exploratorio.py                                          | Informe de pruebas exploratorias                                                                          | explorador-web                                                                                                                                                                                                                                                                                             |
| npm run accesibilidad (k0lmena tools/accesibilidad)                              | Auditoría de accesibilidad: axe-core, teclado y reflow                                                    | analista-accesibilidad                                                                                                                                                                                                                                                                                     |
| scripts/generar_informe_accesibilidad.py                                         | Informe de accesibilidad                                                                                  | analista-accesibilidad                                                                                                                                                                                                                                                                                     |
| npm run rendimiento (k0lmena tools/rendimiento)                                  | Lighthouse: velocidad de carga y Core Web Vitals                                                          | auditor-rendimiento-web                                                                                                                                                                                                                                                                                    |
| scripts/generar_informe_rendimiento.py                                           | Informe de rendimiento web                                                                                | auditor-rendimiento-web                                                                                                                                                                                                                                                                                    |
| scripts/analizar_fallos.py · generar_informe_fallos.py                           | Clasifica las fallas de npm test e informe                                                                | analista-fallos                                                                                                                                                                                                                                                                                            |
| scripts/analizar_cobertura.py · generar_informe_cobertura.py                     | Matriz de cobertura y trazabilidad e informe                                                              | analista-cobertura                                                                                                                                                                                                                                                                                         |
| npm run pixel-perfect (k0lmena tools/pixel-perfect y tools/visual)               | Regresión visual: captura estable y comparación píxel a píxel y por elemento                              | pixel-perfect                                                                                                                                                                                                                                                                                              |
| scripts/generar_informe_pixel_perfect.py                                         | Informe de regresión visual                                                                               | pixel-perfect                                                                                                                                                                                                                                                                                              |
| npm run cross-browser (k0lmena tools/cross-browser)                              | Suite o páginas en Chromium, Firefox y WebKit                                                             | cross-browser                                                                                                                                                                                                                                                                                              |
| scripts/generar_informe_cross_browser.py                                         | Informe cross-browser                                                                                     | cross-browser                                                                                                                                                                                                                                                                                              |
| npm run reparar (k0lmena tools/reparador)                                        | Diagnostica, propone, aplica y verifica locators                                                          | reparador-automatizacion                                                                                                                                                                                                                                                                                   |
| scripts/generar_informe_reparacion.py                                            | Informe de reparación de la automatización                                                                | reparador-automatizacion                                                                                                                                                                                                                                                                                   |
| scripts/seleccionar_casos.py · generar_informe_seleccion.py                      | Selección de casos por cambio e informe                                                                   | selector-casos-de-prueba                                                                                                                                                                                                                                                                                   |
| Mailpit (herramientas/mailpit) · npm run correos                                 | Buzón de prueba y revisión de los correos                                                                 | verificador-correos                                                                                                                                                                                                                                                                                        |
| scripts/generar_informe_correos.py                                               | Informe de correos                                                                                        | verificador-correos                                                                                                                                                                                                                                                                                        |
| npm run traductor (k0lmena tools/traductor)                                      | Cada página en cada idioma: traducción, cortes y formatos                                                 | analista-traductor                                                                                                                                                                                                                                                                                         |
| scripts/generar_informe_traductor.py                                             | Informe de traducciones                                                                                   | analista-traductor                                                                                                                                                                                                                                                                                         |
| scripts/_historial.py · k0lmena tools/historial                                  | Últimas 5 corridas de cada herramienta y su comparación                                                   | todos los que generan informes                                                                                                                                                                                                                                                                             |
| scripts/estimacion.py                                                            | Tiempo estimado de ejecución manual de cada caso (planilla, herramienta de gestión, selección y revisión) | generador-casos-manuales, generador-casos-bdd, gestor-pruebas, revisor-casos, selector-casos-de-prueba                                                                                                                                                                                                     |
| scripts/revisar_casos.py · generar_informe_revision.py                           | Calidad de los casos e informe                                                                            | revisor-casos                                                                                                                                                                                                                                                                                              |
| scripts/generar_charters.py                                                      | Hojas de sesión e informe de sesiones exploratorias                                                       | generador-charters                                                                                                                                                                                                                                                                                         |
| npm run ux (k0lmena tools/ux) · generar_informe_ux.py                            | Heurísticas de Nielsen e informe                                                                          | evaluador-ux                                                                                                                                                                                                                                                                                               |
| npm run formularios (k0lmena tools/formularios) · generar_informe_formularios.py | Validaciones de formularios e informe                                                                     | probador-formularios                                                                                                                                                                                                                                                                                       |
| scripts/analizar_logs.py · generar_informe_logs.py                               | Logs agrupados, cruzados con la corrida, e informe                                                        | analista-logs                                                                                                                                                                                                                                                                                              |
| npm run mapa-funcional (k0lmena tools/mapa-funcional) · indice_documentacion.py  | Mapa funcional de la web e índice de input/documentacion/                                                 | documentador-proyecto                                                                                                                                                                                                                                                                                      |
| npm run permisos (k0lmena tools/permisos) · generar_informe_permisos.py          | Matriz de permisos por rol e informe                                                                      | probador-permisos                                                                                                                                                                                                                                                                                          |
| npm run resiliencia (k0lmena tools/resiliencia) · generar_informe_resiliencia.py | Fallas simuladas de API, red y recursos, e informe                                                        | probador-resiliencia                                                                                                                                                                                                                                                                                       |
| scripts/buscar_duplicados.py                                                     | Similitud entre bugs: duplicados, regresiones y relacionados                                              | triador-bugs                                                                                                                                                                                                                                                                                               |
| scripts/tablero_calidad.py                                                       | Tablero de calidad por sprint o release                                                                   | tablero-calidad                                                                                                                                                                                                                                                                                            |
| scripts/portal_informes.py (npm run portal)                                      | Portal con el último informe de cada herramienta (output/index.html, se actualiza solo)                   | todos los que generan informes                                                                                                                                                                                                                                                                             |
| scripts/avisar.py (npm run avisar)                                               | Avisos a Slack y Teams por webhook                                                                        | triador-bugs, tablero-calidad, monitoreo sintético, vos                                                                                                                                                                                                                                                    |
| npm run monitorear (k0lmena tools/monitoreo) · generar_informe_monitoreo.py      | Monitoreo sintético de solo lectura, con aviso cuando algo se rompe o se recupera                         | vos, el Programador de tareas, cron o GitHub Actions                                                                                                                                                                                                                                                       |
| scripts/cambios_documentacion.py                                                 | Documentación incremental: qué documentos y casos afecta un cambio del código                             | documentador-proyecto                                                                                                                                                                                                                                                                                      |
| scripts/convertir_coleccion.py · resumir_graphql.py                              | Bruno e Insomnia a Postman; resumen de un schema GraphQL                                                  | ejecutor-api, api-mapper, generador-casos-api                                                                                                                                                                                                                                                              |
| scripts/evaluar_agentes.py (npm run evals)                                       | Evals de los agentes: casos con trampas, chequeos e informe con regresiones                               | vos, al cambiar un agente o un skill                                                                                                                                                                                                                                                                       |
| scripts/gestion/                                                                 | Xray, QTM4J y AIO Tests; conversión para Azure Test Plans                                                 | gestor-pruebas, publicador-resultados                                                                                                                                                                                                                                                                      |
| scripts/doctor.py (npm run doctor)                                               | Revisa el entorno y la configuración                                                                      | vos, al instalar o cuando algo no anda                                                                                                                                                                                                                                                                     |

## Conectores: qué agentes los aprovechan

| Conector                         | Activo por defecto | Lo aprovechan                                                                                                                                                                                                                                                                                              |
| -------------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| playwright · playwright-headless | Sí                 | ejecutor-e2e, web-mapper, explorador-web, analista-accesibilidad, analista-fallos, pixel-perfect, cross-browser, reparador-automatizacion, verificador-correos, analista-traductor, generador-charters, evaluador-ux, probador-formularios, documentador-proyecto, probador-permisos, probador-resiliencia |
| atlassian (Jira y Confluence)    | Sí                 | todos los que investigan una historia (skill investigacion-contexto), generador-reportes-bug, documentador-proyecto (también Bitbucket Cloud, con token)                                                                                                                                                   |
| azure-devops                     | No                 | los mismos que atlassian, si tu equipo usa Azure DevOps; gestor-pruebas (Azure Test Plans); documentador-proyecto (Azure Repos)                                                                                                                                                                            |
| figma · figma-desktop            | No                 | los que investigan una historia (textos, estados y validaciones del diseño), web-mapper, pixel-perfect (comparar contra el diseño)                                                                                                                                                                         |
| qtm4j · qmetry · aio-tests       | No                 | consultas desde el chat (la carga de casos y resultados va por scripts/gestion)                                                                                                                                                                                                                            |
| k0lmena-tmt                      | No                 | cargar y consultar casos en k0lmenaTMT                                                                                                                                                                                                                                                                     |
| github · gitlab                  | No                 | documentador-proyecto (repositorio de la app, solo lectura), triador-bugs (issues)                                                                                                                                                                                                                         |
| appium-mcp                       | No                 | mobile-mapper                                                                                                                                                                                                                                                                                              |
