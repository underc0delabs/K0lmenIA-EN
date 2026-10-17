# Cambios de k0lmenIA

Los cambios más relevantes, del más nuevo al más viejo. El detalle de cada uno está en el historial de git.

## 2026-10-17 — Ahorro al automatizar en el tablero
- El tablero de calidad calcula el **ahorro de tiempo al automatizar**: el tiempo estimado de ejecución manual de los casos automatizados menos lo que tardan corriendo solos (`npm test`). Muestra el **ahorro por corrida** y el **acumulado** del período en los indicadores, y una columna de ahorro por historia. Usa el tiempo manual que ya se guardaba por caso y la duración real de la última corrida.

## 2026-10-17 — Prioridad en BDD y agente de pentest
- **Tag de prioridad en BDD**: los escenarios llevan `@critica`/`@alta`/`@media`/`@baja` (el equivalente de la columna *Prioridad* de los casos manuales). `scripts/gestion/lectores.py` lo lee (un tag explícito manda; `@smoke` sigue valiendo `Alta`); los mappers conservan ese tag en los `.feature` que generan. Antes un caso "Crítica" llegaba a la gestión como "Media". El tiempo estimado de ejecución manual ya se guardaba (columna *Tiempo estimado (min)* en manuales; calculado con `estimacion.py` en BDD), base para medir el ahorro al automatizar.
- **Nuevo agente `pentester-web`** (ethical hacking autorizado): intenta vulnerar un sitio **propio o con permiso escrito** con el escaneo activo de OWASP ZAP más verificación manual del OWASP Top 10 (control de acceso, autenticación, inyección, XSS, configuración, CSRF/SSRF) con Playwright MCP, confirma cada hallazgo y entrega el informe HTML (modo activo) más un `reporte-pentest.md` con pasos para reproducir y corrección. Solo URLs de `SEGURIDAD_URLS_AUTORIZADAS`, con `PENTEST_AUTORIZADO=si`, nunca producción sin autorización y sin técnicas destructivas (DoS, fuerza bruta masiva, borrado de datos).
- `herramientas/zap/escanear.py` suma `--activo` (full scan, gated por autorización) y `generar_informe_seguridad.py` distingue informe pasivo de activo (`--modo`).

## 2026-10-17 — Revisión de calidad de los agentes
- **Sin falsos verdes**: un `Then` que falla porque la app no cumple ya no se marca `@bloqueado` en web-mapper y mobile-mapper (`npm test` nunca lo corría y el bug quedaba oculto): queda activo con `# POSIBLE BUG`. Un request de Newman sin `pm.test` sale *Bloqueado* ("Sin validaciones"), no *Aprobado*.
- **Trazabilidad**: los casos manuales conservan los `CP-XXX` que la historia ya tenía (BDD, automatización, gestión); un `Scenario Outline` es un solo caso; `CP-API` se numera por historia o contrato. El informe de cierre y el tablero distinguen el mismo `CP` de dos historias (clave historia + ID) y toman los resultados de `npm test` también de `historial/`. La regla de HU contra key de la herramienta quedó en *Convenciones de IDs*.
- **Falta información** con un formato único (`{id, que_falta, pregunta}`) en todos los informes HTML; los datos de prueba y los casos de API ya no suponen reglas: las marcan como `FI-XX`.
- **Autorrevisión antes de entregar** en los generadores y analistas, y los scripts de informe avisan por stderr IDs o severidades del `analisis.json` que no existen.
- **Efectos y seguridad**: el ejecutor de API confirma los métodos con efecto; los mappers nunca contra producción; `--enviar-vacio` aprieta el botón del formulario correcto; el informe de seguridad enmascara secretos de la evidencia de ZAP.
- **Referencias corregidas**: `--dry-run` del publicador antes del subcomando, `--repo` obligatorio en el selector (diff desde la base común), `--aceptar` de pixel-perfect con su `--url`, reintentos de fallos por suite, `correr_newman.py --datos`, `formatear_tablas.py` con su archivo, estimación con etiquetas como texto, estados cerrados en español en el triador, plantillas de casos y cobertura sin supuestos presentados como hechos.
- `npm run debug` deja sus reportes en `reports/debug/` (ya no se mezclan con el reporte web) y la validación de los mappers web usa `REPORT_DIR=reports/validacion` para no pisar el último `npm test`.

