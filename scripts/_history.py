"""Run history: each tool keeps its last 5 runs (with their evidence) so they can be compared.

Before a new run, the previous one is MOVED to <folder>/history/<date-time>/ with its JSON, its analysis,
its report and its evidence (screenshots, videos...), so its report still opens the same way. The 4
previous runs + the current one = 5 are kept; older ones are deleted.

In the report, `section(type, folder, data)` adds "Run history": which findings are new,
which were resolved and which persist since the previous run, the trend of the main indicators
and the link to the report of each saved run.

Used by the Python reports and, from Node, tools/k0lmena/tools/history/history.js (same logic).
"""
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import os

# How many runs are kept (the current one included): RUN_HISTORY from the environment, 5 by default.
MAX_RUNS = int(os.environ.get("RUN_HISTORY", "5")) if os.environ.get("RUN_HISTORY", "5").isdigit() and int(os.environ.get("RUN_HISTORY", "5")) > 1 else 5
FOLDER = "history"


# ------------------------------------------------------------------ archive
def _stamp(data_file):
    try:
        d = json.loads(Path(data_file).read_text(encoding="utf-8"))
        f = d.get("stamp") or d.get("date")
    except (OSError, ValueError):
        f = None
    if not f:
        f = datetime.fromtimestamp(Path(data_file).stat().st_mtime).isoformat(timespec="seconds")
    return re.sub(r"[^0-9A-Za-z-]+", "-", str(f))[:19].strip("-")


def archive(folder, names, data_file, max_runs=MAX_RUNS):
    """Moves the previous run (the `names` that exist) to history/<stamp>/ and prunes to max_runs - 1."""
    folder = Path(folder)
    data = folder / data_file
    if not data.exists():
        return None
    base = folder / FOLDER / _stamp(data)
    target, n = base, 2
    while target.exists():
        target, n = Path(f"{base}-{n}"), n + 1
    target.mkdir(parents=True)
    for name in names:
        src = folder / name
        if src.exists():
            shutil.move(str(src), str(target / name))
    prune(folder, max_runs - 1)
    return target


def prune(folder, keep):
    dirs = sorted((d for d in (Path(folder) / FOLDER).glob("*") if d.is_dir()), key=lambda d: d.name)
    for d in dirs[: max(0, len(dirs) - keep)]:
        shutil.rmtree(d, ignore_errors=True)


def load(folder, data_file):
    """Saved runs (oldest to newest): [{"stamp", "data", "report"}]."""
    output = []
    for d in sorted((Path(folder) / FOLDER).glob("*"), key=lambda d: d.name):
        file = d / data_file
        if not file.exists():
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        report = next((f"{FOLDER}/{d.name}/{h.name}" for h in sorted(d.glob("*-report.html"))), None)
        output.append({"stamp": d.name, "data": data, "report": report})
    return output[-(MAX_RUNS - 1):]


# ------------------------------------------------------------------ what is compared for each tool
_NO_NUMBERS = re.compile(r"[-+]?\d+([.,]\d+)?")


def _norm(s):
    return _NO_NUMBERS.sub("#", str(s or "")).strip().lower()


def _gaps(d):
    return [dict(x, story=h.get("story")) for h in d.get("stories") or [] for x in h.get("gaps") or []]


def _cov_pct(d):
    hs = d.get("stories") or []
    tot = sum(h["metrics"]["criteria"] for h in hs)
    return round(sum(h["metrics"]["covered_criteria"] for h in hs) / tot * 100) if tot else None


def _r(*keys):
    def f(d):
        v = d.get("summary") or {}
        for c in keys:
            v = (v or {}).get(c) if isinstance(v, dict) else None
        return v
    return f


