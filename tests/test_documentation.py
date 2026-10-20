"""Index of input/documentation/ (project-documenter agent)."""
import datetime as dt
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import documentation_index as index  # noqa: E402


def _md(path, header, body="# File title\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    front = "".join(f"{k}: {v}\n" for k, v in header.items())
    path.write_text((f"---\n{front}---\n" if header else "") + body, encoding="utf-8")


def test_reads_header_and_tolerates_bom():
    assert index.read_header("﻿---\ntitle: Rules\ntype: project\n---\n# x") == {"title": "Rules", "type": "project"}
    assert index.read_header("# No header") == {}


def test_documents_by_type_with_story_and_added_by_hand(tmp_path):
    _md(tmp_path / "project" / "business-rules.md", {"title": "Rules", "type": "project", "sources": "github a/b", "updated": "2026-01-10"})
    _md(tmp_path / "stories" / "PROJ-12" / "dossier.md", {"title": "Dossier PROJ-12", "type": "story", "story": "PROJ-12", "updated": "2026-10-01"})
    _md(tmp_path / "project" / "functional-map.md", {"title": "Map", "type": "web", "updated": "2026-10-01"})
    (tmp_path / "project" / "functional-map.json").write_text("{}", encoding="utf-8")  # data of the .md: not listed separately
    _md(tmp_path / "user-manual.md", {}, "# User manual\n")
    (tmp_path / "minutes.pdf").write_bytes(b"%PDF")
    _md(tmp_path / "_draft.md", {"type": "project"})  # temporary files starting with _ are not listed
    (tmp_path / "INDEX.md").write_text("old", encoding="utf-8")

    docs = index.documents(tmp_path)
    assert [d["path"] for d in docs] == [
        "project/business-rules.md", "project/functional-map.md", "stories/PROJ-12/dossier.md", "minutes.pdf", "user-manual.md"]
    manual = docs[-1]
    assert manual["type"] == "manual" and manual["title"] == "User manual"

    text = index.build_index(docs, dt.date(2026, 10, 14), days=30)
    assert "5 document(s) · 1 to review" in text
    assert "| `project/business-rules.md` | Rules | github a/b | 2026-01-10 | Review |" in text
    assert "| `stories/PROJ-12/dossier.md` | Dossier PROJ-12 | PROJ-12 | - | 2026-10-01 | Current |" in text
    assert text.index("## Project") < text.index("## Web application") < text.index("## Stories") < text.index("## Added by hand")


def test_without_documentation_says_so(tmp_path):
    assert "There is no documentation yet" in index.build_index([], dt.date(2026, 10, 14), 30)


def test_main_writes_index_with_aligned_tables(tmp_path, capsys):
    _md(tmp_path / "project" / "summary.md", {"title": "Summary", "type": "project", "updated": dt.date.today().isoformat()})
    assert index.main(["--folder", str(tmp_path)]) == 0
    text = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    assert "+====" in text and "Summary" in text  # format_tables.py turned it into ASCII
    assert "1 document(s)" in capsys.readouterr().out


def test_generated_documentation_is_not_versioned():
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "/input/documentation/*" in rules and "!/input/documentation/.gitkeep" in rules
    assert os.path.exists(ROOT / "input" / "documentation" / ".gitkeep")