## 2026-10-17 — npm test arma el reporte completo
- `npm test` genera solo, al terminar cada suite de web y API, el reporte completo de k0lmena (`reports/<suite>/index.html`, el de `npm run report:web` / `report:api`). Antes quedaba solo el HTML básico de Cucumber (`front-report.html`), y ese era el que enlazaba el portal de informes después de automatizar con el `web-mapper`.
- El portal muestra una sola entrada por suite con el reporte completo (el básico queda como "otro" y las páginas de `features/` no salen como informes aparte); el historial guarda también el reporte completo de cada corrida.

## 2026-10-16 — npm run configurar
- **`npm run configurar`**: asistente en español para dejar el proyecto listo sin saber nombres de variables ni de conectores. Pregunta la URL de la app y el usuario de prueba, dónde están las historias, dónde guardan los casos, dónde está el código y si usan Figma (opciones numeradas); pide solo los datos de lo elegido (los tokens no se muestran), los escribe en el `.env` (lo crea si no existe) y activa los conectores. Se puede correr de nuevo: Enter deja lo que ya estaba. `npm run conector` queda para lo puntual.

## 2026-10-16 — APIs desde un Swagger que funcionan
- `scripts/resumir_openapi.py`: resume un Swagger 2.0 u OpenAPI 3.x (JSON o YAML, por URL o archivo) con el `API_BASEURL` correcto (server + basePath, servers relativos y con variables), el step de autenticación de cada `securityScheme`, parámetros, body de ejemplo (JSON, formulario o multipart) y status documentados. Lo usan el `generador-casos-api` y el `api-mapper` en lugar de leer la spec a mano.
- Steps de API (`api/steps/comunes.steps.ts`): URL unida con una sola barra (antes `/v2/v2/pet` o `hostpet`), API key en header o query, autenticación básica, parámetros de query, formularios (`con el formulario:`), respuestas de texto plano, búsqueda de un elemento en una lista, tipos de la spec (`integer`, …), ids int64 sin perder precisión, timeout por request, `{variables}` sin valor que cortan con un mensaje claro y todas las credenciales ocultas en el reporte. Los steps que ya existían no cambian de texto.
- Datos únicos por escenario: `{aleatorio}`, `{uuid}`, `{timestamp}` y `{ahora}`.
- El `api-mapper` verifica cada `Then` contra la API, hace que cada escenario cree los datos que lee y marca `@difiere-de-la-spec` cuando la API no cumple la spec (para separar bugs de tests mal hechos). El `generador-casos-api` solo usa los status del contrato.

## 2026-10-16 — Cross-browser sin falsos positivos y la URL en un solo lugar
- **Cross-browser**: lo que falla solo en un navegador se confirma antes de informarlo. En suite, el escenario se repite en ese navegador (`--reintentos`, 2 por defecto) y si pasa queda *Inestable*; en páginas, la página se recarga en todos los navegadores y lo intermitente baja a *Baja* o se descarta.
- Los errores se comparan por su origen (archivo:línea:columna) y sus palabras propias, porque cada motor redacta distinto el mismo error (antes un error de todos los navegadores salía como "solo en Firefox"). Se ignora el ruido de consola de cada motor, los recursos se comparan sin query string y sin el favicon, y lo que un navegador pidió y los otros no pesa menos.
- Sin barras de scroll al comparar (Firefox las dibuja ocupando ancho), colores normalizados en sRGB (oklch y otros formatos), corrimientos por la medida del texto en *Baja* salvo que algo quede fuera de la pantalla, "faltantes" que estaban con el mismo texto, y Firefox en mobile (no emula un teléfono) con sus diferencias visuales en *Baja*.
- El agente ya no intenta reproducir en Firefox con Playwright MCP (abre Chromium): usa el script o la suite con `BROWSER=firefox`.
- **La URL de la app va solo en `APP_URL`**: k0lmena arma `BASEURL` desde ahí (`env.js`); `BASEURL` en el `.env` queda como nombre viejo y `npm run doctor` avisa si sobra o no coincide.

