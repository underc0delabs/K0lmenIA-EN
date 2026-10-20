#!/usr/bin/env python3
"""
Search for duplicate and related bugs (bug-triager agent).

Usage (from the repo root):
    python scripts/find_duplicates.py --bug output/bug-reports/BUG-008.md [--candidates candidates.json]
                                        [--name BUG-008] [--no-local] [--max 10]
                                        [--duplicate-threshold 0.55] [--related-threshold 0.30]
    python scripts/find_duplicates.py --batch output/bug-reports [--candidates candidates.json] --name sprint-5

Compares a bug (or each bug in a folder, with --batch) against:
  - the local bugs in output/bug-reports/ and input/bugs/ (unless --no-local), and
  - the candidates the agent brought from Jira, Azure DevOps, GitHub or GitLab (--candidates).

The similarity uses the same concepts as the case selection (scripts/select_cases.py: English and
Spanish, synonyms, without accents or stopwords). The title weighs double; the same story, the
same screen ([Screen] in the title) and the same quoted error message add to it. Each candidate ends up
as "Probable duplicate", "Related" or "Different". A probable duplicate that is already closed or
resolved is flagged as a "possible regression".

Format of --candidates (JSON list; only "id" and "title" are required):
    [{"id": "PROJ-120", "title": "...", "description": "...", "status": "Open", "source": "jira",
      "url": "https://...", "story": "PROJ-12", "component": "Payments", "created": "2026-09-30"}]

Output in output/triage/<name>/: triage.json (the data) and triage.md (aligned tables).
"""
import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from select_cases import tokens  # noqa: E402  (same normalization and synonyms)

DUPLICATE, RELATED, DIFFERENT = "Probable duplicate", "Related", "Different"
CLOSED = {"closed", "resolved", "done", "fixed", "rejected", "removed", "won't fix", "finished", "complete", "completed",
          "cerrado", "cerrada", "resuelto", "resuelta", "hecho", "listo", "finalizado", "finalizada", "rechazado"}
RE_FIELD = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
RE_SCREEN = re.compile(r"^\s*\[([^\]]+)\]")
RE_QUOTE = re.compile(r"[\"“«']([^\"”»']{6,})[\"”»']")
RE_STORY = re.compile(r"\b(?:US|[A-Z][A-Z0-9]{1,9})-\d+\b")


# ------------------------------------------------------------------ reading
def read_bug_md(text, ident=""):
    """Fields of a bug report in a vertical block (the repo template) or of a loose note."""
    fields, current = {}, None
    for line in text.splitlines():
        m = RE_FIELD.match(line.strip())
        if m:
            current = m.group(1).strip().lower()
            fields[current] = m.group(2).strip()
        elif current:
            fields[current] += "\n" + line
    clean = lambda v: re.sub(r"`", "", (v or "")).strip()
    title = clean(fields.get("title"))
    if not title:  # loose note: first line with text
        title = next((l.strip("# ").strip() for l in text.splitlines() if l.strip()), "")
    body_keys = ("description", "steps to reproduce", "actual result", "expected result", "preconditions")
    body = "\n".join(clean(fields.get(k)) for k in body_keys if fields.get(k)) or text
    story = RE_STORY.search(clean(fields.get("story")) or "")
    return {
        "id": clean(fields.get("id")).split()[0] if fields.get("id") else ident,
        "title": title,
        "description": body,
        "actual_result": clean(fields.get("actual result")),
        "story": story.group(0) if story else "",
        "status": clean(fields.get("status")).split(" ")[0] if fields.get("status") else "",
        "source": "local",
    }


def read_bug(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        data.setdefault("id", path.stem)
        data.setdefault("source", "local")
        return data
    bug = read_bug_md(text, path.stem)
    bug["file"] = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)
    return bug


def local_bugs(exclude=()):
    exclude = {Path(e).resolve() for e in exclude}
    out = []
    for folder in (ROOT / "output" / "bug-reports", ROOT / "input" / "bugs"):
        for path in sorted(folder.glob("*.md")) if folder.exists() else []:
            if path.resolve() not in exclude and not path.name.startswith("_"):
                out.append(read_bug(path))
    return out


