"""Documentación incremental (scripts/cambios_documentacion.py) y su reflejo en el índice."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts"))

import cambios_documentacion as cd  # noqa: E402
import indice_documentacion as indice  # noqa: E402


def _estado():
    e = cd.estado_vacio()
    cd.registrar_repo(e, "github", "org/app", "main", "aaa111")
    cd.registrar_documento(e, "proyecto/reglas-de-negocio.md", ["src/pagos/", "src/**/validaciones*.ts"], "org/app", ["PROJ-12"], ["pagos"])
    cd.registrar_documento(e, "proyecto/mensajes.md", ["src/i18n/es.json"], "org/app", [], ["login"])
    cd.registrar_documento(e, "proyecto/otro-repo.md", ["src/pagos/"], "org/otra")
    cd.registrar_historia(e, "PROJ-20", hu="HU-007", archivos=["src/carrito/"], modulos=["carrito"])
    cd.registrar_historia(e, "PROJ-12", hu="HU-001")
    return e


def test_coincidencias_de_fuentes():
    assert cd.coincide("src/pagos/checkout.ts", "src/pagos/")
    assert cd.coincide("./src/pagos/x.ts", "src/pagos")
    assert cd.coincide("src/a/b/validaciones-tarjeta.ts", "src/**/validaciones*.ts")
    assert cd.coincide("src/validaciones.ts", "src/**/validaciones*.ts")
    assert cd.coincide(".github/workflows/ci.yml", ".github/")
    assert not cd.coincide("src/pagosx/a.ts", "src/pagos/")
    assert not cd.coincide("src/pagos.ts", "src/pagos/")
    assert not cd.coincide("a.ts", "")


def _casos(raiz):
    (raiz / "output/casos-de-prueba/manuales").mkdir(parents=True)
    (raiz / "output/casos-de-prueba/manuales/casos-HU-001.md").write_text("# Casos de pagos", encoding="utf-8")
    (raiz / "output/casos-de-prueba/manuales/casos-HU-001-cobertura.md").write_text("cobertura", encoding="utf-8")
    (raiz / "output/casos-de-prueba/manuales/casos-HU-007.xlsx").write_bytes(b"PK")
    feat = raiz / "herramientas/k0lmena/web/features"
    feat.mkdir(parents=True)
    (feat / "HU-009-login.feature").write_text("@HU-009\nFeature: Login\n  Scenario: mensaje de error del login", encoding="utf-8")
    (feat / "HU-010-perfil.feature").write_text("@HU-010\nFeature: Perfil", encoding="utf-8")


def test_analiza_documentos_historias_y_casos(tmp_path):
    _casos(tmp_path)
    archivos = ["src/pagos/checkout.ts", "src/i18n/es.json", "src/carrito/total.ts", "README.md"]
    r = cd.analizar(_estado(), archivos, "org/app", raiz=tmp_path)
    assert r["documentos"] == {"proyecto/reglas-de-negocio.md": ["src/pagos/checkout.ts"], "proyecto/mensajes.md": ["src/i18n/es.json"]}
    assert r["historias"] == ["PROJ-12", "PROJ-20"]
    assert r["modulos"] == ["carrito", "login", "pagos"]
    casos = {c["archivo"]: c["motivo"] for c in r["casos"]}
    assert casos == {
        "output/casos-de-prueba/manuales/casos-HU-001.md": "historia HU-001 · módulo pagos",
        "output/casos-de-prueba/manuales/casos-HU-007.xlsx": "historia HU-007",
        "herramientas/k0lmena/web/features/HU-009-login.feature": "módulo login",
    }
    assert r["sin_documento"] == ["src/carrito/total.ts", "README.md"]


def test_marcar_y_volver_a_registrar_limpia_la_marca():
    e = _estado()
    r = {"documentos": {"proyecto/mensajes.md": ["src/i18n/es.json"]}}
    cd.marcar(e, r, "aaa111", "bbb222")
    assert e["documentos"]["proyecto/mensajes.md"]["desactualizado"]["desde"] == "aaa111"
    cd.registrar_documento(e, "proyecto/mensajes.md", ["src/i18n/es.json"], "org/app")
    assert "desactualizado" not in e["documentos"]["proyecto/mensajes.md"]


def test_cambios_md(tmp_path):
    _casos(tmp_path)
    r = cd.analizar(_estado(), ["src/pagos/a.ts"], "org/app", raiz=tmp_path)
    md = cd.armar_cambios_md(r, "aaa111", "HEAD")
    assert md.startswith("---\ntitulo: Cambios desde la última documentación\ntipo: cambios\n")
    assert "| `proyecto/reglas-de-negocio.md` | `src/pagos/a.ts` |" in md
    assert "`revisor-casos`" in md and "casos-HU-001.md" in md


def test_linea_de_comandos_con_git_e_indice(tmp_path):
    repo = tmp_path / "app"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (repo / "src/pagos").mkdir(parents=True)
    (repo / "src/pagos/a.ts").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "uno")
    inicial = git("rev-parse", "HEAD")
    (repo / "src/pagos/a.ts").write_text("2", encoding="utf-8")
    git("commit", "-qam", "dos")

    doc = tmp_path / "doc"
    (doc / "proyecto").mkdir(parents=True)
    (doc / "proyecto/reglas.md").write_text(f"---\ntitulo: Reglas\ntipo: proyecto\nactualizado: {dt.date.today()}\n---\n", encoding="utf-8")
    base = ["--carpeta", str(doc)]
    assert cd.main(base + ["repo", "--proveedor", "github", "--nombre", "org/app", "--commit", inicial]) == 0
    assert cd.main(base + ["registrar", "--documento", "proyecto/reglas.md", "--fuentes", "src/pagos/", "--repo", "org/app"]) == 0
    assert cd.main(base + ["cambios", "--git", str(repo), "--marcar"]) == 0
    estado = json.loads((doc / ".estado.json").read_text(encoding="utf-8"))
    assert estado["documentos"]["proyecto/reglas.md"]["desactualizado"]["archivos"] == ["src/pagos/a.ts"]
    assert "+====" in (doc / "cambios.md").read_text(encoding="utf-8")  # tablas alineadas

    assert indice.main(["--carpeta", str(doc)]) == 0
    texto = (doc / "INDICE.md").read_text(encoding="utf-8")
    assert f"Desactualizado (desde {inicial[:10]})" in texto
    assert texto.index("Cambios desde la última documentación") < texto.index("## Proyecto")
    assert ".estado.json" not in texto
