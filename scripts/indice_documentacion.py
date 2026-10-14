#!/usr/bin/env python3
"""
Índice de la documentación del proyecto (agente documentador-proyecto).

Uso (desde la raíz del repo):
    python scripts/indice_documentacion.py [--carpeta input/documentacion] [--dias 30]

Recorre input/documentacion/ y arma input/documentacion/INDICE.md: qué documento hay, de qué trata,
de qué fuentes sale, cuándo se actualizó y si conviene revisarlo (más viejo que --dias). Es lo
primero que leen los demás agentes (skill investigacion-contexto) para saber qué contexto existe sin
abrir todos los archivos.

Cada .md que escribe el documentador lleva un encabezado (frontmatter) así:

    ---
    titulo: Reglas de negocio de pagos
    tipo: proyecto | repositorio | web | historia | api | links
    historia: HU-001            (solo en los dossiers de una historia)
    fuentes: github mi-empresa/mi-app (src/pagos), PROJ-12
    actualizado: 2026-10-14
    ---

Los archivos sin encabezado (por ejemplo, un PDF o un .md que agregó una persona) también se listan,
como "Agregado a mano", con la fecha del archivo.
"""
import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
INDICE = "INDICE.md"
IGNORAR = {INDICE, ".gitkeep"}
ORDEN_TIPOS = ["proyecto", "repositorio", "api", "web", "historia", "links"]
NOMBRE_TIPO = {
    "proyecto": "Proyecto",
    "repositorio": "Repositorio",
    "api": "Contratos de API",
    "web": "Aplicación web",
    "historia": "Historias",
    "links": "Links externos",
    "manual": "Agregado a mano",
}
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(\n|\Z)", re.S)


def leer_encabezado(texto):
    """{clave: valor} del frontmatter (formato simple clave: valor), o {} si no tiene."""
    m = _FRONT.match(texto.lstrip("﻿"))
    if not m:
        return {}
    datos = {}
    for linea in m.group(1).splitlines():
        if ":" in linea and not linea.lstrip().startswith("#"):
            clave, valor = linea.split(":", 1)
            datos[clave.strip().lower()] = valor.strip()
    return datos


def _fecha(texto):
    try:
        return dt.date.fromisoformat(str(texto)[:10])
    except ValueError:
        return None


def _titulo_md(texto):
    for linea in _FRONT.sub("", texto.lstrip("﻿"), count=1).splitlines():
        if linea.startswith("# "):
            return linea[2:].strip()
    return ""


def documentos(carpeta):
    """Lista de documentos de la carpeta con sus datos, ordenados por tipo y ruta."""
    docs = []
    for ruta in sorted(p for p in carpeta.rglob("*") if p.is_file()):
        # Los .json con su .md al lado (el mapa funcional) son los datos del mismo documento.
        if ruta.name in IGNORAR or ruta.name.startswith("_") or (ruta.suffix == ".json" and ruta.with_suffix(".md").exists()):
            continue
        rel = ruta.relative_to(carpeta).as_posix()
        meta = {}
        if ruta.suffix.lower() == ".md":
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            meta = leer_encabezado(texto)
            meta.setdefault("titulo", _titulo_md(texto))
        tipo = (meta.get("tipo") or "manual").lower()
        if tipo not in NOMBRE_TIPO:
            tipo = "manual"
        fecha = _fecha(meta.get("actualizado", "")) or dt.date.fromtimestamp(ruta.stat().st_mtime)
        docs.append({
            "ruta": rel,
            "titulo": meta.get("titulo") or ruta.stem,
            "tipo": tipo,
            "historia": meta.get("historia", ""),
            "fuentes": meta.get("fuentes", ""),
            "actualizado": fecha,
        })
    orden = {t: i for i, t in enumerate(ORDEN_TIPOS + ["manual"])}
    return sorted(docs, key=lambda d: (orden[d["tipo"]], d["historia"], d["ruta"]))


def armar_indice(docs, hoy, dias):
    lineas = [
        "---",
        "titulo: Índice de la documentación del proyecto",
        "tipo: indice",
        f"actualizado: {hoy.isoformat()}",
        "---",
        "",
        "# Documentación del proyecto",
        "",
        "Contexto del proyecto para los agentes (lo arma el `documentador-proyecto`; se regenera con "
        "`python scripts/indice_documentacion.py`). Leé primero este índice y abrí solo lo que necesites.",
        "Lo que viene del código o de la aplicación describe cómo funciona **hoy**: es contexto, no "
        "reemplaza a la historia ni a las decisiones del PO.",
        "",
    ]
    if not docs:
        lineas += ["Todavía no hay documentación. Pedile al `documentador-proyecto` que la arme.", ""]
        return "\n".join(lineas)
    viejos = [d for d in docs if (hoy - d["actualizado"]).days > dias]
    lineas += [f"{len(docs)} documento(s) · {len(viejos)} para revisar (más de {dias} días sin actualizar).", ""]
    for tipo in ORDEN_TIPOS + ["manual"]:
        grupo = [d for d in docs if d["tipo"] == tipo]
        if not grupo:
            continue
        lineas += [f"## {NOMBRE_TIPO[tipo]}", ""]
        con_historia = any(d["historia"] for d in grupo)
        cab = ["Documento", "Título"] + (["Historia"] if con_historia else []) + ["Fuentes", "Actualizado", "Estado"]
        lineas += ["| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
        for d in grupo:
            estado = "Revisar" if d in viejos else "Vigente"
            fila = [f"`{d['ruta']}`", d["titulo"]] + ([d["historia"]] if con_historia else []) + [
                d["fuentes"] or "-", d["actualizado"].isoformat(), estado]
            lineas.append("| " + " | ".join(str(c).replace("|", "/") for c in fila) + " |")
        lineas.append("")
    return "\n".join(lineas)


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        flujo.reconfigure(encoding="utf-8")
    ap =argparse.ArgumentParser(description="Arma input/documentacion/INDICE.md")
    ap.add_argument("--carpeta", default=str(RAIZ / "input" / "documentacion"))
    ap.add_argument("--dias", type=int, default=30, help="días después de los que un documento se marca para revisar")
    a = ap.parse_args(argv)
    carpeta = Path(a.carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    docs = documentos(carpeta)
    destino = carpeta / INDICE
    destino.write_text(armar_indice(docs, dt.date.today(), a.dias), encoding="utf-8")
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "formatear_tablas.py"), str(destino)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"Aviso: no pude alinear las tablas ({r.stderr.strip().splitlines()[-1:] or ''}).")
    print(f"{len(docs)} documento(s) en el índice: {destino.relative_to(RAIZ) if destino.is_relative_to(RAIZ) else destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