## 2026-10-16 — Sesión guardada con npm run login
- `npm run login` (k0lmena `tools/login`): abre el navegador, te logueás a mano (captcha, 2FA o SSO incluidos) y guarda la sesión (cookies, localStorage e IndexedDB) en `.auth/` (gitignored). `--nombre <rol>` guarda una por rol.
- Con `SESION=si` (o `SESION=<rol>`) en el `.env`, las suites web de k0lmena y el navegador de los agentes (Playwright MCP, con `--isolated --storage-state`) arrancan logueados. Los escenarios `@sin-sesion` arrancan sin sesión.

## 2026-10-14 (3) — Estilo k0lmena en la web, los diagramas, el PDF y los informes
- La web de documentación, los diagramas (y sus imágenes), el PDF y todos los informes HTML (los de Python y los reportes de k0lmena) usan el estilo de https://k0lmena.com: fondo noche y carbón, ámbar, miel y naranja, patrón de panal, etiquetas `// sección` y viñetas hexagonales.
- Tipografía de k0lmena incrustada: Saira (títulos), Inter (texto) y JetBrains Mono (código), con licencia OFL (`docs/assets/fuentes/` y `scripts/fuentes/`); reemplazan a Geist.
- Paleta de gráficos cálida y validada para contraste y daltonismo; los estados usan verde, miel, naranja y rojo cálido.
- La web arranca en oscuro (tema claro cálido opcional) y el PDF sale con el mismo estilo oscuro.
- Diagrama nuevo `docs/assets/img/relaciones.png`: cómo se relacionan agentes, skills, plantillas, scripts, herramientas y conectores MCP (en el README, la web y `ARQUITECTURA.md`).

## 2026-10-14 (3) — Buscador, versión en inglés, portal con filtros, doctor, onboarding y uso de tokens
- **Web con buscador** (Ctrl K o /): resultados por sección con el término resaltado, sin importar acentos, navegación con el teclado y salto al lugar exacto.
- **Versión en inglés** de la web (`docs/en/`), de los diagramas y del PDF (`docs/k0lmenIA-documentation.pdf`), con selector de idioma.
- **Portal de informes con filtros**: buscador, filtros por herramienta, historia, estado y fecha, y vista por historia.
- **`npm run doctor` más completo**: por secciones (también fuentes, integraciones del `.env`, git, workflows y la CLI de Claude), con `--seccion`, `--rapido` y `--json`; nunca muestra secretos.
- Nuevo agente `guia-onboarding`: plan de incorporación de un QA nuevo con el producto, su entorno, los agentes para su rol, las primeras tareas, preguntas y un checklist (`scripts/generar_onboarding.py`).
- **Uso de tokens** (`npm run metricas`, `scripts/metricas_tokens.py`): costo estimado por agente, día y modelo desde las transcripciones de Claude Code, con oportunidades de ahorro; el tablero de calidad lo suma.

