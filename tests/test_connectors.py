"""MCP connectors: Claude Code has to start without asking for approvals, and the optional ones in the
catalog (npm run connector) have to point to scripts and versions that exist."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_everything_in_mcp_json_is_enabled():
    # A server in .mcp.json that isn't in enabledMcpjsonServers triggers the approval prompt at startup.
    servers = set(_json(".mcp.json")["mcpServers"])
    enabled = set(_json(".claude/settings.json")["enabledMcpjsonServers"])
    assert servers == enabled


def test_catalog_points_to_existing_scripts_and_versions():
    catalog = _json("scripts/mcp/catalog.json")["connectors"]
    versions = set(re.findall(r"'([@\w/.-]+)':\s*'[\d.]+'", (ROOT / "scripts/mcp/launch.js").read_text(encoding="utf-8")))
    assert not set(catalog) & set(_json(".mcp.json")["mcpServers"]), "a connector can't be on both sides"
    for name, c in catalog.items():
        s = c["server"]
        text = json.dumps(s)
        assert "@latest" not in text, name
        for script in re.findall(r"scripts/mcp/[\w.-]+\.js", text):
            assert (ROOT / script).exists(), f"{name}: {script} does not exist"
        if "--" in s.get("args", []):  # with-env.js ... -- <package>
            package = s["args"][s["args"].index("--") + 1]
            assert package in versions, f"{name}: {package} has no pinned version in launch.js"
