#!/usr/bin/env python3
"""
Generates the Role permissions report in HTML (dashboard, dark mode) from permissions.json
(npm run permissions) and, optionally, from the permissions-tester agent's analysis.

Usage:
    python scripts/generate_permissions_report.py <permissions.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (roles, paths, allowed and denied visits, differences from what was
expected, findings), the role × path matrix (and role × endpoint), the differences against what was expected, the
findings, what each role sees (menus and buttons), the missing information, the recommendations and the evolution
of the runs.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "bad", "summary": "...",
  "expected": {"admin": {"/admin": "allowed", "/reports*": "allowed"}, "anonymous": {"/admin": "denied"}},
  "expected_source": "input/documentation/project/statuses-and-permissions.md (src/auth/roles.ts:12)",
  "findings": {"P-01": {"severity": "High", "note": "..."}},
  "discarded": [{"id": "P-04", "reason": "..."}],
  "additional": [{"severity": "Medium", "type": "Button", "title": "...", "detail": "...", "fix": "...", "role": "operator", "url": "...",
                  "screenshot": "screenshots/manual/pm-01.png"}],
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],   // "description" works as an alias of what_is_missing
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
In "expected", each route is the path (with * at the end for a prefix) and the value is "allowed" or
"denied" ("requires-login" also works). Whatever is not in "expected" is not compared: it is Missing information.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import _history
from _report_styles import (missing_info, warn_analysis, e, page, meta, section, kpi_tiles, banner, doc_list, table, bar_chart, two_col,
                            level_badge, _pill, thumbnail, CRITICAL, WARNING, NEUTRAL, OK, SERIES)
from generate_exploratory_report import CSS_EXTRA

SEV = ["Critical", "High", "Medium", "Low"]
DENIED = {"denied", "requires-login"}
ACCESS = {"allowed": ("Allowed", OK, "✓"), "denied": ("Denied", NEUTRAL, "⛔"), "requires-login": ("Requires login", NEUTRAL, "🔒"),
          "not-found": ("Not found", WARNING, "?"), "error": ("Error", CRITICAL, "✕")}

# Type for the run history (registered here so _history.py does not need to change).
_history.TYPES.setdefault("permissions", {
    "file": "permissions.json", "items": lambda d: d.get("findings") or [],
    "key": lambda h: f'{h.get("type")}|{h.get("role")}|{h.get("url")}', "title": lambda h: f'[{h.get("role")}] {h.get("title")}',
    "metrics": [("Findings", _history._r("findings"), ""), ("Critical", _history._r("by_severity", "Critical"), ""),
                ("Allowed visits", _history._r("allowed"), ""), ("Paths", _history._r("paths"), "")]})

CSS_PERM = """
<style>
.matrix td,.matrix th{text-align:center;white-space:nowrap}
.matrix td:first-child,.matrix th:first-child{text-align:left;white-space:normal}
.role h3{font-size:15px;color:var(--ink);margin:0 0 8px}
.role{border-top:1px solid var(--border-soft);padding:16px 24px}
.role:first-child{border-top:0}
.chips span{display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border-radius:999px;background:var(--bg);border:1px solid var(--border);font-size:12px}
.discarded{opacity:.55}
</style>
"""


def path_of(url):
    p = urlparse(url or "")
    return (p.path or "/") + (f"?{p.query}" if p.query else "") if p.scheme else (url or "")


def matches(pattern, url):
    r = path_of(url)
    pattern = path_of(pattern) if pattern.startswith("http") else pattern
    return r.startswith(pattern[:-1]) if pattern.endswith("*") else r.rstrip("/") == pattern.rstrip("/") or (r == "/" and pattern == "/")


def expected_for(expected, role, url):
    """What is expected for a role and a path (the longest matching pattern), or None."""
    rules = (expected or {}).get(role) or {}
    cand = sorted((p for p in rules if matches(p, url)), key=len, reverse=True)
    return rules[cand[0]] if cand else None


def differences(data, expected):
    """E-XX findings: where the matrix does not match what was expected."""
    out = []
    for c in data.get("matrix") or []:
        exp = expected_for(expected, c["role"], c["url"])
        if not exp or c.get("access") in ("error", "not-found"):
            continue
        real = c.get("access")
        if exp == "allowed" and real in DENIED:
            out.append({"severity": "High", "type": "Different from expected", "role": c["role"], "url": c["url"],
                        "title": f'The role "{c["role"]}" cannot get into something it should',
                        "detail": f'{path_of(c["url"])}: allowed was expected and it {"requires login" if real == "requires-login" else "denies access"}.'})
        elif exp in DENIED and real == "allowed":
            out.append({"severity": "Critical", "type": "Different from expected", "role": c["role"], "url": c["url"],
                        "title": f'The role "{c["role"]}" gets into something it should not',
                        "detail": f'{path_of(c["url"])}: {exp} was expected and it opens (status {c.get("status")}).'})
    out.sort(key=lambda h: SEV.index(h["severity"]))
    for i, h in enumerate(out, 1):
        h["id"] = f"E-{i:02d}"
    return out


def access_pill(acc):
    t, color, ic = ACCESS.get(acc or "", (acc or "—", NEUTRAL, "●"))
    return _pill(t, color, ic)


def build_html(data, analysis, hist_html=""):
    adjustments = analysis.get("findings") or {}
    desc = {str(d.get("id")): d.get("reason") for d in analysis.get("discarded") or []}
    expected = analysis.get("expected") or {}
    diffs = differences(data, expected)
    extra = [dict(h, id=h.get("id") or f"M-{i:02d}") for i, h in enumerate(analysis.get("additional") or [], 1)]
    findings = []
    for h in (data.get("findings") or []) + diffs + extra:
        h = dict(h)
        a = adjustments.get(h.get("id")) or {}
        if a.get("severity") in SEV:
            h["severity"] = a["severity"]
        h["_note"], h["_desc"] = a.get("note"), desc.get(h.get("id"))
        findings.append(h)
    findings.sort(key=lambda h: SEV.index(h["severity"]) if h.get("severity") in SEV else 9)
    live = [h for h in findings if not h["_desc"]]
    r = data.get("summary") or {}
    roles = data.get("roles") or []
    paths = data.get("paths") or []
    matrix = {(c["role"], c["url"]): c for c in data.get("matrix") or []}
    active = [x for x in roles if not x.get("authenticated") or x.get("login_ok")]
    critical = [h for h in live if h["severity"] == "Critical"]
    no_login = [x for x in roles if x.get("authenticated") and not x.get("login_ok")]
    if not paths:
        tone, text = "warn", "No paths were found to test"
    elif critical:
        tone, text = "bad", f"{len(critical)} critical problem(s): there are accesses that should not be allowed"
    elif live:
        tone, text = "warn", "There are no critical accesses, but there are differences to review"
    else:
        tone, text = "ok", "Each role sees and accesses what it should according to what was reviewed"
    if no_login and tone == "ok":
        tone, text = "warn", f"Could not test with {len(no_login)} role(s): check their credentials"
    body = [banner(analysis.get("verdict") or text, analysis.get("verdict_tone") or tone)]
    denied = r.get("denied", 0) + r.get("require_login", 0)
    body.append('<div style="margin-top:20px">' + kpi_tiles([
        ("Roles", r.get("roles", len(roles)), "warn" if no_login else "", f'{len(active)} tested, including anonymous', "person"),
        ("Paths", r.get("paths", len(paths)), "", f'{r.get("visits", 0)} role × path visits', "target"),
        ("Allowed", r.get("allowed", 0), "", "the page opened", "page"),
        ("Denied", denied, "", "access denied or requires login", "key"),
        ("Different from expected", len(diffs), "bad" if diffs else ("ok" if expected else ""), "compared against the documented rule" if expected else "no expected rule (see Missing information)", "warn"),
        ("Findings", len(live), "bad" if critical else ("warn" if live else "ok"), f"{len(critical)} critical", "bug"),
    ]) + "</div>")
    if analysis.get("summary"):
        body.append(section("Executive summary", f'<div class="cardbody"><p class="lead">{e(analysis["summary"])}</p></div>'))
    by_sev = [(s, sum(1 for h in live if h["severity"] == s), c) for s, c in zip(SEV, [CRITICAL, WARNING, SERIES[2], NEUTRAL])]
    by_role = [(x["id"], sum(1 for c in (data.get("matrix") or []) if c["role"] == x["id"] and c.get("access") == "allowed"), SERIES[i % len(SERIES)])
               for i, x in enumerate(active)]
    body.append(two_col(section("Findings by severity", bar_chart(by_sev, label_width=90) if live else '<p class="muted" style="padding:16px 24px">No findings.</p>'),
                        section("Paths each role opens", bar_chart(by_role, label_width=120) if by_role else '<p class="muted" style="padding:16px 24px">—</p>')))

    # Role × path matrix
    if paths and active:
        rows = []
        for ru in paths:
            cells = [f'<span class="mono">{e(ru.get("path") or path_of(ru["url"]))}</span>'
                     + (f'<div class="muted">in the navigation of: {e(", ".join(ru.get("discovered_by") or []) or "—")}</div>')]
            for x in active:
                c = matrix.get((x["id"], ru["url"]))
                if not c:
                    cells.append('<span class="muted">—</span>')
                    continue
                exp = expected_for(expected, x["id"], ru["url"])
                mark = ""
                if exp:
                    ok = (exp == "allowed") == (c.get("access") == "allowed")
                    mark = f'<div class="muted">expected: {e(exp)} {"✓" if ok else "✕"}</div>'
                cells.append(access_pill(c.get("access")) + f'<div class="muted mono">{e(c.get("status"))}</div>' + mark)
            rows.append(cells)
        body.append(section("Access matrix by role", f'<div class="matrix">{table(["Path"] + [x["id"] for x in active], rows)}</div>',
                            "each role opens each path by typing the URL, even if it doesn't see it in its menu"))
    eps = data.get("endpoints") or []
    if eps:
        rows = []
        for ep in eps:
            cells = [f'<span class="mono">{e(ep["method"])} {e(ep["path"])}</span>']
            for x in roles:
                res = (ep.get("results") or {}).get(x["id"])
                if not res:
                    cells.append('<span class="muted">—</span>')
                    continue
                st = res.get("status") or 0
                color = OK if 200 <= st < 300 else NEUTRAL if st in (401, 403) else CRITICAL if st >= 500 or st == 0 else WARNING
                cells.append(_pill(str(st or "no response"), color, "●") + (' <span class="muted">token</span>' if res.get("with_token") else ""))
            rows.append(cells)
        body.append(section("Endpoints by role", f'<div class="matrix">{table(["Endpoint"] + [x["id"] for x in roles], rows)}</div>',
                            "status of each endpoint with each role's session and token (only GET, HEAD or OPTIONS)"))

    if findings:
        rows = []
        for h in findings:
            det = (f'<strong style="color:var(--ink)">{e(h.get("title"))}</strong><div class="muted">{e(h.get("detail"))}</div>'
                   + (f'<div><i>{e(h["_note"])}</i></div>' if h.get("_note") else "")
                   + (f'<div><b>How to fix it:</b> {e(h["fix"])}</div>' if h.get("fix") else "")
                   + (f'<div class="muted">Discarded: {e(h["_desc"])}</div>' if h.get("_desc") else ""))
            cap = h.get("screenshot") or (matrix.get((h.get("role"), h.get("url"))) or {}).get("screenshot")
            rows.append([e(h.get("id")), level_badge(h.get("severity")), e(h.get("type")), e(h.get("role") or "—"), det,
                         thumbnail(cap, f'{h.get("role")} · {path_of(h.get("url"))}') if cap else '<span class="muted">—</span>'])
        body.append(section("Findings", table(["ID", "Severity", "Type", "Role", "Finding", "Evidence"], rows)))

    # What each role sees
    blocks = []
    for x in roles:
        status = ("no session" if not x.get("authenticated") else "session started" if x.get("login_ok") else f'could not log in: {x.get("login_error") or ""}')
        cells = [c for (role, _), c in matrix.items() if role == x["id"] and c.get("access") == "allowed"]
        menus = sorted({m for c in cells for m in c.get("menus") or []})
        buttons = sorted({b for c in cells for b in c.get("buttons") or []})
        blocks.append(f'<div class="role"><h3>{e(x.get("name") or x["id"])} <span class="muted">· {e(status)}</span></h3>'
                      f'<div class="muted">Menus and links</div><div class="chips">{"".join(f"<span>{e(m)}</span>" for m in menus) or "—"}</div>'
                      f'<div class="muted" style="margin-top:8px">Buttons</div><div class="chips">{"".join(f"<span>{e(b)}</span>" for b in buttons) or "—"}</div></div>')
    if blocks:
        body.append(section("What each role sees", "".join(blocks), "menus, links and buttons visible on the pages that open for it"))

    mi = analysis.get("missing_info") or []
    if not expected and not mi:
        mi = [{"id": "—", "what_is_missing": "The expected permissions rule (which role can see what).",
               "question": "Where is the permissions matrix by role defined? Without it, the matrix describes how it works today, not whether it is right."}]
    body.append(missing_info(mi))
    if analysis.get("recommendations"):
        rows = [[f'<strong style="color:var(--ink)">{e(x.get("action"))}</strong>', e(x.get("reason")), level_badge(x.get("priority"))]
                for x in analysis["recommendations"]]
        body.append(section("Recommendations", table(["Action", "Why", "Priority"], rows)))
    if analysis.get("next_steps"):
        body.append(section("Next steps", doc_list(analysis["next_steps"])))
    if hist_html:
        body.append(hist_html)
    m = meta([("Story", data.get("story")), ("Site", data.get("host")), ("Date", (data.get("date") or "")[:16].replace("T", " ")),
              ("Expected", analysis.get("expected_source") or ("documented" if expected else "not defined"))])
    return page("Permissions", "Role permissions", m, CSS_EXTRA + CSS_PERM + "".join(body))


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="HTML role permissions report from permissions.json")
    ap.add_argument("data_json")
    ap.add_argument("output")
    ap.add_argument("--analysis")
    a = ap.parse_args()
    if not a.output.lower().endswith(".html"):
        sys.exit("The output must end in .html")
    with open(a.data_json, encoding="utf-8") as f:
        data = json.load(f)
    analysis = {}
    if a.analysis:
        with open(a.analysis, encoding="utf-8") as f:
            analysis = json.load(f)
        warn_analysis(analysis, [h.get("id") for h in data.get("findings") or []])
    hist_html = _history.section("permissions", Path(a.data_json).resolve().parent, data)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write(build_html(data, analysis, hist_html=hist_html))
    print(f"OK: {a.output}")


if __name__ == "__main__":
    main()