## 2026-10-14 (2) — Permisos, resiliencia, triage, consultas, tablero, avisos, monitoreo, evals y más fuentes
- Nuevo agente `probador-permisos`: `npm run permisos` inicia sesión con cada rol (más el anónimo) y arma la matriz rol × ruta y rol × endpoint, con acceso por URL directa, menús y botones visibles por rol y diferencias con la regla documentada. Solo GET.
- Nuevo agente `probador-resiliencia`: `npm run resiliencia` intercepta la red desde el navegador (API con 500/503/404, timeout, red lenta, sin conexión, respuestas vacías, rotas o con nulos, estáticos que no cargan) y revisa pantallas en blanco, fallas silenciosas, spinners infinitos, mensajes técnicos, reintentos y recuperación.
- Nuevo agente `triador-bugs`: busca duplicados y posibles regresiones en Jira, Azure DevOps, los bugs locales y los issues del repositorio (`scripts/buscar_duplicados.py`) y sugiere severidad, componente, responsable e historia. El `generador-reportes-bug` lo sugiere antes de cargar un bug.
- Nuevo agente `consultor-proyecto`: responde preguntas del producto solo con la documentación del proyecto, citando la fuente o diciendo que no está documentado.
- Nuevo agente `tablero-calidad`: tablero por sprint o release (aprobados y tendencia, % automatizado, cobertura, bugs, inestables, tiempo manual) con resumen para gerencia.
- **Portal de informes**: `output/index.html` con el último informe de cada herramienta; se regenera solo al terminar cualquier informe.
- **Documentación incremental**: el `documentador-proyecto` guarda el estado de lo documentado (`.estado.json`), rehace solo lo que cambió y deja en `cambios.md` los casos a revisar (`scripts/cambios_documentacion.py`).
- **Avisos a Slack y Teams** por webhook (`scripts/avisar.py`, `npm run avisar`), con resumen de `npm test`.
- **Monitoreo sintético** de solo lectura (`npm run monitorear`): URLs, textos, tiempos, certificado y escenarios `@sintetico`; avisa cuando algo se rompe o se recupera; workflow programable `.github/workflows/monitoreo.yml`.
- **Evals de los agentes** (`evals/`, `scripts/evaluar_agentes.py`, `npm run evals`): casos con trampas deliberadas, chequeos determinísticos, workspace aislado con `claude -p` e informe con regresiones; workflow manual `.github/workflows/evals.yml`.
- **APIs**: GraphQL (steps genéricos en k0lmena, `scripts/resumir_graphql.py`, casos GraphQL en el generador) y colecciones de Bruno e Insomnia (`scripts/convertir_coleccion.py`, que `correr_newman.py` usa solo), con demos en `input/api/`.
- **Más herramientas de gestión**: conectores MCP oficiales de Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack y Shortcut como fuente de historias; el skill `investigacion-contexto` trae las equivalencias de campos de cada herramienta.
- Los tests no tocan el portal (`K0LMENIA_PORTAL=0`).

## 2026-10-14 — Documentador del proyecto y conexión al repositorio
- Nuevo agente `documentador-proyecto`: arma la documentación del proyecto en `input/documentacion/` para que el resto de los agentes trabaje con contexto real. Lee el repositorio de la aplicación en solo lectura (README y docs, validaciones y límites, mensajes, estados, roles y permisos, rutas, contratos de API y los PRs y commits de cada historia), las historias de Jira o Azure DevOps con sus comentarios, subtareas, épica, vínculos y links (Confluence, Wiki, Figma y páginas públicas; los privados quedan como *No accesible*) y la web. Deja una base del proyecto, un dossier por historia y un índice; cada dato con su fuente.
- **Repositorio de la aplicación** en el `.env` (`REPO_PROVEEDOR`, `REPO_NOMBRE`, `REPO_RAMA`, `REPO_RUTA_LOCAL`) con los servers MCP oficiales de cada proveedor: conectores nuevos `github` (remoto, modo solo lectura, `GITHUB_TOKEN`) y `gitlab` (`/api/v4/mcp`, OAuth o `GITLAB_TOKEN`) en el catálogo; Azure Repos con el dominio `repositories`, que ahora viene por defecto en `azure-devops`; Bitbucket Cloud con el conector `atlassian` y autenticación por token.
- `npm run mapa-funcional` (k0lmena `tools/mapa-funcional`): recorre el sitio solo con GET y documenta cada página (secciones, menús, formularios con cada campo y sus restricciones, botones, mensajes y tablas), sin enviar nada. Reutiliza el descubrimiento de páginas de pixel-perfect y la extracción de campos de formularios.
- `scripts/indice_documentacion.py`: índice de `input/documentacion/` con el tipo, las fuentes, la fecha y si conviene revisar cada documento.
- El skill `investigacion-contexto` lee primero la documentación del proyecto (el índice y el dossier de la historia), así que la aprovechan todos los agentes que investigan una historia; el código del repositorio cuenta como *observado*, no como requisito.
- `input/documentacion/` deja de versionarse (puede tener código e información interna del cliente).
- `npm run conector -- activar` toma del `.env` las variables de la URL de un conector (`GITLAB_URL`, `K0LMENA_TMT_URL`).