TYPES = {
    "exploratory": {"file": "exploration.json", "items": lambda d: d.get("findings") or [],
                    "key": lambda h: f'{h.get("category")}|{_norm(h.get("title"))}|{h.get("page")}', "title": lambda h: h.get("title"),
                    "metrics": [("Findings", _r("findings"), ""), ("Broken links", _r("broken_links"), ""),
                                ("JavaScript errors", _r("js_errors"), ""), ("Average load", _r("load_avg_ms"), " ms")]},
    "accessibility": {"file": "audit.json", "items": lambda d: d.get("findings") or [],
                      "key": lambda h: h.get("rule") or _norm(h.get("title")), "title": lambda h: h.get("title"),
                      "metrics": [("Compliance", _r("compliance_pct"), " %"), ("Findings", _r("findings"), ""),
                                  ("Critical", _r("critical"), ""), ("Affected elements", _r("affected_elements"), "")]},
    "web-performance": {"file": "web-performance.json", "items": lambda d: d.get("findings") or [],
                        "key": lambda h: f'{h.get("category")}|{h.get("metric")}|{h.get("page")}|{h.get("device")}', "title": lambda h: h.get("title"),
                        "metrics": [("Mobile performance", _r("web_performance_mobile"), ""), ("Desktop performance", _r("web_performance_desktop"), ""),
                                    ("Findings", _r("findings"), ""), ("Opportunities", _r("opportunities"), "")]},
    "pixel-perfect": {"file": "pixel-perfect.json", "items": lambda d: d.get("findings") or [],
                      "key": lambda h: f'{h.get("type")}|{h.get("screen")}|{_norm(h.get("title"))}', "title": lambda h: f'{h.get("title")} ({h.get("resolution")})',
                      "metrics": [("Largest difference", _r("pct_max"), " %"), ("Screens with changes", _r("with_changes"), ""),
                                  ("Findings", _r("findings"), ""), ("Shifted elements", _r("shifted_elements"), "")]},
    "cross-browser": {"file": "cross-browser.json", "items": lambda d: d.get("findings") or [],
                      "key": lambda h: f'{h.get("type")}|{h.get("browser") or ",".join(h.get("failing") or [])}|{_norm(h.get("title"))}',
                      "title": lambda h: h.get("title"),
                      "metrics": [("Findings", _r("findings"), ""), ("Differences between browsers", lambda d: (d.get("summary") or {}).get("differences", (d.get("summary") or {}).get("with_issues")), ""),
                                  ("Fail in all", _r("fail_in_all"), "")]},
    "failures": {"file": "failures.json", "items": lambda d: d.get("failures") or [],
                 "key": lambda f: f.get("key") or f'{f.get("uri")}:{f.get("line")}', "title": lambda f: f'{f.get("case") or ""} {f.get("scenario")}'.strip(),
                 "metrics": [("With failures", _r("failed"), ""), ("Still failing", _r("still_failing"), ""),
                             ("Possible bugs", _r("by_category", "Possible bug"), ""), ("Flaky", _r("by_category", "Flaky"), "")]},
    "coverage": {"file": "coverage.json", "items": _gaps,
                 "key": lambda x: f'{x.get("story")}|{x.get("type")}|{x.get("ref")}', "title": lambda x: f'{x.get("story")} · {x.get("type")}: {x.get("detail")}',
                 "metrics": [("Covered criteria", _cov_pct, " %"), ("Gaps", lambda d: len(_gaps(d)), ""),
                             ("Automated", lambda d: sum(h["metrics"]["automated"] for h in d.get("stories") or []), "")]},
    "repair": {"file": "repairs.json", "items": lambda d: d.get("repairs") or [],
               "key": lambda r: f'{r.get("uri")}:{r.get("line")}', "title": lambda r: f'{r.get("case") or ""} {r.get("scenario")} · {r.get("diagnosis")}'.strip(),
               "metrics": [("Failures analyzed", _r("failures"), ""), ("With proposal", _r("with_proposal"), ""), ("Verified", _r("verified"), "")]},
    "emails": {"file": "emails.json", "items": lambda d: d.get("findings") or [],
               "key": lambda h: f'{h.get("type")}|{_norm(h.get("subject"))}|{_norm(h.get("title"))}', "title": lambda h: f'{h.get("title")} ({h.get("subject") or "no email"})',
               "metrics": [("Emails", _r("emails"), ""), ("Expectations met", _r("met"), ""), ("Findings", _r("findings"), ""),
                           ("Compatibility", _r("compatibility_avg"), " %")]},
    "translator": {"file": "translator.json", "items": lambda d: d.get("findings") or [],
                   "key": lambda h: f'{h.get("type")}|{h.get("language")}|{h.get("text") or _norm(h.get("title"))}', "title": lambda h: f'[{h.get("language")}] {h.get("title")}',
                   "metrics": [("Untranslated", _r("untranslated"), ""), ("Findings", _r("findings"), ""), ("Truncated", _r("truncated"), ""),
                               ("Visible keys", _r("keys"), "")]},
    "review": {"file": "review.json", "items": lambda d: [dict(x, case=f'{c.get("story")}:{c.get("id")}') for c in d.get("cases") or [] for x in c.get("findings") or []],
               "key": lambda x: f'{x.get("case")}|{x.get("type")}|{_norm(x.get("title"))}', "title": lambda x: f'{x.get("case")} · {x.get("title")}',
               "metrics": [("Average score", _r("avg_score"), ""), ("To improve", _r("to_improve"), ""), ("Problems", _r("findings"), ""),
                           ("Manual run", _r("total_time_min"), " min")]},
    "charters": {"file": "sessions.json", "items": lambda d: d.get("findings") or [],
                 "key": lambda b: f'{b.get("charter")}|{_norm(b.get("text"))}', "title": lambda b: f'{b.get("charter")} · {b.get("text")}',
                 "metrics": [("Sessions", _r("sessions"), ""), ("Bugs", _r("bugs"), ""), ("Questions", _r("questions"), ""), ("Minutes", _r("minutes"), " min")]},
    "ux": {"file": "ux.json", "items": lambda d: d.get("findings") or [],
           "key": lambda h: f'{h.get("heuristic")}|{_norm(h.get("title"))}', "title": lambda h: f'{h.get("heuristic")} · {h.get("title")}',
           "metrics": [("Heuristic score", _r("score"), ""), ("Findings", _r("findings"), ""), ("High", _r("by_severity", "High"), "")]},
    "forms": {"file": "forms.json", "items": lambda d: d.get("findings") or [],
              "key": lambda h: f'{h.get("form")}|{h.get("field")}|{h.get("type")}', "title": lambda h: f'{h.get("field") or h.get("form")} · {h.get("title")}',
              "metrics": [("Fields", _r("fields"), ""), ("Failing tests", _r("tests_failing"), ""), ("Findings", _r("findings"), "")]},
    "logs": {"file": "logs.json", "items": lambda d: d.get("signatures") or [],
             "key": lambda f: f.get("signature"), "title": lambda f: f'{f.get("level")} · {f.get("example", "")[:100]}',
             "metrics": [("Errors", _r("errors"), ""), ("Distinct signatures", _r("signatures"), ""), ("Warnings", _r("warnings"), "")]},
    "selection": {"file": "selection.json", "items": lambda d: [c for c in d.get("cases") or [] if c.get("group") != "Not selected"],
                  "key": lambda c: c.get("key"), "title": lambda c: f'{c.get("story")} · {c.get("id")} {c.get("title")}',
                  "metrics": [("Selected", _r("selected"), ""), ("Minutes", _r("selection_minutes"), " min"), ("Changes without cases", _r("no_coverage"), "")]},
    "dashboard": {"file": "dashboard.json", "items": lambda d: d.get("alerts") or [],
                  "key": lambda a: f'{a.get("type")}|{_norm(a.get("title"))}', "title": lambda a: f'{a.get("type")} · {a.get("title")}',
                  "metrics": [("Passed", _r("pct_passed"), " %"), ("Automated", _r("pct_automated"), " %"),
                              ("Coverage", _r("coverage_pct"), " %"), ("Open bugs", _r("open_bugs"), "")]},
}

