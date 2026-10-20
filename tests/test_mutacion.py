"""Mutation testing: parser del reporte de Stryker (helpers puros)."""
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "herramientas" / "mutacion"))

import mutacion  # noqa: E402

REPORTE = {
    "schemaVersion": "1.0",
    "files": {
        "src/precio.js": {"mutants": [
            {"id": "1", "mutatorName": "ArithmeticOperator", "status": "Killed", "location": {"start": {"line": 10}}},
            {"id": "2", "mutatorName": "EqualityOperator", "status": "Survived", "location": {"start": {"line": 12}}},
            {"id": "3", "mutatorName": "BooleanLiteral", "status": "Killed", "location": {"start": {"line": 14}}},
        ]},
        "src/util.js": {"mutants": [
            {"id": "4", "mutatorName": "ConditionalExpression", "status": "NoCoverage", "location": {"start": {"line": 3}}},
            {"id": "5", "mutatorName": "StringLiteral", "status": "Killed", "location": {"start": {"line": 5}}},
        ]},
    },
}


def test_parse_stryker_score_y_sobrevivientes():
    r = mutacion.parse_stryker(REPORTE)
    assert r["total"] == 5
    assert r["por_estado"] == {"Killed": 3, "Survived": 1, "NoCoverage": 1}
    # score global = detectados(3 killed) / validos(5) * 100 = 60.0
    assert r["score"] == 60.0
    # sobrevivientes: el Survived y el NoCoverage
    assert len(r["survived"]) == 2
    archivos = {s["archivo"] for s in r["survived"]}
    assert archivos == {"src/precio.js", "src/util.js"}
    # score por archivo: precio.js 2/3 killed = 66.7 ; util.js 1/2 = 50.0
    assert r["por_archivo"]["src/precio.js"]["score"] == 66.7
    assert r["por_archivo"]["src/util.js"]["score"] == 50.0


def test_bajo_umbral():
    r = mutacion.parse_stryker(REPORTE)
    assert mutacion.bajo_umbral(r["por_archivo"], 70) == ["src/util.js", "src/precio.js"]
    assert mutacion.bajo_umbral(r["por_archivo"], 55) == ["src/util.js"]


def test_reporte_vacio():
    r = mutacion.parse_stryker({"files": {}})
    assert r["score"] is None and r["total"] == 0 and r["survived"] == []
