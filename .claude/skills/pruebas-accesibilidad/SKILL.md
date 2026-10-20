---
name: pruebas-accesibilidad
description: Cómo auditar accesibilidad (a11y) en las tres plataformas — web (WCAG 2.2, principios POUR, niveles A/AA/AAA, axe-core, navegación por teclado y trampas de foco, foco visible, reflow a 320px, contraste, ARIA y roles, formularios y mensajes de error, encabezados y landmarks, lectores de pantalla NVDA/VoiceOver), mobile (Android TalkBack e iOS VoiceOver, etiquetas accesibles —contentDescription / accessibilityLabel—, tamaño de los objetivos táctiles 48dp/44pt, escalado de fuente dinámico, orden de foco y agrupación, alternativas a gestos, subtítulos, Accessibility Scanner y Accessibility Inspector, accessibility ids con Appium) y desktop (UI Automation — Name/ControlType de cada control, navegación completa por teclado y orden de tabulación, lectores NVDA/JAWS/Narrator, modo de alto contraste, escalado de texto y DPI, controles sin nombre accesible). Mapeo de WCAG a mobile/desktop, cómo automatizar cada plataforma (axe-core web, Appium mobile, el árbol de controles en desktop) y qué necesita criterio humano, cómo priorizar por impacto y preguntas para el equipo. Lo usa el analista-accesibilidad, y lo referencian el probador-mobile y el probador-desktop.
---

# Accesibilidad (a11y): web, mobile y desktop

La accesibilidad es que **cualquier persona** —con lector de pantalla, solo teclado, baja visión, daltonismo o motricidad reducida— pueda usar el producto. La base es **WCAG 2.2** y sus principios **POUR** (Perceptible, Operable, Comprensible, Robusto); mobile y desktop adaptan esos principios a sus APIs de accesibilidad. Lo automático lo corre una herramienta; lo que necesita criterio humano se revisa a mano.

## 1. Lo común a las tres plataformas (POUR)

- **Perceptible**: todo lo visual tiene alternativa (texto alternativo en imágenes, subtítulos en video), suficiente **contraste**, y la información no depende solo del color.
- **Operable**: todo se puede usar **solo con teclado** (o switch/lector), el **foco es visible** y su orden es lógico, sin **trampas de foco**, objetivos táctiles/clic suficientemente grandes.
- **Comprensible**: etiquetas y mensajes de error claros, comportamiento predecible, idioma declarado.
- **Robusto**: cada control expone su **nombre, rol y estado** a la API de accesibilidad (ARIA en web, labels en mobile, UIA en desktop); lo que no tiene nombre accesible **no se puede usar con un lector ni automatizar**.

## 2. Web (WCAG 2.2)

- **Automático** (axe-core, `npm run accesibilidad`): contraste, roles/ARIA mal usados, imágenes sin alt, formularios sin label, idioma, encabezados; **teclado** (foco no visible, trampas) y **reflow** a 320px.
- **Manual** (con Playwright MCP y `ejecucion-e2e`): orden de encabezados y **landmarks**, menús/modales con teclado y foco atrapado a propósito, mensajes de error asociados al campo, contenido dinámico anunciado (`aria-live`), y una pasada con **lector de pantalla** (NVDA/VoiceOver).
- Nivel objetivo por defecto: **AA**.

## 3. Mobile (Android / iOS)

- **Etiquetas accesibles**: Android `contentDescription` / `labelFor`, iOS `accessibilityLabel`. Un botón de solo ícono sin etiqueta es invisible para TalkBack/VoiceOver (y para Appium).
- **Objetivos táctiles**: mínimo ~**48dp** (Android) / **44pt** (iOS).
- **Escalado de fuente dinámico** (Dynamic Type / tamaño de fuente del sistema grande): el texto crece sin cortarse ni tapar controles.
- **Orden y agrupación** del foco del lector; **alternativas a gestos** complejos (lo que se hace deslizando también por otro medio); **subtítulos** en video.
- **Contraste** y no depender del color.
- Herramientas: **TalkBack** (Android) y **VoiceOver** (iOS) para la revisión manual; **Accessibility Scanner** (Android) y **Accessibility Inspector** (Xcode) para lo automático; con **Appium** se leen los accessibility ids/labels (lo que falta para a11y también falta para automatizar). Se complementa con `pruebas-mobile`.

## 4. Desktop (Windows / UI Automation)

- Cada control expone **Name** y **ControlType** por **UI Automation (UIA)**; un control sin nombre accesible no lo lee NVDA/JAWS/Narrator ni se puede automatizar. La herramienta `herramientas/desktop/controles.py` (`npm run desktop`) ya **marca los controles sin nombre accesible**.
- **Navegación completa por teclado** y orden de tabulación lógico, foco visible, mnemónicos (Alt+letra), Esc/Enter en diálogos.
- **Modo de alto contraste** de Windows y **escalado de texto/DPI**: la app sigue usable, sin texto cortado.
- Revisión con un lector (NVDA es gratis). Se complementa con `pruebas-desktop`.

## 5. Mapeo de WCAG a mobile/desktop

Los criterios de WCAG se trasladan: "texto alternativo" → etiqueta accesible; "teclado" → navegación por teclado (desktop) o lector/switch (mobile); "contraste" y "reflow/zoom" → escalado de fuente y alto contraste; "nombre, rol, valor" → UIA/labels. Usá WCAG como checklist también fuera de la web.

## 6. Cómo priorizar

Por **impacto en el uso**: primero lo que **bloquea** (no se puede completar una tarea con lector o solo teclado: un botón sin nombre, una trampa de foco, un control inalcanzable), después lo que **dificulta** (contraste bajo, foco poco visible, objetivo chico) y por último lo menor. Decí a **quién** afecta cada barrera.

## 7. Qué es automático y qué necesita criterio humano

- **Automático**: contraste, nombres/labels faltantes, roles mal, objetivos chicos, idioma. Lo corre la herramienta por plataforma, sin gastar tokens por pantalla.
- **Criterio humano**: si la etiqueta **tiene sentido**, si el orden de lectura es lógico, si un cambio dinámico se anuncia, si el flujo completo se puede hacer con lector. Eso se revisa a mano.

## 8. Preguntas típicas para el equipo

Cuando no está escrito, son `FI-XX`:

- ¿Qué plataformas (web, Android, iOS, desktop) y qué nivel WCAG objetivo (A/AA/AAA)?
- ¿Hay que soportar lector de pantalla, solo teclado, alto contraste y fuente grande?
- ¿Qué flujos son críticos para auditar de punta a punta con lector?
- ¿Hay una guía de accesibilidad propia o un estándar legal a cumplir?