# ------------------------------------------------------------------ similarity
def _vector(bug):
    v = Counter(tokens(bug.get("title", "")) * 2)
    v.update(tokens(bug.get("description", "")))
    v.update(tokens(bug.get("actual_result", "")))
    return v


def _cosine(a, b):
    common = set(a) & set(b)
    if not common:
        return 0.0
    num = sum(a[t] * b[t] for t in common)
    return num / (math.sqrt(sum(x * x for x in a.values())) * math.sqrt(sum(x * x for x in b.values())))


def _quotes(bug):
    text = " ".join(str(bug.get(k, "")) for k in ("title", "description", "actual_result"))
    return {c.strip().lower() for c in RE_QUOTE.findall(text)}


def _screen(bug):
    m = RE_SCREEN.match(bug.get("title", ""))
    return m.group(1).strip().lower() if m else ""


def similarity(bug, cand):
    """(score 0..1, reasons) between two bugs."""
    va, vb = _vector(bug), _vector(cand)
    base = _cosine(va, vb)
    reasons = []
    common = sorted(set(va) & set(vb), key=lambda t: -(va[t] + vb[t]))[:6]
    if common:
        reasons.append("concepts in common: " + ", ".join(common))
    extra = 0.0
    if bug.get("story") and bug.get("story") == cand.get("story"):
        extra += 0.10
        reasons.append(f"same story ({bug['story']})")
    if _screen(bug) and _screen(bug) == _screen(cand):
        extra += 0.10
        reasons.append(f"same screen ([{_screen(bug)}])")
    quotes = _quotes(bug) & _quotes(cand)
    if quotes:
        extra += 0.15
        reasons.append(f"same message: \"{sorted(quotes)[0]}\"")
    return round(min(1.0, base + extra), 3), reasons


def classify(score, dup_threshold, rel_threshold):
    return DUPLICATE if score >= dup_threshold else RELATED if score >= rel_threshold else DIFFERENT


def compare(bug, candidates, dup_threshold=0.55, rel_threshold=0.30, maximum=10):
    result = []
    own = {str(bug.get("id", "")).lower(), str(bug.get("file", "")).lower()} - {""}
    for c in candidates:
        if str(c.get("id", "")).lower() in own or str(c.get("file", "")).lower() in own:
            continue
        score, reasons = similarity(bug, c)
        cls = classify(score, dup_threshold, rel_threshold)
        closed = str(c.get("status", "")).strip().lower() in CLOSED
        result.append({
            "id": c.get("id", ""), "title": c.get("title", ""), "source": c.get("source", ""),
            "status": c.get("status", ""), "url": c.get("url", c.get("file", "")), "story": c.get("story", ""),
            "component": c.get("component", ""), "score": score, "classification": cls,
            "possible_regression": cls == DUPLICATE and closed, "reasons": reasons,
        })
    result.sort(key=lambda r: -r["score"])
    return [r for r in result if r["classification"] != DIFFERENT][:maximum] + \
        [r for r in result if r["classification"] == DIFFERENT][: max(0, min(3, maximum))]


def verdict(matches):
    dup = [c for c in matches if c["classification"] == DUPLICATE]
    if any(c["possible_regression"] for c in dup):
        return "Possible regression of a closed bug"
    if dup:
        return "Probable duplicate"
    if any(c["classification"] == RELATED for c in matches):
        return "New, with related bugs"
    return "New"


