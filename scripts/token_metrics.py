#!/usr/bin/env python3
"""
Token usage metrics of the k0lmenIA agents.

Usage (from the repo root):
    python scripts/token_metrics.py [--name <name>] [--from YYYY-MM-DD] [--until YYYY-MM-DD]
                                      [--folder <transcripts>] [--output <folder>]
    npm run metrics

Where the data comes from: Claude Code saves each session in ~/.claude/projects/<repo path>/ as
<session>.jsonl (the main conversation) and <session>/subagents/agent-<id>.jsonl + .meta.json (each
subagent, with its agentType: story-analyst, manual-case-generator, …). Each model response
carries message.usage (input_tokens, output_tokens, cache_creation_input_tokens with the 5m/1h detail,
cache_read_input_tokens) and message.model. The same response appears on several lines (one per block):
it is counted only once per message.id.

The usage is attributed to each agent (subagents by their type; the rest to "main conversation") and
aggregated per agent, per day and per model: calls, tokens (input, output, cache write and read),
% of cache and estimated cost with the PRICES table. If present, it adds the costs of the evals
(evals/results/*/results.json). It also points out opportunities: the agents that spend the most, the ones
used many times (candidates to automate in k0lmena, which runs with no tokens) and low cache.

Privacy: it never reads, stores or shows the text of the messages; only counts, models and agent names.

Leaves output/token-metrics/<name>/ with metrics.json and metrics-report.html; the previous run moves
to history/ (last 5).
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

# ------------------------------------------------------------------ prices
# USD per million tokens. Source: the models table of the Claude API documentation (claude-api
# skill, cached on 2026-10-06). Cache write: ×1.25 the input (5 minutes) and ×2 (1 hour);
# read: the published value if there is one, otherwise ×0.1 the input. Edit this table if prices change.
# Haiku 5.5 charges more above 100K prompt tokens ($0.50 / $2.50): the base price is used here.
PRICES_DATE = "2026-10-06"
_P = {  # model: (input, output, cache read or None)
    "claude-fable-5-1": (10.00, 50.00, 0.25), "claude-mythos-5-1": (10.00, 50.00, 0.25),
    "claude-fable-5": (10.00, 50.00, None), "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, None), "claude-opus-4-8": (5.00, 25.00, None), "claude-opus-4-7": (5.00, 25.00, None),
    "claude-opus-4-6": (5.00, 25.00, None), "claude-sonnet-5-5": (2.00, 10.00, 0.20), "claude-sonnet-5": (2.00, 10.00, None),
    "claude-sonnet-4-6": (3.00, 15.00, None), "claude-haiku-5-5": (0.10, 0.50, None), "claude-haiku-4-5": (1.00, 5.00, None),
}
PRICES = {m: {"input": i, "output": o, "cache_5m": i * 1.25, "cache_1h": i * 2.0, "cache_read": r if r is not None else i * 0.1}
          for m, (i, o, r) in _P.items()}
GENERATED = ["metrics.json", "metrics-report.html"]
MAIN = "main conversation"
# An agent used this many times or more in the period is a candidate to automate.
REPEATED_THRESHOLD = 5


def price_of(model):
    """Price of the model (accepts suffixes such as [1m] or dates); None if it is not in the table."""
    m = re.sub(r"\[.*?\]$", "", model or "")
    if m in PRICES:
        return PRICES[m]
    for k in sorted(PRICES, key=len, reverse=True):
        if m.startswith(k):
            return PRICES[k]
    return None


def cost(usage, model):
    """Estimated cost in USD of a usage, or None if the model has no price."""
    p = price_of(model)
    if not p:
        return None
    return (usage["input"] * p["input"] + usage["output"] * p["output"] + usage["cache_5m"] * p["cache_5m"]
            + usage["cache_1h"] * p["cache_1h"] + usage["cache_read"] * p["cache_read"]) / 1_000_000


def transcripts_folder(root=ROOT):
    """~/.claude/projects/<path with slashes and colons changed to hyphens>: the repo's or, if Claude Code
    was opened in a folder that contains it, that folder's."""
    base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"
    existing = {d.name.lower(): d for d in base.glob("*")} if base.is_dir() else {}
    path = Path(root).resolve()
    for r in [path, *path.parents]:
        name = re.sub(r"[\\/:]", "-", str(r)).rstrip("-")
        if name.lower() in existing:
            return existing[name.lower()]
    return base / re.sub(r"[\\/:]", "-", str(path))


def _usage_of(usage):
    cc = usage.get("cache_creation") or {}
    total_cc = int(usage.get("cache_creation_input_tokens") or 0)
    h1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
    m5 = int(cc.get("ephemeral_5m_input_tokens") or 0) or max(0, total_cc - h1)
    return {"input": int(usage.get("input_tokens") or 0), "output": int(usage.get("output_tokens") or 0),
            "cache_5m": m5, "cache_1h": h1, "cache_read": int(usage.get("cache_read_input_tokens") or 0)}


