#!/usr/bin/env python3
"""
Generates the Synthetic monitoring report in HTML (dashboard, dark mode) from monitoring.json
(npm run monitor, tools/k0lmena/tools/monitoring/monitor.js).

Usage:
    python scripts/generate_monitoring_report.py <monitoring.json> <output.html>

What it shows: the state of the run (OK, Degraded or Down) and what changed since the previous one (what broke
and what recovered), indicators (checks OK, average time, availability across the saved runs,
certificates about to expire), the result of each check, the response times, the availability and the
time of each check across the runs in history/ and the link to each run's report.
"""
import argparse
import json
import sys
from pathlib import Path

from _report_styles import (e, page, meta, section, kpi_tiles, banner, table, bar_chart, line_chart, _pill,
                            CRITICAL, WARNING, OK, NEUTRAL, SERIES)

COLOR = {"OK": OK, "Slow": WARNING, "Expiring": WARNING, "Degraded": WARNING, "Down": CRITICAL}
ICON = {"OK": "✓", "Slow": "!", "Expiring": "!", "Degraded": "!", "Down": "✕"}
TONE = {"OK": "ok", "Degraded": "warn", "Down": "bad"}


def pill(state):
    return _pill(state or "—", COLOR.get(state, NEUTRAL), ICON.get(state, "●"))


def runs(folder, current):
    """Runs saved in history/ (from the oldest to the newest) + the current one: [(stamp, data, report)]."""
    out = []
    for d in sorted((Path(folder) / "history").glob("*"), key=lambda d: d.name):
        file = d / "monitoring.json"
        if not file.exists():
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        report = f"history/{d.name}/monitoring-report.html" if (d / "monitoring-report.html").exists() else None
        out.append((d.name, data, report))
    return out + [("current", current, None)]


def availability(items, check_id=None):
    """% of runs without Down (of one check, or of the whole run)."""
    states = []
    for _, d, _ in items:
        if check_id is None:
            states.append(d.get("state"))
        else:
            r = next((x for x in d.get("results") or [] if x.get("id") == check_id), None)
            if r:
                states.append(r.get("state"))
    return round(sum(1 for s in states if s != "Down") / len(states) * 100, 1) if states else None