# ------------------------------------------------------------------ output
def to_markdown(data):
    l = [f"# Bug triage — {data['name']}", "",
         f"Thresholds: probable duplicate from {data['thresholds']['duplicate']}, related from "
         f"{data['thresholds']['related']}. Candidates reviewed: {data['reviewed_candidates']}.",
         "The score is a heuristic: the agent confirms each duplicate by reading both bugs.", ""]
    for b in data["bugs"]:
        l += [f"## {b['id'] or 'Bug'} — {b['title']}", "", f"**Verdict:** {b['verdict']}", ""]
        if not b["matches"]:
            l += ["No candidates to compare.", ""]
            continue
        l += ["| Candidate | Source | Status | Score | Classification | Reasons |", "|---|---|---|---|---|---|"]
        for c in b["matches"]:
            cls = c["classification"] + (" (possible regression)" if c["possible_regression"] else "")
            row = [f"{c['id']} {c['title']}".strip(), c["source"] or "-", c["status"] or "-", f"{c['score']:.2f}",
                   cls, "; ".join(c["reasons"]) or "-"]
            l.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in row) + " |")
        l.append("")
    return "\n".join(l)


def write(data, folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "triage.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    md = folder / "triage.md"
    md.write_text(to_markdown(data), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "format_tables.py"), str(md)], capture_output=True, text=True)
    if r.returncode != 0:
        print("Warning: could not align the tables of triage.md (run scripts/format_tables.py by hand).")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Duplicate and related bugs")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bug", help="the bug to triage (template .md, loose note or .json)")
    g.add_argument("--batch", help="folder with several bugs: compares each one against the rest and the candidates")
    ap.add_argument("--candidates", help="JSON with the bugs the agent brought from Jira, Azure DevOps, GitHub or GitLab")
    ap.add_argument("--name", help="output folder in output/triage/ (by default, the bug ID or the batch name)")
    ap.add_argument("--no-local", action="store_true", help="do not compare against output/bug-reports/ and input/bugs/")
    ap.add_argument("--max", type=int, default=10, help="matches per bug (10)")
    ap.add_argument("--duplicate-threshold", type=float, default=0.55)
    ap.add_argument("--related-threshold", type=float, default=0.30)
    ap.add_argument("--output", help="output folder (by default output/triage/<name>)")
    a = ap.parse_args(argv)
    if not 0 < a.related_threshold < a.duplicate_threshold <= 1:
        ap.error("the thresholds must satisfy 0 < related < duplicate <= 1")

    candidates = []
    if a.candidates:
        candidates = json.loads(Path(a.candidates).read_text(encoding="utf-8-sig"))
        if not isinstance(candidates, list):
            ap.error("--candidates must be a JSON list")
    if a.batch:
        folder = Path(a.batch)
        paths = sorted(p for p in folder.glob("*") if p.suffix.lower() in (".md", ".json") and not p.name.startswith("_"))
        bugs = [read_bug(p) for p in paths]
        local = [] if a.no_local else local_bugs(exclude=paths)
        name = a.name or folder.name
    else:
        bug = read_bug(a.bug)
        bugs = [bug]
        local = [] if a.no_local else local_bugs(exclude=[a.bug])
        name = a.name or bug.get("id") or Path(a.bug).stem
    if not re.fullmatch(r"[\w.-]+", name):
        ap.error(f"invalid --name: {name!r} (only letters, numbers, hyphens and dots)")

    result = []
    for b in bugs:
        pool = candidates + local + [x for x in bugs if x is not b]
        matches = compare(b, pool, a.duplicate_threshold, a.related_threshold, a.max)
        result.append({"id": b.get("id", ""), "title": b.get("title", ""), "story": b.get("story", ""),
                       "verdict": verdict(matches), "matches": matches})
    data = {"name": name, "thresholds": {"duplicate": a.duplicate_threshold, "related": a.related_threshold},
            "reviewed_candidates": len(candidates) + len(local) + (len(bugs) - 1 if len(bugs) > 1 else 0),
            "bugs": result}
    folder = Path(a.output) if a.output else ROOT / "output" / "triage" / name
    write(data, folder)
    for b in result:
        top = b["matches"][0] if b["matches"] else None
        extra = f" · most similar: {top['id']} ({top['score']:.2f}, {top['classification']})" if top else ""
        print(f"{b['id'] or b['title'][:40]}: {b['verdict']}{extra}")
    print(f"Triage: {folder / 'triage.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
