"""Static code quality: the code_quality tool (heuristics, duplication, auth header) and its report."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import code_quality  # noqa: E402
import generate_code_quality_report as gcq  # noqa: E402


def rules(text, language):
    return {r for r, *_ in code_quality.find_patterns(text, language)}


def test_python_patterns():
    text = "def f(x=[]):\n    try:\n        pass\n    except:\n        pass\nfrom os import *\n"
    assert {"mutable-default", "bare-except", "wildcard-import"} <= rules(text, "Python")


def test_js_patterns_and_loops():
    text = ("const a = fs.readFileSync('x');\nconsole.log(a);\ntry { go() } catch (e) {}\n"
            "for (const id of ids) {\n  const row = await db.query('select 1');\n}\nitems.forEach(async (i) => save(i));\n")
    found = rules(text, "JavaScript")
    assert {"sync-io", "console-log", "empty-catch", "await-in-loop", "query-in-loop", "foreach-async"} <= found


def test_no_false_positive_for_dict_get_in_loop():
    text = "for k in keys:\n    v = data.get(k)\n    s = name.find('x')\n"
    assert "query-in-loop" not in rules(text, "Python")


def test_patterns_respect_language():
    assert "console-log" not in rules("console.log(1)\n", "Python")


def test_find_duplicates():
    block = "\n".join(f"value_{i} = compute({i}) + other({i})" for i in range(8))
    files = {"a.py": block + "\nunique_a = 1\n", "b.py": "header = 2\n" + block, "c.py": "nothing_here = 3\n"}
    blocks, dup_lines = code_quality.find_duplicates(files)
    assert len(blocks) == 1 and blocks[0]["lines"] == 8
    assert {loc[0] for loc in blocks[0]["locations"]} == {"a.py", "b.py"}
    assert dup_lines == 16


def test_auth_header_never_contains_raw_token():
    h = code_quality.auth_header("github", "secret-token-123")
    assert h.startswith("Authorization: Basic ") and "secret-token-123" not in h
    assert code_quality.auth_header("gitlab", "") is None


def test_survey_on_a_small_project(tmp_path):
    (tmp_path / "app.py").write_text("def f(x={}):\n    return x\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "lib.js").write_text("console.log(1)\n", encoding="utf-8")
    inv = code_quality.survey(tmp_path, use_linters=False)
    assert inv["summary"]["files"] == 1 and "Python" in inv["languages"]
    assert any(f["rule"] == "mutable-default" for f in inv["findings"])


def test_report(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    data = {"title": "Code quality — demo", "project": {"repo": "acme/demo", "branch": "main", "commit": "abc123"},
            "metrics": {"files": 3, "loc": 120, "duplication_pct": 12.5, "avg_complexity": 4.2, "max_complexity": 31, "complex_functions": 2},
            "languages": [{"language": "Python", "files": 3, "loc": 120}],
            "findings": [{"id": "CQ-01", "severity": "High", "category": "Performance", "file": "a.py", "line": 3,
                          "text": "Query per item", "impact": "N+1", "recommendation": "Batch it"}],
            "discarded": [{"rule": "sync-io", "file": "build.js", "reason": "build script"}],
            "duplicates": [{"lines": 8, "locations": ["a.py:1", "b.py:2"]}],
            "missing_info": [{"id": "MI-01", "what_is_missing": "Complexity limit", "question": "Which limit?"}]}
    (tmp_path / "analysis.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gcq.generate(tmp_path / "analysis.json", tmp_path / "report.html")
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    for text in ("CQ-01", "acme/demo", "12.5%", "build script", "MI-01", "a.py:1"):
        assert text in html
