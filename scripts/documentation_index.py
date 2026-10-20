#!/usr/bin/env python3
"""
Index of the project documentation (project-documenter agent).

Usage (from the repo root):
    python scripts/documentation_index.py [--folder input/documentation] [--days 30]

Walks input/documentation/ and builds input/documentation/INDEX.md: which documents there are, what they are about,
which sources they come from, when they were updated and whether they should be reviewed (older than --days). It is the
first thing the other agents read (context-research skill) to know what context exists without
opening every file.

Each .md written by the documenter carries a header (frontmatter) like this:

    ---
    title: Payment business rules
    type: project | repository | web | story | api | links
    story: US-001               (only in a story's dossiers)
    sources: github my-company/my-app (src/payments), PROJ-12
    updated: 2026-10-14
    ---

Files without a header (for example, a PDF or a .md added by a person) are also listed,
as "Added by hand", with the file's date.

Incremental documentation: if input/documentation/.status.json exists (scripts/documentation_changes.py),
the documents left outdated by a code change are shown as "Outdated"
with the commit they changed from, and changes.md (what changed and which cases to review) goes first.
"""
import json
import argparse
import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = "INDEX.md"
IGNORE = {INDEX, ".gitkeep"}
TYPE_ORDER = ["changes", "project", "repository", "api", "web", "story", "links"]
TYPE_NAME = {
    "changes": "Changes since the last documentation",
    "project": "Project",
    "repository": "Repository",
    "api": "API contracts",
    "web": "Web application",
    "story": "Stories",
    "links": "External links",
    "manual": "Added by hand",
}
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*(\n|\Z)", re.S)


def read_header(text):
    """{key: value} of the frontmatter (simple key: value format), or {} if it has none."""
    m = _FRONT.match(text.lstrip("﻿"))
    if not m:
        return {}
    data = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            data[key.strip().lower()] = value.strip()
    return data


def _date(text):
    try:
        return dt.date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def _md_title(text):
    for line in _FRONT.sub("", text.lstrip("﻿"), count=1).splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def documents(folder):
    """List of the folder's documents with their data, sorted by type and path."""
    docs = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        # The .json files with their .md next to them (the functional map) are the data of the same document.
        if path.name in IGNORE or path.name.startswith(("_", ".")) or (path.suffix == ".json" and path.with_suffix(".md").exists()):
            continue
        rel = path.relative_to(folder).as_posix()
        meta = {}
        if path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8", errors="replace")
            meta = read_header(text)
            meta.setdefault("title", _md_title(text))
        type_ = (meta.get("type") or "manual").lower()
        if type_ not in TYPE_NAME:
            type_ = "manual"
        date = _date(meta.get("updated", "")) or dt.date.fromtimestamp(path.stat().st_mtime)
        docs.append({
            "path": rel,
            "title": meta.get("title") or path.stem,
            "type": type_,
            "story": meta.get("story", ""),
            "sources": meta.get("sources", ""),
            "updated": date,
        })
    order = {t: i for i, t in enumerate(TYPE_ORDER + ["manual"])}
    return sorted(docs, key=lambda d: (order[d["type"]], d["story"], d["path"]))


def outdated(folder):
    """{document: "since <commit>"} of the documents marked by a code change (.status.json)."""
    try:
        status = json.loads((Path(folder) / ".status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {doc: f"since {str((info.get('outdated') or {}).get('since', '?'))[:10]}"
            for doc, info in (status.get("documents") or {}).items() if info.get("outdated")}


def build_index(docs, today, days, marked=None):
    marked = marked or {}
    lines = [
        "---",
        "title: Index of the project documentation",
        "type: index",
        f"updated: {today.isoformat()}",
        "---",
        "",
        "# Project documentation",
        "",
        "Project context for the agents (built by the `project-documenter`; regenerated with "
        "`python scripts/documentation_index.py`). Read this index first and open only what you need.",
        "What comes from the code or the application describes how it works **today**: it is context, it does not "
        "replace the story or the PO's decisions.",
        "",
    ]
    if not docs:
        lines += ["There is no documentation yet. Ask the `project-documenter` to build it.", ""]
        return "\n".join(lines)
    old = [d for d in docs if (today - d["updated"]).days > days]
    lines += [f"{len(docs)} document(s) · {len(old)} to review (more than {days} days without an update)"
              + (f" · {len(marked)} outdated by code changes (see `changes.md`)" if marked else "") + ".", ""]
    for type_ in TYPE_ORDER + ["manual"]:
        group = [d for d in docs if d["type"] == type_]
        if not group:
            continue
        lines += [f"## {TYPE_NAME[type_]}", ""]
        with_story = any(d["story"] for d in group)
        head = ["Document", "Title"] + (["Story"] if with_story else []) + ["Sources", "Updated", "Status"]
        lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for d in group:
            status = f"Outdated ({marked[d['path']]})" if d["path"] in marked else "Review" if d in old else "Current"
            row = [f"`{d['path']}`", d["title"]] + ([d["story"]] if with_story else []) + [
                d["sources"] or "-", d["updated"].isoformat(), status]
            lines.append("| " + " | ".join(str(c).replace("|", "/") for c in row) + " |")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Builds input/documentation/INDEX.md")
    ap.add_argument("--folder", default=str(ROOT / "input" / "documentation"))
    ap.add_argument("--days", type=int, default=30, help="days after which a document is marked for review")
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    folder.mkdir(parents=True, exist_ok=True)
    docs = documents(folder)
    target = folder / INDEX
    target.write_text(build_index(docs, dt.date.today(), a.days, outdated(folder)), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "format_tables.py"), str(target)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"Warning: could not align the tables ({r.stderr.strip().splitlines()[-1:] or ''}).")
    print(f"{len(docs)} document(s) in the index: {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
