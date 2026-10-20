"""Incremental documentation (scripts/documentation_changes.py) and how it shows in the index."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import documentation_changes as dc  # noqa: E402
import documentation_index as index  # noqa: E402


def _status():
    s = dc.empty_state()
    dc.register_repo(s, "github", "org/app", "main", "aaa111")
    dc.register_document(s, "project/business-rules.md", ["src/payments/", "src/**/validations*.ts"], "org/app", ["PROJ-12"], ["payments"])
    dc.register_document(s, "project/messages.md", ["src/i18n/en.json"], "org/app", [], ["login"])
    dc.register_document(s, "project/other-repo.md", ["src/payments/"], "org/other")
    dc.register_story(s, "PROJ-20", us="US-007", files=["src/cart/"], modules=["cart"])
    dc.register_story(s, "PROJ-12", us="US-001")
    return s


def test_source_matches():
    assert dc.matches("src/payments/checkout.ts", "src/payments/")
    assert dc.matches("./src/payments/x.ts", "src/payments")
    assert dc.matches("src/a/b/validations-card.ts", "src/**/validations*.ts")
    assert dc.matches("src/validations.ts", "src/**/validations*.ts")
    assert dc.matches(".github/workflows/ci.yml", ".github/")
    assert not dc.matches("src/paymentsx/a.ts", "src/payments/")
    assert not dc.matches("src/payments.ts", "src/payments/")
    assert not dc.matches("a.ts", "")


def _cases(root):
    (root / "output/test-cases/manual").mkdir(parents=True)
    (root / "output/test-cases/manual/cases-US-001.md").write_text("# Cases for payments", encoding="utf-8")
    (root / "output/test-cases/manual/cases-US-001-coverage.md").write_text("coverage", encoding="utf-8")
    (root / "output/test-cases/manual/cases-US-007.xlsx").write_bytes(b"PK")
    feat = root / "tools/k0lmena/web/features"
    feat.mkdir(parents=True)
    (feat / "US-009-login.feature").write_text("@US-009\nFeature: Login\n  Scenario: login error message", encoding="utf-8")
    (feat / "US-010-profile.feature").write_text("@US-010\nFeature: Profile", encoding="utf-8")


def test_analyzes_documents_stories_and_cases(tmp_path):
    _cases(tmp_path)
    files = ["src/payments/checkout.ts", "src/i18n/en.json", "src/cart/total.ts", "README.md"]
    r = dc.analyze(_status(), files, "org/app", root=tmp_path)
    assert r["documents"] == {"project/business-rules.md": ["src/payments/checkout.ts"], "project/messages.md": ["src/i18n/en.json"]}
    assert r["stories"] == ["PROJ-12", "PROJ-20"]
    assert r["modules"] == ["cart", "login", "payments"]
    cases = {c["file"]: c["reason"] for c in r["cases"]}
    assert cases == {
        "output/test-cases/manual/cases-US-001.md": "story US-001 · module payments",
        "output/test-cases/manual/cases-US-007.xlsx": "story US-007",
        "tools/k0lmena/web/features/US-009-login.feature": "module login",
    }
    assert r["no_document"] == ["src/cart/total.ts", "README.md"]


def test_mark_and_re_register_clears_mark():
    s = _status()
    r = {"documents": {"project/messages.md": ["src/i18n/en.json"]}}
    dc.mark(s, r, "aaa111", "bbb222")
    assert s["documents"]["project/messages.md"]["outdated"]["since"] == "aaa111"
    dc.register_document(s, "project/messages.md", ["src/i18n/en.json"], "org/app")
    assert "outdated" not in s["documents"]["project/messages.md"]


def test_changes_md(tmp_path):
    _cases(tmp_path)
    r = dc.analyze(_status(), ["src/payments/a.ts"], "org/app", root=tmp_path)
    md = dc.build_changes_md(r, "aaa111", "HEAD")
    assert md.startswith("---\ntitle: Changes since the last documentation\ntype: changes\n")
    assert "| `project/business-rules.md` | `src/payments/a.ts` |" in md
    assert "`case-reviewer`" in md and "cases-US-001.md" in md


def test_command_line_with_git_and_index(tmp_path):
    repo = tmp_path / "app"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout.strip()
    git("init", "-q")
    git("config", "user.email", "t@t")
    git("config", "user.name", "t")
    (repo / "src/payments").mkdir(parents=True)
    (repo / "src/payments/a.ts").write_text("1", encoding="utf-8")
    git("add", ".")
    git("commit", "-qm", "one")
    initial = git("rev-parse", "HEAD")
    (repo / "src/payments/a.ts").write_text("2", encoding="utf-8")
    git("commit", "-qam", "two")

    doc = tmp_path / "doc"
    (doc / "project").mkdir(parents=True)
    (doc / "project/rules.md").write_text(f"---\ntitle: Rules\ntype: project\nupdated: {dt.date.today()}\n---\n", encoding="utf-8")
    base = ["--folder", str(doc)]
    assert dc.main(base + ["repo", "--provider", "github", "--name", "org/app", "--commit", initial]) == 0
    assert dc.main(base + ["register", "--document", "project/rules.md", "--sources", "src/payments/", "--repo", "org/app"]) == 0
    assert dc.main(base + ["changes", "--git", str(repo), "--mark"]) == 0
    status = json.loads((doc / ".status.json").read_text(encoding="utf-8"))
    assert status["documents"]["project/rules.md"]["outdated"]["files"] == ["src/payments/a.ts"]
    assert "+====" in (doc / "changes.md").read_text(encoding="utf-8")  # aligned tables

    assert index.main(["--folder", str(doc)]) == 0
    text = (doc / "INDEX.md").read_text(encoding="utf-8")
    assert f"Outdated (since {initial[:10]})" in text
    assert text.index("Changes since the last documentation") < text.index("## Project")
    assert ".status.json" not in text
