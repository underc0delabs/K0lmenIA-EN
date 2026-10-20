"""Project integrity: everything the agents reference exists and the counts match.

Checks that "everything talks to everything": every `npm run`, script and tool an agent mentions
really exists, every skill has its folder with the right name, and the number of agents is consistent in
the README, AGENTS.md and the website."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AGENTS = sorted((ROOT / ".claude" / "agents").glob("*.md"))
SKILLS = sorted(p.parent.name for p in (ROOT / ".claude" / "skills").glob("*/SKILL.md"))


def _npm_scripts():
    keys = set()
    for rel in ("package.json", "tools/k0lmena/package.json"):
        p = ROOT / rel
        if p.exists():
            keys |= set((json.loads(p.read_text(encoding="utf-8")).get("scripts") or {}).keys())
    return keys | {"test", "connector"}


NPM = _npm_scripts()


def test_package_json_scripts_exist():
    cmds = json.loads((ROOT / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    missing = []
    for name, cmd in cmds.items():
        for ref in re.findall(r"'((?:tools|scripts)/[^']+\.py)'", cmd):
            if not (ROOT / ref).exists():
                missing.append(f"{name} -> {ref}")
    assert not missing, f"package.json scripts that point to nonexistent files: {missing}"


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_agent_references_exist(agent):
    t = agent.read_text(encoding="utf-8")
    missing = []
    for sc in set(re.findall(r"\b(scripts/[\w/]+\.py)", t)):
        if not (ROOT / sc).exists():
            missing.append(sc)
    for tl in set(re.findall(r"\b(tools/[\w/]+\.py)", t)):
        if not (ROOT / tl).exists():
            missing.append(tl)
    for gr in set(re.findall(r"\b(generate_\w+_report\.py)", t)):
        if not (ROOT / "scripts" / gr).exists():
            missing.append(f"scripts/{gr}")
    for run in set(re.findall(r"npm run ([a-z0-9:_-]+)", t)):
        if run not in NPM:
            missing.append(f"npm run {run}")
    assert not missing, f"{agent.name} references things that don't exist: {missing}"


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_name_matches_folder(skill):
    txt = (ROOT / ".claude" / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^name:\s*(.+)$", txt, re.M)
    assert m and m.group(1).strip() == skill, f"the frontmatter name doesn't match the folder {skill}"


def test_consistent_counts():
    n = len(AGENTS)
    assert f"{n} agents" in (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{n} agents" in (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert f"{n} agents" in (ROOT / "docs/index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("agent", AGENTS, ids=lambda p: p.stem)
def test_agent_has_card_on_website(agent):
    docs = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    assert f"<h4>{agent.stem}</h4>" in docs, f"{agent.stem} has no card in docs/index.html"