ITEM_LABEL = {"dashboard": "alerts", "failures": "scenarios with failures", "coverage": "gaps", "repair": "repairs", "selection": "selected cases"}


def compare(type_, current, previous):
    t = TYPES[type_]
    a = {t["key"](x): x for x in t["items"](current)}
    b = {t["key"](x): x for x in t["items"](previous)} if previous else {}
    return {"new": [a[k] for k in a if k not in b], "resolved": [b[k] for k in b if k not in a], "persisting": [a[k] for k in a if k in b],
            "new_keys": {k for k in a if k not in b} if previous else set()}


def is_new(type_, item, comparison):
    return bool(comparison) and TYPES[type_]["key"](item) in comparison["new_keys"]


# ------------------------------------------------------------------ report section
def _date(stamp):
    m = re.match(r"(\d{4})-?(\d{2})-?(\d{2})[T_-]?(\d{2})-?(\d{2})", stamp or "")
    return f"{m.group(2)}/{m.group(3)} {m.group(4)}:{m.group(5)}" if m else (stamp or "")[:16]


def section(type_, folder, data):
    """HTML for "Run history" (or "" if the type is unknown)."""
    from _report_styles import e, kpi_tiles, table, line_chart, SERIES
    from _report_styles import section as card

    t = TYPES.get(type_)
    if not t:
        return ""
    previous = load(folder, t["file"])
    current_stamp = re.sub(r"[^0-9A-Za-z-]+", "-", str(data.get("stamp") or data.get("date") or "current"))[:19]
    runs = [dict(c, current=False) for c in previous] + [{"stamp": current_stamp, "data": data, "report": None, "current": True}]
    label = ITEM_LABEL.get(type_, "findings")
    if not previous:
        return card("Run history",
                    f'<div class="cardbody"><p class="muted">This is the first run saved in this folder. From the next one on you will see here which '
                    f'{e(label)} are new, which were resolved and how the indicators evolve (the last {MAX_RUNS} '
                    f'runs are kept in <span class="mono">history/</span>).</p></div>')
    cmp = compare(type_, data, previous[-1]["data"])
    parts = ['<div style="padding:18px 24px 4px">' + kpi_tiles([
        ("Saved runs", len(runs), "", f"the last {MAX_RUNS}, with their evidence", "clock"),
        ("New", len(cmp["new"]), "bad" if cmp["new"] else "ok", f"{label} that were not in the previous run", "warn"),
        ("Resolved", len(cmp["resolved"]), "ok" if cmp["resolved"] else "", f"{label} that no longer appear", "ok"),
        ("Persisting", len(cmp["persisting"]), "warn" if cmp["persisting"] else "ok", "were there and still are", "list"),
    ]) + "</div>"]

    charts = []
    x = list(range(len(runs)))
    for i, (name, f, unit) in enumerate(t["metrics"]):
        vals = []
        for c in runs:
            try:
                v = f(c["data"])
            except (KeyError, TypeError, ZeroDivisionError):
                v = None
            vals.append(v if isinstance(v, (int, float)) else None)
        if sum(v is not None for v in vals) < 2:
            continue
        fmt = (lambda u: (lambda v: f"{v:g}{u}"))(unit)
        fx = (lambda cs: (lambda v: _date(cs[int(v)]["stamp"]) if 0 <= int(v) < len(cs) else ""))(runs)
        charts.append(f'<div class="evo"><div class="lbl" style="margin:0 0 4px">{e(name)}</div>'
                      f'{line_chart(x, [(name, SERIES[i % len(SERIES)], vals)], fmt=fmt, fmt_x=fx, height=220, width=660)}</div>')
    if charts:
        parts.append('<style>.evos{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;padding:6px 24px 14px}'
                     '.evo{background:var(--bg);border:1px solid var(--border);border-radius:12px;padding:12px 8px 4px}'
                     '@media (max-width:900px){.evos{grid-template-columns:1fr}}</style>'
                     f'<div class="evos">{"".join(charts)}</div>')

    rows = []
    for c in reversed(runs):
        cells = [f'<strong style="color:var(--ink)">{e(_date(c["stamp"]))}</strong>' + (' <span class="pill">current</span>' if c["current"] else "")]
        for _, f, unit in t["metrics"]:
            try:
                v = f(c["data"])
            except (KeyError, TypeError, ZeroDivisionError):
                v = None
            cells.append(e(f"{v:g}{unit}") if isinstance(v, (int, float)) else '<span class="muted">—</span>')
        cells.append(f'<a href="{e(c["report"])}" style="color:var(--ink)">open report</a>' if c["report"]
                     else '<span class="muted">this one</span>' if c["current"] else '<span class="muted">no report</span>')
        rows.append(cells)
    parts.append(table(["Run"] + [m[0] for m in t["metrics"]] + ["Report"], rows))

    def items_list(title, items):
        if not items:
            return ""
        lis = "".join(f"<li>{e(t['title'](x))}</li>" for x in items[:12])
        more = f'<li class="muted">and {len(items) - 12} more</li>' if len(items) > 12 else ""
        return f'<div class="cardbody"><div class="lbl" style="margin:0 0 6px">{e(title)}</div><ul class="doclist">{lis}{more}</ul></div>'

    parts.append(items_list(f"New since the previous run ({_date(previous[-1]['stamp'])})", cmp["new"]))
    parts.append(items_list("Resolved since the previous run", cmp["resolved"]))
    return card("Run history", "".join(parts),
                f"compared with the {len(previous)} previous run(s) saved in history/")
