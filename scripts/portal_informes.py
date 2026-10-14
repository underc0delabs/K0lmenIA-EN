#!/usr/bin/env python3
"""
Portal de informes: output/index.html con el último informe de cada herramienta.

Uso (desde la raíz del repo):
    python scripts/portal_informes.py [--abrir]

Recorre output/ (cada carpeta es una herramienta: ejecuciones, exploratorias, accesibilidad, …; las que
se agreguen después aparecen solas) y los reportes de k0lmena (herramientas/k0lmena/reports/), y arma
una página con una tarjeta por herramienta: el último informe HTML de cada historia, sitio o suite, su
fecha, el veredicto o resultado si el JSON lo trae, y el link a la corrida anterior guardada en historial/.

Los links son relativos: output/index.html se abre con doble clic, sin servidor.

Se regenera solo: cada informe HTML que arman los scripts (con _estilos_reporte.page) lo actualiza al
terminar. Para desactivarlo, K0LMENIA_PORTAL=0 en el entorno.
"""
import argparse
import atexit
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# Nombres legibles de las carpetas conocidas (las demás se muestran con su nombre capitalizado).
NOMBRES = {
    "ejecuciones": "Ejecuciones (E2E y API)", "exploratorias": "Pruebas exploratorias", "accesibilidad": "Accesibilidad",
    "rendimiento": "Rendimiento web", "fallos": "Análisis de fallos", "cobertura": "Cobertura y trazabilidad",
    "pixel-perfect": "Regresión visual", "cross-browser": "Cross-browser", "reparaciones": "Reparación de la automatización",
    "seleccion-casos": "Selección de casos", "correos": "Correos", "traductor": "Traducciones", "revision-casos": "Revisión de casos",
    "charters": "Charters exploratorios", "ux": "Usabilidad", "formularios": "Formularios", "logs": "Logs",
    "seguridad": "Seguridad web", "performance": "Performance", "informes-cierre": "Informes de cierre",
    "planes-de-prueba": "Planes de prueba", "permisos": "Permisos por rol", "resiliencia": "Resiliencia",
    "triage": "Triage de bugs", "tablero": "Tablero de calidad", "monitoreo": "Monitoreo sintético",
    "evals": "Evals de los agentes", "k0lmena": "npm test (k0lmena)",
}
# Orden de las tarjetas: primero lo que más se mira.
ORDEN = ["tablero", "informes-cierre", "ejecuciones", "k0lmena", "fallos", "cobertura", "monitoreo", "planes-de-prueba",
         "seleccion-casos", "exploratorias", "accesibilidad", "rendimiento", "performance", "seguridad", "permisos",
         "resiliencia", "pixel-perfect", "cross-browser", "formularios", "ux", "correos", "traductor", "logs",
         "reparaciones", "revision-casos", "charters", "triage", "evals"]
IGNORAR = {"historial", "evidencia", "capturas", "videos", "recortes", "diferencias", "lighthouse", "referencia",
           "actual", "respaldo", "suite", "eml", "sesiones", "node_modules"}
_SELLO = re.compile(r"[-_]?\d{4}-?\d{2}-?\d{2}([-_T]?\d{2}-?\d{2}(-?\d{2})?)?$")


def _fecha(p):
    return datetime.fromtimestamp(p.stat().st_mtime)


def _htmls(carpeta):
    """Los .html de la carpeta, sin entrar a historial/ ni a las carpetas de evidencia."""
    for raiz, dirs, archivos in os.walk(carpeta):
        dirs[:] = [d for d in dirs if d not in IGNORAR and not d.startswith((".", "_"))]
        for a in archivos:
            if a.lower().endswith(".html"):
                yield Path(raiz) / a


def _principal(archivos):
    """De varios .html de una misma unidad, el informe principal más reciente."""
    def peso(p):
        n = p.name.lower()
        return (n.startswith(("informe-", "reporte-", "cierre-", "plan-", "cucumber")), p.stat().st_mtime)
    return max(archivos, key=peso)


