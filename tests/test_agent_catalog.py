"""AGENTS.md must name every agent and skill, and the skills it says each agent uses
must be the ones the agent actually mentions in its file."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
AGENTS = sorted(p.stem for p in (ROOT / ".claude" / "agents").glob("*.md"))
SKILLS = sorted(p.parent.name for p in (ROOT / ".claude" / "skills").glob("*/SKILL.md"))


def summary_row(agent):
    for line in CATALOG.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == agent:
            return cells
    return None


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_in_catalog(agent):
    assert f"### {agent}\n" in CATALOG, "missing its section in AGENTS.md"
    assert summary_row(agent), "missing its row in the AGENTS.md summary table"


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_skills(agent):
    text = (ROOT / ".claude" / "agents" / f"{agent}.md").read_text(encoding="utf-8")
    uses = {s for s in SKILLS if re.search(r"\b" + re.escape(s) + r"\b", text)}
    says = {s.strip() for s in summary_row(agent)[3].split(",") if s.strip() in SKILLS}
    assert says == uses, f"AGENTS.md says {sorted(says)}, the agent uses {sorted(uses)}"


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_in_catalog(skill):
    assert f"| {skill} " in CATALOG, "missing from the AGENTS.md skills table"
