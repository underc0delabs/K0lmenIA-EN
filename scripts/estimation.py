#!/usr/bin/env python3
"""
Estimate of the MANUAL run time of a test case (and of each step).

Use as a module:     from estimation import estimate_case      → {"minutes", "seconds", "text", "steps", ...}
Use from the console: python scripts/estimation.py <cases.xlsx|.feature> [--json]

The formula (details in templates/time-estimation.md):

    case time = (setup + Σ time of each step + logging) × case factor   → rounded up to 0.5 min

    step time = action time + data time + verification time
      - action: according to the step's verb (ACTIONS table): navigate 0.5 · click or select 0.25 · fill in 0.3 per field ·
        log in 1 · upload or download a file 1 · wait for an email, SMS or process 2 · query the database, an API or
        logs 2 · read or browse 0.5 · any other 0.5 (min)
      - data: 0.15 min for each extra piece of data in the step (beyond the fields already counted)
      - verification: 0.5 min if the step has an expected result (or is a Then), + 0.25 for each additional check (up to 4)
    setup   = 1 min (open the environment and read the case) + 0.5 per precondition (up to 3) + 2 if data or users must be created
    logging = 0.5 min (mark the result and save the evidence) + 0.1 per step
    factor  = 1.1 for negative or edge cases (they must be observed more carefully), 1 for the rest

It is an estimate for planning (not a measurement): teams can adjust the constants with
ESTIMATION_FACTOR (multiplies everything, for example 1.3 for someone who is new to the app).
"""
import json
import math
import os
import re
import sys
from pathlib import Path

# (category, pattern of the verb or phrase, minutes, multiplied by the number of fields)
ACTIONS = [
    ("Log in", r"\blog\s?in|\blogs in|\blogged in|\bsign\w* in\b|authenticat\w*|enter\w* (with )?(his|her|their|the|your) (user|account|credentials)", 1.0, False),
    ("Wait for an email, SMS or process", r"\bwait\w*|receiv\w* (an?|the) (email|e-mail|mail|sms|notification)|check\w* (the|his|her|their|your) (email|mail|inbox)|\binbox\b", 2.0, False),
    ("Query the database, an API or logs", r"query\w* (the|in the) (database|db)|\bdatabase\b|\bsql\b|\bapi\b|endpoint|postman|\blogs\b|\blog files?\b", 2.0, False),
    ("Upload or download a file", r"attach\w*|upload\w*|download\w*|export\w*|import\w*|print\w*", 1.0, False),
    ("Fill in fields", r"\bfill\w*|complet\w* (the|a|an|all|his|her|their|your)\b|\bwrit\w*|enter\w* (the|a|an|his|her|their|your)\b(?! (\w+ )?(page|site|section|menu|screen|module)\b)|\btyp\w*|\binput\w*|introduc\w*", 0.3, True),
    ("Navigate", r"\bgo(es)? (to|back)\b|navigat\w*|access\w*|\bopen\w*|visit\w*|enter\w* (the )?(\w+ )?(page|site|section|menu|screen|module)\b|\bis (on|in|at) the\b", 0.5, False),
    ("Click or select", r"click\w*|press\w*|\btap\w*|select\w*|choos\w*|\bcheck\w*|uncheck\w*|activat\w*|deactivat\w*|enabl\w*|disabl\w*|\bclos\w*|confirm\w*|accept\w*|cancel\w*|submit\w*|\bsend\w*|\bsav\w*", 0.25, False),
    ("Read or browse", r"scroll\w*|\bread\w*|review\w*|observ\w*|brows\w*|look\w* (at|through)", 0.5, False),
]
_ACT = [(c, re.compile(p, re.I), m, x) for c, p, m, x in ACTIONS]
NEGATIVE = re.compile(r"invalid|incorrect|wrong|erroneous|error|empty|blank|without (completing|filling|data)|limit|maxim|minim|edge|boundar|reject|block|expired|exceed|negative", re.I)
CREATE_DATA = re.compile(r"creat\w* (an?|the|some)? ?(user|account|customer|client|record|order|product|data)|sign\w* up|insert\w* (in|into) the database|loaded (in|into) the database|seed\w*", re.I)
FACTOR = float(os.environ.get("ESTIMATION_FACTOR", "1") or 1)


def _items(text):
    """Number of pieces of data in a text: lines or elements separated by a comma or semicolon."""
    text = str(text or "").strip()
    if not text:
        return 0
    parts = [p for p in re.split(r"[\n;]|,(?!\d)", text) if p.strip()]
    return len(parts)


def _verifications(result):
    result = str(result or "").strip()
    if not result:
        return 0
    return max(1, min(4, len([p for p in re.split(r"[\n;]|\.\s|\band\b(?= (the|a|an|it|is|are|shows|appears|no|not))", result) if p and p.strip()])))