## 2026-10-11 (5) — Revisor de casos, charters, UX, formularios, logs y tiempo de ejecución
- **Tiempo estimado de ejecución manual** de cada caso (`scripts/estimacion.py`, fórmula en `plantillas/estimacion-tiempos.md`): columna *Tiempo estimado (min)* con el total en la planilla de casos y en el `.md`; al subir a la herramienta de gestión va en la descripción y en el campo nativo (Original Estimate en Xray Cloud y Server/DC, estimatedTime en QTM4J, estimatedEffort en AIO Tests; si se rechaza, se crea sin él); para Azure DevOps en el JSON y como etiqueta. Un valor cargado a mano en la planilla manda sobre la fórmula.
- Nuevo agente `revisor-casos`: puntaje por caso, resultados y pasos vagos, duplicados, escenarios sin Then o imperativos, historias sin negativos, tiempo de ejecución y versiones mejoradas.
- Nuevo agente `generador-charters`: charters de exploración por sesiones, hojas para imprimir, plantilla de notas e informe de las sesiones (bugs, preguntas, reparto del tiempo, áreas cubiertas).
- Nuevo agente `evaluador-ux`: `npm run ux` con las 10 heurísticas de Nielsen en desktop y mobile, la página 404 y la revisión manual de los flujos.
- Nuevo agente `probador-formularios`: `npm run formularios` prueba cada campo sin enviar (bloquea cualquier envío) y arma la matriz campo × prueba.
- Nuevo agente `analista-logs`: agrupa los errores de los logs por firma, la línea de tiempo y el cruce con los escenarios fallidos; los steps comunes de k0lmena guardan el inicio y fin de cada escenario.

## 2026-10-11 (4) — Correos, traducciones e historial de corridas
- Nuevo agente `verificador-correos`: con Mailpit como buzón de prueba (`herramientas/mailpit/`), `npm run correos` revisa que llegue lo esperado por caso (destinatario, asunto, textos, links, adjuntos), variables sin reemplazar, links rotos o a localhost, imágenes, texto plano, tamaño, compatibilidad del HTML con los clientes de correo (html-check de Mailpit) y cómo se ve en desktop y mobile. Steps de correo para los `.feature` de k0lmena (`tools/correos/correos.steps.ts`).
- Nuevo agente `analista-traductor`: `npm run traductor` recorre cada página en cada idioma (hreflang, plantilla de URL o idioma del navegador) y detecta textos sin traducir, claves a la vista, caracteres mal codificados, textos cortados o desbordados, números y fechas de otra región y el atributo lang.
- **Historial de corridas**: cada herramienta guarda sus últimas 5 corridas con la evidencia en `historial/` (y `npm test`, en `reports/<suite>/historial/`); los informes suman "Evolución de las corridas" con lo nuevo, lo resuelto, los indicadores en el tiempo y el link a cada informe anterior.
- Gráficos de línea: con pocos puntos marcan cada uno y las etiquetas de los extremos ya no se cortan.

