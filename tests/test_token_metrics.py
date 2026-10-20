"""Token usage metrics: attribution per agent, deduplication, costs and privacy."""
import json

import token_metrics as mt


def _response(mid, model, input_, output, read=0, write=0, ts="2026-10-14T12:00:00Z", tools=(), text="secret"):
    content = [{"type": "text", "text": text}] + [{"type": "tool_use", "name": h, "input": {}} for h in tools]
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {
        "id": mid, "model": model, "content": content,
        "usage": {"input_tokens": input_, "output_tokens": output, "cache_read_input_tokens": read,
                  "cache_creation_input_tokens": write, "cache_creation": {"ephemeral_5m_input_tokens": write}}}})


def _project(tmp_path):
    base = tmp_path / "projects" / "E--repo"
    sub = base / "s1" / "subagents"
    sub.mkdir(parents=True)
    # the same response appears on two lines (one per block): it is counted once
    (base / "s1.jsonl").write_text("\n".join([
        json.dumps({"type": "user", "message": {"content": "hello"}}),
        _response("m1", "claude-opus-5-5", 1000, 100, read=9000, tools=["Bash"]),
        _response("m1", "claude-opus-5-5", 1000, 100, read=9000, tools=["Read"]),
        _response("m2", "new-model-x", 10, 10, ts="2026-10-13T10:00:00Z"),
    ]), encoding="utf-8")
    (sub / "agent-a1.jsonl").write_text(_response("m3", "claude-sonnet-5-5", 2000, 500, write=4000), encoding="utf-8")
    (sub / "agent-a1.meta.json").write_text(json.dumps({"agentType": "manual-case-generator"}), encoding="utf-8")
    return base


def test_attributes_deduplicates_and_computes_costs(tmp_path):
    regs = mt.collect(_project(tmp_path))
    assert len(regs) == 3
    d = mt.aggregate(regs)
    agents = {a["agent"]: a for a in d["agents"]}
    assert set(agents) == {mt.MAIN, "manual-case-generator"}
    main = agents[mt.MAIN]
    assert main["calls"] == 2 and main["no_price"] == 1 and sorted(main["tools"]) == ["Bash", "Read"]
    # Opus 5.5: 1000 × $4 + 100 × $20 + 9000 × $0.20 per million
    assert abs(main["cost_usd"] - (1000 * 4 + 100 * 20 + 9000 * 0.20) / 1e6) < 1e-9
    # Sonnet 5.5 with a 5-minute cache write (×1.25 the input)
    gen = agents["manual-case-generator"]
    assert abs(gen["cost_usd"] - (2000 * 2 + 500 * 10 + 4000 * 2.5) / 1e6) < 1e-9
    assert d["summary"]["no_price"] == 1 and any(o["type"] == "No price" for o in d["opportunities"])


def test_filters_by_date_and_does_not_store_text(tmp_path):
    from datetime import date
    regs = mt.collect(_project(tmp_path), date_from=date(2026, 10, 14))
    assert {r["model"] for r in regs} == {"claude-opus-5-5", "claude-sonnet-5-5"}
    assert "secret" not in json.dumps(mt.aggregate(regs))


def test_project_folder_or_parent_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    root = tmp_path / "E" / "repo"
    root.mkdir(parents=True)
    parent = str((tmp_path / "E").resolve())
    for c in (chr(92), "/", ":"):
        parent = parent.replace(c, "-")
    (tmp_path / "projects" / parent).mkdir(parents=True)
    assert mt.transcripts_folder(root).name == parent


def test_cli_and_report_and_candidates(tmp_path, capsys):
    base = _project(tmp_path)
    sub = base / "s1" / "subagents"
    for i in range(2, 7):
        (sub / f"agent-a{i}.jsonl").write_text(_response(f"x{i}", "claude-sonnet-5-5", 100, 10), encoding="utf-8")
        (sub / f"agent-a{i}.meta.json").write_text(json.dumps({"agentType": "e2e-runner"}), encoding="utf-8")
    output = tmp_path / "out"
    assert mt.main(["--folder", str(base), "--output", str(output), "--name", "t"]) == 0
    d = json.loads((output / "metrics.json").read_text(encoding="utf-8"))
    assert any(o["type"] == "Candidate to automate" and o["agent"] == "e2e-runner" for o in d["opportunities"])
    html = (output / "metrics-report.html").read_text(encoding="utf-8")
    assert "Cost per agent" in html and "secret" not in html


def test_without_transcripts_says_so(tmp_path, capsys):
    assert mt.main(["--folder", str(tmp_path / "does-not-exist"), "--output", str(tmp_path / "o")]) == 0
    assert "I cannot find the Claude Code transcripts" in (tmp_path / "o" / "metrics-report.html").read_text(encoding="utf-8")


def test_dashboard_adds_token_usage(tmp_path):
    import quality_dashboard as dashboard
    from pathlib import Path
    d = tmp_path / "output" / "token-metrics" / "general"
    d.mkdir(parents=True)
    (d / "metrics.json").write_text(json.dumps({"period": "x", "summary": {"calls": 3, "cost_usd": 1.5, "pct_cache": 80},
                                                "agents": [{"agent": "story-analyst"}]}), encoding="utf-8")
    real = dashboard.ROOT
    try:
        dashboard.use_root(tmp_path)
        ex = dashboard.extras()
    finally:
        dashboard.use_root(Path(real))
    assert ex["tokens"] == [{"name": "general", "period": "x", "cost_usd": 1.5, "pct_cache": 80, "top_agent": "story-analyst"}]
