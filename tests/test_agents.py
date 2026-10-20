"""Agents and skills only load if their header (frontmatter) is valid YAML:
an unquoted "colon and space" in the description makes Claude Code ignore them."""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / ".claude" / "agents").glob("*.md")) + sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))


@pytest.mark.parametrize("file", FILES, ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.stem)
def test_valid_frontmatter(file):
    text = file.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "missing the --- ... --- header"
    data = yaml.safe_load(m.group(1))
    assert data.get("name") and data.get("description")
    if file.name != "SKILL.md":
        assert data["name"] == file.stem, "the name must match the file name"
        assert "When you are missing information or a confirmation" in text, "missing the questions section for subagents"