## 2026-10-11 (3) — Pixel perfect, cross-browser, reparador y selector de casos
- Nuevo agente `pixel-perfect`: `npm run pixel-perfect` toma una referencia de cada página en cada resolución (o usa un diseño de Figma) y compara píxel a píxel y elemento por elemento: qué se corrió y cuántos píxeles, bloques desplazados con su causa (qué apareció o creció arriba), cambios de tamaño, de texto y de estilo, faltantes y nuevos. Captura estable (sin animaciones, con fuentes e imágenes cargadas y zonas dinámicas ocultas). Informe con comparador deslizable referencia/actual, mapa de diferencias y el antes y después de cada hallazgo.
- Nuevo agente `cross-browser`: `npm run cross-browser` corre la suite web de k0lmena en Chromium, Firefox y WebKit (cada navegador en su carpeta, sin pisar el último `npm test`) y separa lo que falla solo en algunos de lo que falla en todos; sin automatización, recorre las páginas y las compara contra el navegador base (errores de JavaScript y de consola exclusivos, recursos, desborde, elementos y estilos).
- Nuevo agente `reparador-automatizacion`: `npm run reparar` saca del error el locator que falló, lo prueba contra el DOM guardado, diagnostica (ya no existe, coincide con varios, no se ve, falló la espera), propone un locator único y robusto, lo aplica con respaldo y diff y verifica los escenarios. No cambia un test para tapar un bug.
- Nuevo agente `selector-casos-de-prueba`: `scripts/seleccionar_casos.py` cruza un cambio (git, PR, Jira, notas de la release) con los casos manuales, BDD y automatizados y arma la selección por riesgo (imprescindibles, recomendados, regresión mínima) con el comando `npm test` y los cambios sin cobertura.
- k0lmena: la suite web guarda el DOM de la página al fallar (`reports/web/dom/`), `REPORT_DIR` también mueve el reporte JSON y HTML de Cucumber y el `analista-fallos` rescata el DOM y la URL de cada falla.
- Arreglo: con `VIEWPORT_WIDTH`/`VIEWPORT_HEIGHT` vacíos la ventana del navegador quedaba en 0x0 (los clics fallaban por "outside of the viewport"); ahora usa 1366x768.

## 2026-10-11 (2) — Reportes con diseño bento y navegación
- Todos los reportes HTML (los 10 informes de Python, el de cada corrida de `npm run perf` y el tema de los reportes de Cucumber) pasan a un diseño tipo dashboard: barra lateral con el índice del reporte que marca la sección que se está leyendo, encabezado con buscador (Ctrl K) y grilla bento.
- Tipografía Geist y Geist Mono incrustadas (`scripts/fuentes`, licencia OFL): se ven igual en cualquier máquina y sin internet.
- Tarjetas con borde en degradado, indicadores con etiqueta de estado, brillo y barra de progreso o sparkline; columnas y barras con degradado, donas con barras de proporción en la leyenda, líneas con brillo y un medidor semicircular nuevo.
- Las tablas largas suman solas un buscador, filtros por severidad, estado o tipo (con contador) y orden al hacer clic en el encabezado.

## 2026-10-11 — Rendimiento web, análisis de fallos y cobertura
- Nuevo agente `auditor-rendimiento-web`: Lighthouse 13 en mobile y desktop (textos en español) con `npm run rendimiento`. Puntajes, Core Web Vitals de laboratorio con los umbrales de Google, oportunidades con el ahorro estimado y los recursos que las causan, elemento LCP, peso por tipo de recurso, terceros, secuencia de carga y el reporte nativo de cada página.
- Nuevo agente `analista-fallos`: `scripts/analizar_fallos.py` clasifica las fallas de `npm test` (posible bug, locator o espera, ambiente, datos, error en la automatización, paso sin definir), detecta los inestables comparando con reintentos y rescata captura, video y trace; el agente confirma la causa y redacta los bugs reales.
- Nuevo agente `analista-cobertura`: `scripts/analizar_cobertura.py` arma la matriz HU → criterios → casos → automatización → gestión → resultado → bugs y marca los huecos.
- Los tres con su informe HTML con el diseño nuevo, documentación, permisos y tests.