def build_html(data, items):
    res = data.get("results") or []
    changes = data.get("changes") or {}
    state = data.get("state") or "—"
    body = []
    text = {"OK": "Everything responds", "Degraded": "It responds, with problems (slow or certificate about to expire)", "Down": "There are failing checks"}.get(state, state)
    if changes.get("broke"):
        text += f" · broke: {', '.join(changes['broke'])}"
    if changes.get("recovered"):
        text += f" · recovered: {', '.join(changes['recovered'])}"
    if changes.get("previous") and changes["previous"] != state:
        text += f" (before: {changes['previous']})"
    body.append(banner(text, TONE.get(state, "warn")))

    urls = [r for r in res if r.get("type") in ("URL", "Scenario") and r.get("ms") is not None]
    avg = round(sum(r["ms"] for r in urls) / len(urls)) if urls else None
    avail = availability(items)
    tls = [r for r in res if r.get("type") == "TLS" and r.get("remaining_days") is not None]
    min_tls = min((r["remaining_days"] for r in tls), default=None)
    ok = sum(1 for r in res if r.get("state") != "Down")
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("State", state, TONE.get(state, ""), f'before: {changes.get("previous") or "first run"}', "bolt"),
        ("Checks responding", f"{ok}/{len(res)}", "ok" if ok == len(res) else "bad", f'{sum(1 for r in res if r.get("state") in ("Slow", "Expiring"))} with warnings', "list"),
        ("Average time", f"{avg} ms" if avg is not None else "—", "", "of the URLs and scenarios", "clock"),
        ("Availability", f"{avail} %" if avail is not None else "—", "ok" if avail == 100 else ("warn" if avail and avail >= 95 else "bad"),
         f"in the last {len(items)} run(s)", "shield", {"pct": avail or 0}),
        ("Certificate", f"{min_tls} days" if min_tls is not None else "—", "warn" if min_tls is not None and any(r["state"] != "OK" for r in tls) else "",
         "time left until the nearest expiration", "key"),
    ]) + "</div>")

    rows = []
    for r in res:
        detail = r.get("reason") or ""
        if r.get("type") == "TLS" and r.get("expires"):
            detail = (detail + " · " if detail else "") + f'expires {r["expires"][:10]}' + (f' · {r["issuer"]}' if r.get("issuer") else "")
        rows.append([pill(r.get("state")), e(r.get("type")), f'<strong style="color:var(--ink)">{e(r.get("name"))}</strong><div class="muted mono">{e(r.get("url") or "")}</div>',
                     e(r.get("status") or "—"), e(f'{r["ms"]} ms' if r.get("ms") is not None else "—"), e(detail or "—")])
    body.append(section("Checks", table(["State", "Type", "Check", "HTTP", "Time", "Detail"], rows)))
    if urls:
        body.append(section("Response times", bar_chart([(r["name"][:60], r["ms"], COLOR.get(r["state"], OK)) for r in urls], label_width=320),
                            "in milliseconds, for this run"))

    if len(items) >= 2:
        ids = [r["id"] for r in urls][:8]
        x = list(range(len(items)))
        fx = lambda v: (items[int(v)][1].get("date") or "")[5:16].replace("T", " ") if 0 <= int(v) < len(items) else ""
        series = []
        for i, cid in enumerate(ids):
            values = []
            for _, d, _ in items:
                r = next((y for y in d.get("results") or [] if y.get("id") == cid), None)
                values.append(r["ms"] if r and r.get("ms") is not None and r.get("state") != "Down" else 0)
            name = next(r["name"] for r in urls if r["id"] == cid)
            series.append((name[:40], SERIES[i % len(SERIES)], values))
        if series:
            body.append(section("Time of each check across the runs", line_chart(x, series, fmt_x=fx, height=260), "0 = did not respond"))
        rows = []
        for r in res:
            marks = "".join(
                f'<span title="{e((d.get("date") or "")[:16])}: {e(st)}" style="display:inline-block;width:12px;height:18px;margin-right:2px;border-radius:3px;background:{COLOR.get(st, NEUTRAL)}"></span>'
                for _, d, _ in items
                for st in [next((y.get("state") for y in d.get("results") or [] if y.get("id") == r["id"]), None) or "—"])
            av = availability(items, r["id"])
            rows.append([e(r.get("name")), marks, e(f"{av} %" if av is not None else "—")])
        body.append(section("Availability per check", table(["Check", "Runs (from the oldest to the current one)", "Availability"], rows)))
        rows = [[e((d.get("date") or "")[:16].replace("T", " ")), pill(d.get("state")),
                 e(", ".join((d.get("changes") or {}).get("broke") or []) or "—"), e(", ".join((d.get("changes") or {}).get("recovered") or []) or "—"),
                 f'<a href="{e(rep)}">view report</a>' if rep else ("this run" if stamp == "current" else "—")]
                for stamp, d, rep in reversed(items)]
        body.append(section("Runs", table(["Date", "State", "Broke", "Recovered", "Report"], rows)))

    m = meta([("Monitoring", data.get("name")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
              ("Duration", f'{round((data.get("duration_ms") or 0) / 1000, 1)} s')])
    return page("Synthetic monitoring", "Synthetic monitoring", m, "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML synthetic monitoring report from monitoring.json")
    ap.add_argument("data_json")
    ap.add_argument("output")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    data = json.loads(Path(a.data_json).read_text(encoding="utf-8"))
    items = runs(Path(a.data_json).resolve().parent, data)
    Path(a.output).write_text(build_html(data, items), encoding="utf-8")
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