def read_transcript(file):
    """[(timestamp, model, usage, tools used)] per response (once per message.id)."""
    responses = {}
    try:
        fh = open(file, encoding="utf-8")
    except OSError:
        return []
    with fh:
        for line in fh:
            if '"assistant"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("type") != "assistant":
                continue
            m = d.get("message") or {}
            usage = m.get("usage")
            if not usage or m.get("model") in (None, "<synthetic>"):
                continue
            key = m.get("id") or d.get("uuid")
            prev = responses.get(key)
            tools = set(prev[3]) if prev else set()
            for block in m.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools.add(str(block.get("name")))
            responses[key] = (d.get("timestamp") or "", m.get("model"), _usage_of(usage), sorted(tools))
    return list(responses.values())


def collect(folder, date_from=None, date_until=None):
    """Records per response: [{"agent", "session", "invocation", "date", "model", "usage", "tools"}]."""
    folder = Path(folder)
    records = []
    for session in sorted(folder.glob("*.jsonl")):
        sources = [(session, MAIN, session.stem)]
        sub = folder / session.stem / "subagents"
        for t in sorted(sub.glob("agent-*.jsonl")) if sub.is_dir() else []:
            meta = {}
            try:
                meta = json.loads(t.with_suffix(".meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            sources.append((t, meta.get("agentType") or "subagent", t.stem))
        for file, agent, invocation in sources:
            for ts, model, usage, tools in read_transcript(file):
                try:
                    f = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().date()
                except ValueError:
                    continue
                if (date_from and f < date_from) or (date_until and f > date_until):
                    continue
                records.append({"agent": agent, "session": session.stem, "invocation": invocation, "date": f.isoformat(),
                                "model": model, "usage": usage, "tools": tools})
    return records


def evals_costs(root=ROOT, date_from=None, date_until=None):
    """Cost of the eval runs (evals/results/<date>/results.json), if they exist."""
    output = []
    for file in sorted(glob.glob(str(Path(root) / "evals" / "results" / "*" / "results.json"))):
        try:
            d = json.loads(Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        day = str(d.get("date") or Path(file).parent.name)[:10]
        try:
            f = date.fromisoformat(day)
            if (date_from and f < date_from) or (date_until and f > date_until):
                continue
        except ValueError:
            pass
        total = 0.0
        for c in d.get("cases") or []:
            v = c.get("cost_usd") if isinstance(c, dict) else None
            v = v if v is not None else (c.get("metrics") or {}).get("cost_usd") if isinstance(c, dict) else None
            total += float(v or 0)
        total = float(d.get("total_cost_usd") or total)
        output.append({"run": Path(file).parent.name, "date": day, "cost_usd": round(total, 4), "cases": len(d.get("cases") or [])})
    return output


def _empty():
    return {"calls": 0, "input": 0, "output": 0, "cache_5m": 0, "cache_1h": 0, "cache_read": 0,
            "cost_usd": 0.0, "no_price": 0}


def _add(acc, r):
    acc["calls"] += 1
    for k in ("input", "output", "cache_5m", "cache_1h", "cache_read"):
        acc[k] += r["usage"][k]
    c = cost(r["usage"], r["model"])
    if c is None:
        acc["no_price"] += 1
    else:
        acc["cost_usd"] += c


def _pct_cache(a):
    read = a["input"] + a["cache_5m"] + a["cache_1h"] + a["cache_read"]
    return round(100 * a["cache_read"] / read, 1) if read else 0.0


def aggregate(records, evals=None):
    total, by_agent, by_day, by_model = _empty(), defaultdict(_empty), defaultdict(_empty), defaultdict(_empty)
    invocations, tools = defaultdict(set), defaultdict(lambda: defaultdict(int))
    for r in records:
        for acc in (total, by_agent[r["agent"]], by_day[r["date"]], by_model[r["model"]]):
            _add(acc, r)
        invocations[r["agent"]].add(r["invocation"])
        for h in r["tools"]:
            tools[r["agent"]][h] += 1
    agents = []
    for name, a in by_agent.items():
        top = sorted(tools[name].items(), key=lambda kv: -kv[1])[:5]
        agents.append({"agent": name, **a, "cost_usd": round(a["cost_usd"], 4), "invocations": len(invocations[name]),
                       "pct_cache": _pct_cache(a), "tools": [h for h, _ in top]})
    agents.sort(key=lambda x: (-x["cost_usd"], -x["output"]))
    days = [{"date": f, **a, "cost_usd": round(a["cost_usd"], 4)} for f, a in sorted(by_day.items())]
    models = [{"model": m, **a, "cost_usd": round(a["cost_usd"], 4), "has_price": price_of(m) is not None}
              for m, a in sorted(by_model.items(), key=lambda kv: -kv[1]["cost_usd"])]
    evals = evals or []
    evals_cost = round(sum(x["cost_usd"] for x in evals), 4)
    summary = {"calls": total["calls"], "cost_usd": round(total["cost_usd"], 4), "evals_cost_usd": evals_cost,
               "output_tokens": total["output"], "input_tokens_total": total["input"] + total["cache_5m"] + total["cache_1h"] + total["cache_read"],
               "pct_cache": _pct_cache(total), "agents": len([a for a in agents if a["agent"] != MAIN]),
               "sessions": len({r["session"] for r in records}), "no_price": total["no_price"]}
    return {"summary": summary, "agents": agents, "days": days, "models": models, "evals": evals,
            "opportunities": opportunities(agents, summary)}


def opportunities(agents, summary):
    """Recommendations from the numbers (text, without making anything up)."""
    output = []
    subs = [a for a in agents if a["agent"] != MAIN and a["cost_usd"] > 0]
    total = summary["cost_usd"] or 0
    if subs and total:
        top = subs[0]
        output.append({"type": "Highest spend", "agent": top["agent"],
                       "detail": f'{top["agent"]} is the agent that spends the most: ${top["cost_usd"]:.2f} '
                                 f'({100 * top["cost_usd"] / total:.0f} % of the total) in {top["invocations"]} use(s).'})
    for a in agents:
        if a["agent"] in (MAIN, "fork", "subagent", "general-purpose", "Explore", "Plan"):
            continue
        if a["invocations"] >= REPEATED_THRESHOLD:
            output.append({"type": "Candidate to automate", "agent": a["agent"],
                           "detail": f'{a["agent"]} was used {a["invocations"]} times. If it is to run the same tests, '
                                     f'automate them in k0lmena: afterwards they run with npm test, with no tokens.'})
    for a in agents:
        if a["calls"] >= 20 and a["pct_cache"] < 50:
            output.append({"type": "Low cache", "agent": a["agent"],
                           "detail": f'{a["agent"]} reuses only {a["pct_cache"]:.0f} % of the input from cache: '
                                     f'short conversations or context that changes on every call.'})
    if summary.get("no_price"):
        output.append({"type": "No price", "agent": "—",
                       "detail": f'{summary["no_price"]} response(s) from models that are not in the prices table: '
                                 f'their cost is not added (update PRICES in scripts/token_metrics.py).'})
    return output


# ------------------------------------------------------------------ report
def _usd(v):
    return f"${v:,.2f}" if v >= 0.01 or v == 0 else f"${v:.4f}"


def _k(n):
    return f"{n / 1_000_000:.1f} M" if n >= 1_000_000 else f"{n / 1000:.1f} K" if n >= 1000 else str(n)


def build_html(data, folder=None):
    from _report_styles import (e, page, meta, section, kpi_tiles, table, bar_chart, column_chart, doc_list, two_col,
                                  banner, SERIES)
    import _history
    r = data["summary"]
    if not data["agents"]:
        body = section("No data", f'<div class="cardbody"><p>{e(data.get("warning") or "There is no usage recorded in the period.")}</p></div>')
        return page("Token usage", "Token metrics", meta([("Period", data.get("period"))]), body)
    series = [d["cost_usd"] for d in data["days"]]
    body = [kpi_tiles([
        ("Estimated cost", _usd(r["cost_usd"]), "", f'{r["calls"]} model response(s)', "load", {"series": series} if len(series) > 1 else None),
        ("Tokens generated", _k(r["output_tokens"]), "", f'{_k(r["input_tokens_total"])} read', "bolt"),
        ("Read from cache", f'{r["pct_cache"]:.0f} %', "ok" if r["pct_cache"] >= 70 else "warn", "of the input", "clock", {"pct": r["pct_cache"]}),
        ("Agents used", r["agents"], "", f'in {r["sessions"]} session(s)', "person"),
    ])]
    if r.get("no_price"):
        body.append(banner(f'{r["no_price"]} response(s) from models with no price in the table: their cost is not added.', "warn"))
    top = data["agents"][:12]
    body.append(two_col(
        section("Cost per agent", bar_chart([(a["agent"], round(a["cost_usd"], 2), SERIES[0]) for a in top], label_width=190), "estimated USD"),
        section("Cost per day", column_chart([(d["date"][5:], round(d["cost_usd"], 2)) for d in data["days"][-14:]],
                                             fmt=lambda v: f"${v:,.2f}", height=240, width=660), "last 14 days with usage")))
    rows = [[f'<b>{e(a["agent"])}</b>', a["invocations"], a["calls"], _k(a["input"] + a["cache_5m"] + a["cache_1h"] + a["cache_read"]),
             _k(a["output"]), f'{a["pct_cache"]:.0f} %', e(_usd(a["cost_usd"])), e(", ".join(a["tools"]) or "—")] for a in data["agents"]]
    body.append(section("Detail per agent", table(["Agent", "Uses", "Responses", "Tokens read", "Tokens generated", "Cache",
                                                   "Cost", "Most used tools"], rows)))
    rows_m = [[e(m["model"]), m["calls"], _k(m["output"]), e(_usd(m["cost_usd"])) if m["has_price"] else '<span class="muted">no price</span>']
              for m in data["models"]]
    op = [f'{o["type"]}: {o["detail"]}' for o in data["opportunities"]]
    body.append(two_col(section("By model", table(["Model", "Responses", "Tokens generated", "Cost"], rows_m)),
                        section("Opportunities", doc_list(op or ["No clear opportunities in this period."]))))
    if data.get("evals"):
        body.append(section("Agent evals", table(["Run", "Date", "Cases", "Cost"],
                                                 [[e(x["run"]), e(x["date"]), x["cases"], e(_usd(x["cost_usd"]))] for x in data["evals"]]),
                            f'{_usd(r["evals_cost_usd"])} in total'))
    body.append(section("How it is calculated", f'''<div class="cardbody"><p>The Claude Code transcripts of this project are read
(<span class="mono">{e(data.get("source", ""))}</span>): each model response carries the input, output and cache tokens. The
subagents are identified by their type; the rest is the main conversation. The cost is an <b>estimate</b> with the prices per
million tokens as of {e(data.get("prices_date", PRICES_DATE))} (the script's <span class="mono">PRICES</span> table); it does not
replace the actual billing. The text of the messages is not read.</p></div>'''))
    if folder:
        body.append(_history.section("tokens", folder, data))
    return page("Token usage", "Token metrics", meta([("Period", data.get("period")), ("Generated", data.get("date", "")[:16].replace("T", " "))]),
                "".join(body))


# ------------------------------------------------------------------ history
import _history  # noqa: E402

_history.TYPES.setdefault("tokens", {
    "file": "metrics.json", "items": lambda d: d.get("opportunities") or [],
    "key": lambda o: f'{o.get("type")}|{o.get("agent")}', "title": lambda o: f'{o.get("type")} · {o.get("agent")}',
    "metrics": [("Cost (USD)", _history._r("cost_usd"), ""), ("Responses", _history._r("calls"), ""),
                ("Cache", _history._r("pct_cache"), " %"), ("Agents", _history._r("agents"), "")]})


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Token usage metrics of the k0lmenIA agents")
    ap.add_argument("--name", default="general")
    ap.add_argument("--from", dest="date_from", type=date.fromisoformat)
    ap.add_argument("--until", dest="date_until", type=date.fromisoformat)
    ap.add_argument("--days", type=int, help="shortcut: the last N days")
    ap.add_argument("--folder", help="transcripts folder (by default this project's in ~/.claude/projects)")
    ap.add_argument("--output", help="output folder (by default output/token-metrics/<name>)")
    a = ap.parse_args(argv)
    if a.days:
        a.date_from = date.today() - timedelta(days=a.days - 1)
    if not re.fullmatch(r"[\w.-]+", a.name):
        ap.error("--name: only letters, digits, period, hyphen and underscore")
    source = Path(a.folder) if a.folder else transcripts_folder()
    folder = Path(a.output) if a.output else ROOT / "output" / "token-metrics" / a.name
    folder.mkdir(parents=True, exist_ok=True)
    period = f'{a.date_from or "start"} to {a.date_until or "today"}'
    records = collect(source, a.date_from, a.date_until) if source.is_dir() else []
    data = aggregate(records, evals_costs(ROOT, a.date_from, a.date_until))
    data.update({"date": datetime.now().isoformat(timespec="seconds"), "period": period, "source": str(source),
                 "prices_date": PRICES_DATE, "name": a.name})
    if not source.is_dir():
        data["warning"] = (f"I cannot find the Claude Code transcripts in {source}. They are generated when Claude Code is used in this "
                           "project (they do not exist in CI or on another machine); pass another folder with --folder.")
        print(data["warning"])
    _history.archive(folder, GENERATED, "metrics.json")
    (folder / "metrics.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "metrics-report.html").write_text(build_html(data, folder), encoding="utf-8")
    r = data["summary"]
    print(f'{r["calls"]} response(s) · {r["agents"]} agent(s) · estimated cost ${r["cost_usd"]:.2f} · cache {r["pct_cache"]:.0f} %')
    print(f"Report: {folder / 'metrics-report.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