## 2026-10-10 (4) — Rediseño de todos los reportes
- Sistema de diseño nuevo (`scripts/_estilos_reporte.py`) para los 7 informes HTML (plan, ejecución, cierre, performance, seguridad, exploratorias y accesibilidad): más ancho (hasta 1480px), tarjetas con el título adentro, indicadores con íconos según lo que miden y el estado como símbolo (✓ ✕ ! ⊘), nunca solo color, tablas con encabezado destacado y números alineados.
- Gráficos nuevos: curvas suaves con área en degradado y etiquetas solo en el máximo y el último valor, columnas con el valor en la punta, donas con leyenda de valores y porcentajes, barras sobre un riel tenue. Paleta categórica nueva liderada por verde azulado (#14A895), validada para daltonismo y contraste con el script del skill dataviz; los colores de estado no cambian.
- Mismo diseño en el informe de cada corrida de `npm run perf` (k0lmena) y en el tema de los reportes de Cucumber (`npm test` web, API y mobile).
- Arreglo: la duración de una corrida de performance ya no muestra "3m 60s".

## 2026-10-10 (3) — Accesibilidad
- Nuevo agente `analista-accesibilidad`: audita WCAG 2.2 (AA por defecto) y revisa a mano con Playwright MCP lo que una herramienta no puede juzgar (textos alternativos, encabezados, formularios y errores, menús y modales con teclado, lector de pantalla). Nunca afirma conformidad.
- `npm run accesibilidad` (`herramientas/k0lmena/tools/accesibilidad/auditar.js`): axe-core 4.13 con los textos en español, navegación con Tab (foco no visible, trampas de foco, salto al contenido) y reflow a 320px; captura de cada página y de cada elemento que falla, y video. Cada corrida reemplaza a la anterior en `output/accesibilidad/<HU o host>/`.
- `scripts/generar_informe_accesibilidad.py`: informe HTML con cumplimiento, criterios WCAG incumplidos (nombre y nivel), cada problema con sus elementos, capturas y cómo corregirlo, teclado y orden del foco, revisión manual y recomendaciones.

## 2026-10-10 (2) — Pruebas exploratorias
- Nuevo agente `explorador-web`: recorre el sitio (`APP_URL` del `.env` o la URL pedida) buscando links e imágenes rotas, errores de JavaScript y de consola y recursos que fallan; revisa el responsive en mobile, tablet y desktop (scroll horizontal, texto chico, objetivos táctiles chicos según WCAG 2.5.8, meta viewport) con capturas; y explora a mano con Playwright MCP.
- `npm run explorar` (`herramientas/k0lmena/tools/explorador/explorar.js`): el recorrido automático, sin tokens por página. Solo GET: no envía formularios ni sigue links de cierre de sesión. Separa los links rotos de los no verificables (403, 429, timeouts).
- `scripts/generar_informe_exploratorio.py`: informe HTML en modo oscuro con indicadores, gráficos, cada hallazgo con su captura (clic para ampliar), tiempos de carga, matriz de responsive, videos, galerías, links rotos, detalle por página y la exploración manual. `npm run explorar` lo genera solo al terminar.
- Evidencia completa: captura de cada página y de cada resolución con los problemas marcados en rojo, y video del recorrido y de cada resolución. Cada corrida reemplaza a la anterior en `output/exploratorias/<HU o host>/`.

## 2026-10-10 — Inicio directo, conectores a pedido
- Claude Code arranca sin pedir aprobar conectores: `.mcp.json` trae solo los que vienen activos para todos (Playwright y Atlassian).
- Los opcionales (Azure DevOps, Figma, QMetry, QTM4J, AIO Tests, k0lmenaTMT, Appium) pasan a `scripts/mcp/catalogo.json` y cada persona activa los suyos con `npm run conector -- activar <nombre>` (alcance local de Claude Code: solo para esa persona, sin tocar archivos versionados).
- `npm run doctor` revisa también los conectores activados así. Tests que garantizan que todo lo de `.mcp.json` venga habilitado.

## 2026-10-09 (3) — Verificación funcional
- `correr_newman.py` respeta el `base_url` del environment o de la colección; `API_BASEURL` del `.env` se usa solo si no lo definen (la demo terminaba pegándole a Petstore).
- `npm run doctor` acepta Xray Server/DC con usuario y contraseña, y Azure DevOps sin PAT (login interactivo o `az login`).
- `npm run perf` avisa si un mismo nombre de script existe en dos herramientas, en vez de elegir uno en silencio.
- `npm run test:repo` funciona también con Node 20.

## 2026-10-09 (2) — Revisión completa: robustez, seguridad, tests y documentación

**Correcciones**
- Seis agentes (análisis, generadores de casos, datos y bugs) ya pueden leer Jira, Azure DevOps, Confluence y Figma: tenían la lista de herramientas restringida.
- Ningún agente se queda esperando una respuesta: si falta un dato, termina y devuelve "Necesito que confirmes"; la conversación principal pregunta y lo continúa.
- Los escenarios BDD llevan `@CP-XXX`: la trazabilidad BDD → automatización → gestión → resultados ya no se corta. `@smoke` siempre en minúscula.
- Publicación de resultados por historia: un `@CP-001` de otra historia ya no se carga en el caso equivocado.
- Los reintentos ante 429/5xx reenvían las evidencias completas (antes podían subir vacías); los cortes de red se reintentan.
- `subir-casos` registra cada caso apenas lo crea: si falla el vínculo, no se duplica y el vínculo se reintenta.
- El informe de cierre suma todas las fuentes (ejecuciones en vivo, `npm test`, bugs, performance y seguridad) con `scripts/recolectar_resultados.py`; la plantilla de bug suma Historia, Estado y Prioridad.
- El lector de `.feature` conserva los `Examples` con tags y soporta `Rule`.
- Tres agentes (generador-casos-manuales, generador-reporte-cierre y performance-mapper) no cargaban: su descripción tenía ": " sin comillas y el YAML era inválido. Un test valida ahora el encabezado de todos los agentes y skills.

**Seguridad**
- Servers MCP con versiones fijas (sin `@latest`) y Playwright con `--secrets .env`.
- Bases de datos con SSL: se verifica el certificado (`sin-verificar` es explícito); `DB_<NOMBRE>_SSL_CA` para CA propias.
- k6 se descarga verificando su SHA-256; validaciones de keys, historias y rutas en los scripts.
- Permisos del proyecto: se permiten los comandos de solo lectura y generación; lo que escribe afuera sigue pidiendo confirmación.

**Nuevo**
- `npm run doctor`: revisa el entorno y dice qué falta.
- `scripts/correr_newman.py`: corre colecciones con el token y la URL del `.env` en cualquier sistema.
- Tests del repo (pytest y node --test) y CI en GitHub Actions (Ubuntu y Windows).
- `LICENSE`, este `CHANGELOG` y `input/README.md`.

## 2026-10-09 (1) — Nuevas integraciones y reportes
- Rediseño de todos los reportes: modo oscuro moderno, paletas validadas y gráficos con tooltips.
- Todos los conectores listos (Jira, Azure DevOps, Confluence, Figma, QMetry, AIO Tests, k0lmenaTMT, Xray) y Jira habilitado por defecto.
- Seguridad web con OWASP ZAP (escaneo pasivo) y su informe.
- JMeter en performance, guía paso a paso de la prueba e informe final.
- Azure DevOps (Boards, Test Plans, Wiki) y credenciales de todos los conectores leídas del `.env`.

## 2026-10-08
- Conector de k0lmenaTMT; investigación de contexto y "Falta información" (`FI-XX`).
- Agente verificador-datos y verificaciones en base de datos.
- Sitio de documentación (GitHub Pages), PDF y diagramas.
- performance-mapper y el runner de performance de k0lmena.
- Integración con Xray, QMetry (QTM4J) y AIO Tests; GIF como evidencia.
- Integración de k0lmena y los agentes web-mapper, api-mapper y mobile-mapper.
- El proyecto pasa a llamarse k0lmenIA.

## 2026-06
- Primeras versiones de los agentes QARMY: análisis, casos, datos, bugs, API, plan de pruebas e informe final.