def estimate_step(action, data="", result="", is_then=False):
    text = str(action or "")
    cat, minutes, by_field = "Other action", 0.5, False
    if re.match(r"\s*(go|navigat|access|open|visit)\w*\b", text, re.I):  # "Go to the login page" is navigating, not logging in
        cat, minutes = "Navigate", 0.5
    else:
        for c, rx, m, x in _ACT:
            if rx.search(text):
                cat, minutes, by_field = c, m, x
                break
    n_data = _items(data)
    if by_field:
        # Fields: the step's data or, if it has none, the ones it names ("the email, the name and the password" = 3).
        fields = max(1, n_data or len(re.split(r",|\band\b", text)))
        t_action = minutes * fields
        t_data = 0.15 * max(0, n_data - fields)
    else:
        t_action = minutes
        t_data = 0.15 * max(0, n_data - 1)
    nv = _verifications(result) or (1 if is_then else 0)
    t_verif = (0.5 + 0.25 * (nv - 1)) if nv else 0.0
    total = t_action + t_data + t_verif
    return {"category": cat, "action": round(t_action, 2), "data": round(t_data, 2), "verification": round(t_verif, 2),
            "minutes": round(total, 2), "seconds": int(round(total * 60))}


def _steps_of(case):
    """Steps of a manual case ({action, data, result}) or of a BDD scenario (gherkin)."""
    if case.get("steps"):
        steps = case["steps"]
        if isinstance(steps, str):  # "1. ...\n2. ..." (JSON of generate_cases.py)
            lines = [re.sub(r"^\s*\d+[.)-]\s*", "", l).strip() for l in steps.splitlines() if l.strip()]
            steps = [{"action": l, "data": "", "result": ""} for l in lines]
            if steps:
                steps[0]["data"] = case.get("data", "")
                steps[-1]["result"] = case.get("result", "")
        return [(p.get("action", ""), p.get("data", ""), p.get("result", ""), False) for p in steps]
    out = []
    last = None
    for l in str(case.get("gherkin") or "").splitlines():
        m = re.match(r"\s*(Given|When|Then|And|But|\*|Dado|Cuando|Entonces|Y|Pero)\s+(.*)", l)
        if not m:
            if l.strip().startswith("|") and out:  # data table of the previous step
                a, d, r, t = out[-1]
                out[-1] = (a, (d + "\n" + l).strip(), r, t)
            continue
        kw = m.group(1)
        if kw in ("And", "But", "*", "Y", "Pero") and last:
            kw = last
        last = kw
        out.append((m.group(2), "", "", kw in ("Then", "Entonces")))
    return out


def estimate_case(case):
    steps = [estimate_step(a, d, r, t) for a, d, r, t in _steps_of(case)]
    precond = str(case.get("preconditions") or "")
    n_pre = min(3, _items(precond))
    prep = 1.0 + 0.5 * n_pre + (2.0 if CREATE_DATA.search(precond) else 0.0)
    logging = 0.5 + 0.1 * len(steps)
    tags = case.get("tags") or []
    tags = tags if isinstance(tags, (list, tuple, set)) else [str(tags)]  # the JSON of generate_cases.py has a text
    case_text = " ".join(str(case.get(k) or "") for k in ("title", "description")) + " " + " ".join(str(x) for x in tags)
    factor = (1.1 if NEGATIVE.search(case_text) else 1.0) * FACTOR
    raw = (prep + sum(p["minutes"] for p in steps) + logging) * factor
    minutes = max(1.0, math.ceil(raw * 2) / 2)
    source = "formula"
    try:  # a time entered by hand in the spreadsheet ("Estimated Time (min)" column) wins
        manual = float(str(case.get("time_min")).replace(",", "."))
        if manual > 0:
            scale = manual / raw if raw else 1
            for p in steps:  # the steps are distributed proportionally
                p["minutes"] = round(p["minutes"] * scale, 2)
                p["seconds"] = int(round(p["minutes"] * 60))
            minutes, source = manual, "spreadsheet"
    except (TypeError, ValueError):
        pass
    return {"minutes": minutes, "seconds": int(minutes * 60), "text": format_time(minutes), "source": source, "steps": steps,
            "setup": round(prep, 2), "logging": round(logging, 2), "factor": round(factor, 2), "unrounded": round(raw, 2)}


def format_time(minutes):
    """6.5 → "6.5 min"; 75 → "1 h 15 min"."""
    if minutes is None:
        return "—"
    if minutes >= 60:
        h, m = divmod(int(round(minutes)), 60)
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{minutes:g} min"


def jira_duration(minutes):
    """Jira format for Original Estimate: "1h 15m", "7m"."""
    m = int(math.ceil(minutes))
    h, r = divmod(m, 60)
    return " ".join(x for x in (f"{h}h" if h else "", f"{r}m" if r else "") if x) or "1m"


def hhmm(minutes):
    m = int(math.ceil(minutes))
    return f"{m // 60:02d}:{m % 60:02d}"


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.path.insert(0, str(Path(__file__).resolve().parent / "management"))
    from readers import read_cases
    cases = read_cases(sys.argv[1])
    rows = [(c["id"], c["title"], estimate_case(c)) for c in cases]
    if "--json" in sys.argv:
        print(json.dumps([{"id": i, "title": t, **e} for i, t, e in rows], ensure_ascii=False, indent=2))
        return
    total = sum(e["minutes"] for _, _, e in rows)
    for i, t, e in rows:
        print(f"{i:10} {e['text']:>10}  {len(e['steps']):>2} steps  {t[:70]}")
    print(f"\n{len(rows)} case(s) · total {format_time(total)} of manual run time")


if __name__ == "__main__":
    main()