def _leer_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def estado_de(html):
    """Veredicto o resultado de un informe, desde los JSON que tiene al lado (o "")."""
    carpeta = html.parent
    candidatos = [carpeta / "analisis.json"]
    stem = html.stem
    for pref in ("reporte-", "cierre-", "plan-"):
        if stem.startswith(pref):
            candidatos.append(carpeta / f"_resultados-{stem[len(pref):]}.json")
            candidatos.append(carpeta / f"{stem}.json")
    candidatos += sorted(p for p in carpeta.glob("*.json") if p not in candidatos)
    for c in candidatos:
        d = _leer_json(c) if c.exists() else None
        if not isinstance(d, dict):
            continue
        if d.get("veredicto"):
            return str(d["veredicto"])
        casos = d.get("casos")
        if isinstance(casos, list) and casos and isinstance(casos[0], dict) and "estado" in casos[0]:
            ok = sum(1 for x in casos if str(x.get("estado", "")).lower() == "aprobado")
            return f"{ok}/{len(casos)} aprobados"
    if html.name.startswith("cucumber") or (carpeta / "cucumber-report.json").exists():
        d = _leer_json(carpeta / "cucumber-report.json")
        if isinstance(d, list):
            total = ok = 0
            for f in d:
                for esc in f.get("elements") or []:
                    if esc.get("type") == "background":
                        continue
                    total += 1
                    estados = [(p.get("result") or {}).get("status") for p in esc.get("steps") or []]
                    ok += bool(estados) and all(s in ("passed", "skipped") for s in estados) and "passed" in estados
            if total:
                return f"{ok}/{total} escenarios aprobados"
    return ""


def _anterior(carpeta_unidad):
    """(cantidad de corridas guardadas, el informe de la más reciente) de historial/."""
    h = carpeta_unidad / "historial"
    if not h.is_dir():
        return 0, None
    corridas = sorted((d for d in h.iterdir() if d.is_dir()), key=lambda d: d.name)
    if not corridas:
        return 0, None
    ultima = corridas[-1]
    informes = sorted(ultima.rglob("*.html"))
    return len(corridas), (_principal(informes) if informes else None)


def unidades(carpeta):
    """Informes de una herramienta: [{"unidad", "html", "fecha", "estado", "historial", "anterior", "otros"}]."""
    grupos = {}
    for html in _htmls(carpeta):
        rel = html.relative_to(carpeta)
        if len(rel.parts) > 1:
            clave, base = rel.parts[0], carpeta / rel.parts[0]
        else:
            clave = _SELLO.sub("", html.stem) or html.stem
            m = re.search(r"(HU-\d+|API|CP-API)", html.stem, re.I)
            clave = m.group(1).upper() if m and html.stem.startswith(("reporte-", "cierre-", "plan-")) else clave
            base = carpeta
        grupos.setdefault(clave, {"base": base, "htmls": []})["htmls"].append(html)
    salida = []
    for clave, g in grupos.items():
        html = _principal(g["htmls"])
        n, anterior = _anterior(g["base"]) if g["base"] != carpeta else (0, None)
        otros = sorted({h for h in g["htmls"] if h != html and h.parent == html.parent}, key=lambda p: p.name)
        salida.append({"unidad": clave, "html": html, "fecha": _fecha(html), "estado": estado_de(html),
                       "historial": n, "anterior": anterior, "otros": otros})
    return sorted(salida, key=lambda u: u["fecha"], reverse=True)


