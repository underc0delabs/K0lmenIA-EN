#!/usr/bin/env python3
"""
Session-based exploratory testing charters (charter-generator agent): the sheet for each session and,
after the sessions, the report built from the notes.

Usage (from the repo root):
    python scripts/generate_charters.py --name US-001                   → builds the sheets (charters.json → charters.html and charters.md)
    python scripts/generate_charters.py --name US-001 --report          → reads sessions/*.md and builds sessions-report.html

Folder: output/charters/<name>/ with charters.json (written by the agent), charters.html (to print or
share: one sheet per session), charters.md, sessions/CH-01.md (a notes template per charter, to
fill in during the session) and sessions-report.html. The previous report moves to history/ (last 5).

charters.json:
{
  "story": "US-001", "title": "Checkout", "goal": "Find payment risks before the release",
  "charters": [
    {"id": "CH-01", "mission": "Explore card payment with boundary data to discover validation errors",
     "areas": ["Card form", "Error messages"], "risks": ["Duplicate charges"],
     "heuristics": ["Boundary values", "Interruptions"], "data": ["Expired card 4111..."],
     "ideas": ["Pay twice in a row"], "duration_min": 60, "priority": "High",
     "out_of_scope": ["Bank transfer payments"], "questions": ["What happens if the bank is slow?"]}
  ]
}

Notes of a session (sessions/CH-01.md): header and prefixed lines; everything else is ignored.
    Charter: CH-01
    Tester: Ana
    Date: 2026-10-12
    Duration: 60
    Time: setup 10, testing 35, bugs 15        (minutes: the TBS split of session-based testing)
    BUG: The total does not add shipping [High]
    QUESTION: Is the coupon applied before or after shipping?
    IDEA: Try with two tabs open
    RISK: If the bank is slow, there is no message
    COVERED: Card form
    NOT COVERED: Error messages
    NOTE: I used the Visa test card
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _history  # noqa: E402
from _report_styles import (e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, stacked_bars, two_col,  # noqa: E402
                            level_badge, _pill, CRITICAL, WARNING, NEUTRAL, OK, SERIES)

LABELS = {"BUG": "bugs", "QUESTION": "questions", "IDEA": "ideas", "RISK": "risks", "COVERED": "covered", "NOT COVERED": "uncovered", "NOTE": "notes"}

CSS_CH = """
<style>
.sheet{border:1px solid var(--border);border-radius:14px;background:var(--bg);padding:20px 22px;margin:14px 24px;page-break-inside:avoid}
.sheet h3{font-size:18px;color:var(--ink);display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.mission{font-size:15px;color:var(--ink);line-height:1.55;border-left:3px solid var(--accent);padding:6px 12px;margin:8px 0 14px;background:rgba(249,176,6,.06);border-radius:0 8px 8px 0}
.grid2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 22px}
.grid2 .lbl{margin:0 0 4px}
.grid2 ul{margin:0;padding-left:18px;color:var(--body);font-size:13px}
.notes{margin-top:14px;border:1px dashed var(--border);border-radius:10px;padding:10px 12px;color:var(--muted);font-size:12.5px;min-height:90px}
.tags{display:flex;gap:6px;flex-wrap:wrap}
@media (max-width:760px){.grid2{grid-template-columns:1fr}}
@media print{body{background:#fff}.sheet{background:#fff;color:#000;border-color:#999}}
</style>
"""


def _list(xs):
    xs = [x for x in xs or [] if str(x).strip()]
    return "<ul>" + "".join(f"<li>{e(x)}</li>" for x in xs) + "</ul>" if xs else '<p class="muted">—</p>'


def html_sheets(data):
    chs = data.get("charters") or []
    total = sum(c.get("duration_min") or 0 for c in chs)
    body = [banner(data.get("goal") or f'{len(chs)} exploration session(s)', "ok"),
            '<div style="margin-top:20px">' + kpi_tiles([
                ("Charters", len(chs), "", data.get("title") or "", "list"),
                ("Total time", f"{total} min", "", "planned duration of the sessions", "clock"),
                ("High priority", sum(1 for c in chs if c.get("priority") in ("Critical", "High")), "", "start with these", "target"),
                ("Risks covered", len({r for c in chs for r in c.get("risks") or []}), "", "distinct risks the sessions target", "warn"),
            ]) + "</div>"]
    rows = [[f'<a href="#{e(c["id"])}" style="color:var(--ink)">{e(c["id"])}</a>', f'<strong style="color:var(--ink)">{e(c.get("mission"))}</strong>',
             level_badge(c.get("priority") or "Medium"), e(f'{c.get("duration_min") or "—"} min'), e(", ".join(c.get("areas") or []))] for c in chs]
    body.append(section("Sessions", table(["Charter", "Mission", "Priority", "Duration", "Areas"], rows), "one session = one charter, with a fixed time"))
    sheets = []
    for c in chs:
        sheets.append(f'''<div class="sheet" id="{e(c["id"])}"><h3>{e(c["id"])} {level_badge(c.get("priority") or "Medium")}
          {_pill(f'{c.get("duration_min") or "—"} min', SERIES[2], "◷")}</h3>
          <div class="mission">{e(c.get("mission"))}</div>
          <div class="grid2"><div><div class="lbl">Areas to explore</div>{_list(c.get("areas"))}</div>
          <div><div class="lbl">Risks</div>{_list(c.get("risks"))}</div>
          <div><div class="lbl">Heuristics and techniques</div>{_list(c.get("heuristics"))}</div>
          <div><div class="lbl">Test data</div>{_list(c.get("data"))}</div>
          <div><div class="lbl">Ideas to start with</div>{_list(c.get("ideas"))}</div>
          <div><div class="lbl">Out of scope</div>{_list(c.get("out_of_scope"))}</div></div>
          {f'<div class="lbl">Open questions</div>{_list(c.get("questions"))}' if c.get("questions") else ""}
          <div class="notes">Session notes (in <span class="mono">sessions/{e(c["id"])}.md</span>): BUG: · QUESTION: · IDEA: · RISK: · COVERED: · NOT COVERED: · NOTE:<br>
          Time: setup __ · testing __ · bugs __ (min)</div></div>''')
    body.append(section("Session sheets", "".join(sheets), "to print or share with whoever explores"))
    m = meta([("Story", data.get("story")), ("Date", (data.get("date") or "")[:10])])
    return page("Exploration charters", "Session-based exploratory testing", m, CSS_CH + "".join(body))


def md_sheets(data):
    parts = [f'# Exploration charters — {data.get("story") or ""} {data.get("title") or ""}'.strip(), ""]
    if data.get("goal"):
        parts += [f'**Goal:** {data["goal"]}', ""]
    for c in data.get("charters") or []:
        parts += [f'## {c["id"]} · {c.get("priority") or "Medium"} · {c.get("duration_min") or "—"} min', "", f'**Mission:** {c.get("mission")}', ""]
        for title, k in (("Areas", "areas"), ("Risks", "risks"), ("Heuristics", "heuristics"), ("Data", "data"), ("Ideas", "ideas"),
                         ("Out of scope", "out_of_scope"), ("Questions", "questions")):
            if c.get(k):
                parts += [f"**{title}:**", ""] + [f"- {x}" for x in c[k]] + [""]
    return "\n".join(parts) + "\n"


def notes_template(c):
    return (f'Charter: {c["id"]}\nTester: \nDate: {datetime.date.today().isoformat()}\nDuration: {c.get("duration_min") or 60}\n'
            f'Time: setup 0, testing 0, bugs 0\n\n# Mission: {c.get("mission")}\n# One line per item, with its prefix:\n'
            '# BUG: what happened [High]   QUESTION:   IDEA:   RISK:   COVERED: area   NOT COVERED: area   NOTE:\n\n')


def read_notes(file):
    s = {"file": file.name, "bugs": [], "questions": [], "ideas": [], "risks": [], "covered": [], "uncovered": [], "notes": []}
    for l in file.read_text(encoding="utf-8").splitlines():
        l = l.strip()
        if not l or l.startswith("#"):
            continue
        m = re.match(r"^(Charter|Tester|Date|Duration|Time)\s*:\s*(.*)$", l, re.I)
        if m:
            k, v = m.group(1).lower(), m.group(2).strip()
            if k == "time":
                for part in re.split(r"[,·;]", v):
                    mm = re.match(r"\s*(setup|testing|bugs?)\s*(\d+)", part, re.I)
                    if mm:
                        name = mm.group(1).lower()
                        key = "t_setup" if name.startswith("setup") else "t_bugs" if name.startswith("bug") else "t_testing"
                        s[key] = int(mm.group(2))
            elif k == "duration":
                s["duration"] = int(re.sub(r"\D", "", v) or 0) or None
            else:
                s[k] = v
            continue
        m = re.match(r"^(BUG|QUESTION|IDEA|RISK|COVERED|NOT COVERED|NOTE)\s*:\s*(.+)$", l, re.I)
        if m:
            k = LABELS[m.group(1).upper()]
            text = m.group(2).strip()
            if k == "bugs":
                sev = re.search(r"\[(Critical|High|Medium|Low)\]\s*$", text, re.I)
                s["bugs"].append({"text": re.sub(r"\s*\[[^\]]+\]\s*$", "", text), "severity": (sev.group(1).capitalize() if sev else "Medium")})
            else:
                s[k].append(text)
    return s


def html_report(data, sessions, hist_html=""):
    chs = {c["id"]: c for c in data.get("charters") or []}
    done = [s for s in sessions if s.get("charter")]
    bugs = [dict(b, charter=s["charter"]) for s in done for b in s["bugs"]]
    minutes = sum(s.get("duration") or 0 for s in done)
    planned_areas = {(cid, a) for cid, c in chs.items() for a in c.get("areas") or []}
    covered = {(s["charter"], a) for s in done for a in s["covered"]}
    coverage = round(len(covered & planned_areas) / len(planned_areas) * 100) if planned_areas else None
    high = [b for b in bugs if b["severity"] in ("Critical", "High")]
    body = [banner(f'{len(done)} of {len(chs)} session(s) done · {len(bugs)} bug(s), {len(high)} important',
                   "bad" if high else "warn" if bugs or len(done) < len(chs) else "ok"),
            '<div style="margin-top:20px">' + kpi_tiles([
                ("Sessions", f"{len(done)}/{len(chs)}", "ok" if len(done) >= len(chs) else "warn", "done out of the planned ones", "list", {"pct": len(done) / len(chs) * 100 if chs else 0}),
                ("Exploration time", f"{minutes} min", "", "sum of the sessions", "clock"),
                ("Bugs", len(bugs), "bad" if high else ("warn" if bugs else "ok"), f"{len(high)} of high or critical severity", "bug"),
                ("Questions", sum(len(s["questions"]) for s in done), "warn" if any(s["questions"] for s in done) else "", "for the PO or the team", "search"),
                ("New risks", sum(len(s["risks"]) for s in done), "", "that came up in the sessions", "warn"),
                ("Areas covered", f"{coverage} %" if coverage is not None else "—", "" if coverage is None else ("ok" if coverage >= 80 else "warn"),
                 "of the areas planned in the charters", "target", {"pct": coverage or 0}),
            ]) + "</div>"]
    tbs = [(s["charter"], [s.get("t_setup") or 0, s.get("t_testing") or 0, s.get("t_bugs") or 0]) for s in done]
    if any(sum(v) for _, v in tbs):
        body.append(two_col(section("Where the time went", stacked_bars(tbs, [("Setup", SERIES[0]), ("Testing", SERIES[1]), ("Bugs", SERIES[7])]),
                                    "TBS split: a lot of setup or a lot of time on bugs reduces exploration"),
                            section("Bugs per session", bar_chart([(s["charter"], len(s["bugs"]), SERIES[7]) for s in done], label_width=80))))
    if bugs:
        rows = [[level_badge(b["severity"]), f'<strong style="color:var(--ink)">{e(b["text"])}</strong>', e(b["charter"])] for b in bugs]
        body.append(section("Bugs found", table(["Severity", "Bug", "Session"], rows), "write them up with the bug-report-generator"))
    questions = [(p, s["charter"]) for s in done for p in s["questions"]]
    if questions:
        body.append(section("Open questions", table(["Question", "Session"], [[e(p), e(c)] for p, c in questions])))
    rows = []
    for cid, c in chs.items():
        s = next((x for x in done if x["charter"] == cid), None)
        status = _pill("Done", OK, "✓") if s else _pill("Pending", WARNING, "◷")
        cov = ", ".join(s["covered"]) if s else "—"
        unc = ", ".join(s["uncovered"]) if s else ", ".join(c.get("areas") or [])
        rows.append([f'<strong style="color:var(--ink)">{e(cid)}</strong>', e(c.get("mission")), status, e(s.get("tester", "—") if s else "—"),
                     e(cov or "—"), e(unc or "—"), e(f'{s.get("duration") or "—"} min' if s else "—")])
    body.append(section("Each charter", table(["Charter", "Mission", "Status", "Tester", "Covered", "Not covered", "Duration"], rows)))
    for title, k in (("Ideas for upcoming sessions", "ideas"), ("Risks that came up", "risks"), ("Notes", "notes")):
        xs = [f'{x} ({s["charter"]})' for s in done for x in s[k]]
        if xs:
            body.append(section(title, doc_list(xs)))
    if hist_html:
        body.append(hist_html)
    m = meta([("Story", data.get("story")), ("Date", datetime.date.today().isoformat())])
    return page("Sessions report", "Session-based exploratory testing", m, CSS_CH + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Exploratory testing charters and sessions")
    ap.add_argument("--name", required=True, help="folder: output/charters/<name>/ (for example, US-001)")
    ap.add_argument("--report", action="store_true", help="builds the report from the notes in sessions/")
    ap.add_argument("--output")
    a = ap.parse_args()
    folder = Path(a.output) if a.output else ROOT / "output" / "charters" / a.name
    file = folder / "charters.json"
    if not file.exists():
        sys.exit(f"{file} does not exist: the agent has to write the charters first.")
    data = json.loads(file.read_text(encoding="utf-8"))
    sessions_dir = folder / "sessions"
    if not a.report:
        data.setdefault("date", datetime.datetime.now().isoformat(timespec="seconds"))
        (folder / "charters.html").write_text(html_sheets(data), encoding="utf-8")
        (folder / "charters.md").write_text(md_sheets(data), encoding="utf-8")
        sessions_dir.mkdir(exist_ok=True)
        for c in data.get("charters") or []:
            notes = sessions_dir / f'{c["id"]}.md'
            if not notes.exists():  # never overwrites notes already written
                notes.write_text(notes_template(c), encoding="utf-8")
        print(f'{len(data.get("charters") or [])} charter(s) · {folder / "charters.html"} · notes in {sessions_dir}')
        return
    sessions = [read_notes(f) for f in sorted(sessions_dir.glob("*.md"))]
    sessions = [s for s in sessions if s.get("charter") and (s["bugs"] or s["covered"] or s["notes"] or s["questions"] or s["ideas"] or s.get("tester"))]
    now = datetime.datetime.now()
    summary = {"sessions": len(sessions), "charters": len(data.get("charters") or []), "bugs": sum(len(s["bugs"]) for s in sessions),
               "questions": sum(len(s["questions"]) for s in sessions), "minutes": sum(s.get("duration") or 0 for s in sessions)}
    result = {"story": data.get("story"), "date": now.isoformat(timespec="seconds"), "stamp": now.strftime("%Y%m%d-%H%M%S"),
              "summary": summary, "sessions": sessions, "findings": [dict(b, charter=s["charter"]) for s in sessions for b in s["bugs"]]}
    _history.archive(folder, ["sessions.json", "sessions-report.html"], "sessions.json")
    (folder / "sessions.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    hist = _history.section("charters", folder, result)
    (folder / "sessions-report.html").write_text(html_report(data, sessions, hist), encoding="utf-8")
    print(f'Sessions: {summary["sessions"]}/{summary["charters"]} · bugs: {summary["bugs"]} · questions: {summary["questions"]} · {summary["minutes"]} min')
    print(f'OK: {folder / "sessions-report.html"}')


if __name__ == "__main__":
    main()