def descubrir(output, reportes_k0=None):
    """{herramienta: [unidades]} de todas las carpetas de output/ (y npm test), con o sin informes."""
    herramientas = {}
    if output.is_dir():
        for d in sorted(p for p in output.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            herramientas[d.name] = unidades(d)
    if reportes_k0 and Path(reportes_k0).is_dir():
        k0 = []
        for suite in sorted(p for p in Path(reportes_k0).iterdir() if p.is_dir()):
            for u in unidades(suite):
                u["unidad"] = suite.name if u["unidad"] in (Path(u["html"]).stem, "cucumber-report", "index") else f'{suite.name} · {u["unidad"]}'
                if u["html"].parent == suite:
                    u["historial"], u["anterior"] = _anterior(suite)
                k0.append(u)
        herramientas["k0lmena"] = sorted(k0, key=lambda u: u["fecha"], reverse=True)
    orden = {n: i for i, n in enumerate(ORDEN)}
    return dict(sorted(herramientas.items(), key=lambda kv: (orden.get(kv[0], len(ORDEN)), kv[0])))


def _tono(estado):
    t = (estado or "").lower()
    m = re.match(r"(\d+)/(\d+)", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return "ok" if a == b else "bad" if a < b * 0.8 else "warn"
    if re.search(r"no apto|no-go|no go|crític|critic|bloque|falla|rechaz|alto riesgo|riesgo alto", t):
        return "bad"
    if re.search(r"observacion|revisar|riesgo|parcial|condicion|atenci|medio", t):
        return "warn"
    if re.search(r"apto|\bgo\b|en orden|aprobad|ok|sin hallazgos|cumple", t):
        return "ok"
    return ""


def armar_html(herramientas, destino):
    from _estilos_reporte import page, meta, section, kpi_tiles, table, e, _pastilla, OK, AVISO, CRITICO, NEUTRO

    dir_html = Path(destino).resolve().parent

    def link(p, texto):
        try:
            rel = os.path.relpath(Path(p).resolve(), dir_html).replace("\\", "/")
        except ValueError:  # otra unidad en Windows: no hay ruta relativa
            rel = Path(p).resolve().as_uri()
        return f'<a href="{e(rel)}">{e(texto)}</a>'

    con = {k: v for k, v in herramientas.items() if v}
    vacias = [k for k, v in herramientas.items() if not v]
    todas = [u for us in con.values() for u in us]
    ultimo = max((u["fecha"] for u in todas), default=None)
    malos = sum(1 for u in todas if _tono(u["estado"]) == "bad")
    body = [kpi_tiles([
        ("Herramientas con informes", len(con), "", f"{len(herramientas)} carpeta(s) en total", "grid"),
        ("Informes", len(todas), "", "el último de cada historia, sitio o suite", "lista"),
        ("Para revisar", malos, "bad" if malos else "ok", "con veredicto o resultado en rojo", "warn"),
        ("Último informe", ultimo.strftime("%d/%m %H:%M") if ultimo else "—", "", "", "reloj"),
    ])]
    if not todas:
        body.append(section("Sin informes todavía", '<div class="cardbody"><p class="muted">Cuando los agentes generen '
                            'informes, van a aparecer acá. Este portal se actualiza solo cada vez que se arma uno.</p></div>'))
    color = {"ok": OK, "warn": AVISO, "bad": CRITICO}
    icono = {"ok": "✓", "warn": "!", "bad": "✕"}
    for nombre, us in con.items():
        filas = []
        for u in us:
            t = _tono(u["estado"])
            estado = _pastilla(u["estado"], color.get(t, NEUTRO), icono.get(t, "●")) if u["estado"] else '<span class="muted">—</span>'
            otros = " · ".join(link(o, o.stem) for o in u["otros"][:4])
            informe = link(u["html"], u["html"].name) + (f'<div class="muted" style="font-size:12px">{otros}</div>' if otros else "")
            hist = (link(u["anterior"], f'anterior ({u["historial"]} guardada{"s" if u["historial"] != 1 else ""})')
                    if u["anterior"] else '<span class="muted">—</span>')
            filas.append([f'<b>{e(u["unidad"])}</b>', informe, e(u["fecha"].strftime("%d/%m/%Y %H:%M")), estado, hist])
        body.append(section(NOMBRES.get(nombre, nombre.replace("-", " ").capitalize()),
                            table(["Historia / sitio / suite", "Informe", "Fecha", "Estado", "Corrida anterior"], filas),
                            f"{len(us)} informe(s)"))
    if vacias:
        chips = " ".join(f'<span class="chip">{e(NOMBRES.get(v, v))}</span>' for v in vacias)
        body.append(section("Todavía sin informes", f'<div class="cardbody"><div class="meta">{chips}</div></div>'))
    return page("Portal de informes", "Portal", meta([("Actualizado", datetime.now().strftime("%d/%m/%Y %H:%M")),
                                                      ("Carpeta", "output/")]), "".join(body))


def generar(output=None, reportes_k0=None, destino=None):
    output = Path(output or RAIZ / "output")
    reportes_k0 = reportes_k0 if reportes_k0 is not None else RAIZ / "herramientas" / "k0lmena" / "reports"
    destino = Path(destino or output / "index.html")
    destino.parent.mkdir(parents=True, exist_ok=True)
    herramientas = descubrir(output, reportes_k0)
    destino.write_text(armar_html(herramientas, destino), encoding="utf-8")
    return destino, herramientas


# ------------------------------------------------------------------ actualización automática
_PROGRAMADO = [False]


def _actualizar_al_salir():
    try:
        generar()
    except Exception as ex:  # el portal nunca rompe un informe
        print(f"[!] No pude actualizar el portal de informes ({ex}).", file=sys.stderr)


def programar():
    """Regenera output/index.html cuando termina el proceso (después de que el informe se escribió).
    No hace nada en los tests, con K0LMENIA_PORTAL=0 o si no existe output/."""
    if _PROGRAMADO[0] or os.environ.get("K0LMENIA_PORTAL", "1") == "0" or "pytest" in sys.modules:
        return
    if not (RAIZ / "output").is_dir():
        return
    _PROGRAMADO[0] = True
    atexit.register(_actualizar_al_salir)


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Portal con el último informe de cada herramienta (output/index.html)")
    ap.add_argument("--abrir", action="store_true", help="abre el portal en el navegador")
    ap.add_argument("--output", help=argparse.SUPPRESS)
    ap.add_argument("--reportes", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    _PROGRAMADO[0] = True  # este proceso ya genera el portal: que page() no lo programe de nuevo
    destino, herramientas = generar(a.output, a.reportes)
    n = sum(len(v) for v in herramientas.values())
    print(f"Portal: {destino} ({n} informe(s) de {sum(1 for v in herramientas.values() if v)} herramienta(s))")
    if a.abrir:
        import webbrowser
        webbrowser.open(destino.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
