#!/usr/bin/env python3
"""
Incremental documentation for the project-documenter: what was documented, from which commit, and what changed.

Saves the status in input/documentation/.status.json:
    repositories  per repo: provider, name, branch, documented commit and date
    documents     per document: which code files or folders fed it (sources), its
                  stories and modules, and whether it became outdated because of a code change
    stories       per story: change date of the story and of its PRs when it was documented, local
                  alias (US-XXX), modules and files it touches

Commands (from the repo root):
    python scripts/documentation_changes.py repo --provider github --name my-org/my-app --branch main --commit a1b2c3d
    python scripts/documentation_changes.py register --document project/business-rules.md
           --sources "src/payments/,src/**/validations*.ts" [--repo my-org/my-app] [--stories PROJ-12] [--modules payments]
    python scripts/documentation_changes.py story --key PROJ-12 [--us US-001] --story-change 2026-10-10T12:00
           [--prs-change 2026-10-11] [--modules payments] [--files src/payments/checkout.ts]
    python scripts/documentation_changes.py changes --repo my-org/my-app
           (--git <clone path> | --files a.ts,b.ts | --files-from list.txt) [--until <commit>] [--mark]

"changes" takes the files that changed since the documented commit (with --git it runs
`git diff --name-only <commit>..HEAD` in the clone; with the connector, the agent passes the list with --files
or --files-from) and writes input/documentation/changes.md with:
    - the affected documents (the ones to redo) and because of which file,
    - the affected stories,
    - the existing cases that may be outdated (output/test-cases/ and the .feature files of
      tools/k0lmena), to hand to the case-reviewer.
With --mark it leaves those documents as outdated in the status (the index shows them that way) until
they are registered again with "register". Prints the result as JSON.

The sources of a document are paths relative to the root of the app repository: a folder
(ending in "/"), a file or a pattern with * and ** (src/**/i18n/*.json).
"""
import argparse
import datetime as dt
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "input" / "documentation"
STATUS = ".status.json"
CHANGES = "changes.md"
_ID_US = re.compile(r"\b(US-\d+)\b")
_TAG_US = re.compile(r"@(US-\d+)\b")


# ------------------------------------------------------------------ status
def empty_state():
    return {"version": 1, "repositories": {}, "documents": {}, "stories": {}}


def read_state(folder=FOLDER):
    file = Path(folder) / STATUS
    if not file.exists():
        return empty_state()
    data = json.loads(file.read_text(encoding="utf-8"))
    base = empty_state()
    base.update(data)
    return base


def save_state(status, folder=FOLDER):
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / STATUS).write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _list(text):
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def _today():
    return dt.date.today().isoformat()


def register_repo(status, provider, name, branch, commit, date=None):
    status["repositories"][name] = {"provider": provider, "name": name, "branch": branch or "", "commit": commit,
                                    "date": date or _today()}
    return status


def register_document(status, document, sources, repo="", stories=(), modules=(), date=None):
    """Adds or updates a document: clears the outdated mark (it was just redone)."""
    status["documents"][document] = {"repo": repo, "sources": list(sources), "stories": list(stories),
                                     "modules": list(modules), "updated": date or _today()}
    return status


def register_story(status, key, us="", story_change="", prs_change="", modules=(), files=(), date=None):
    status["stories"][key] = {"us": us, "story_change": story_change, "prs_change": prs_change,
                              "modules": list(modules), "files": list(files), "documented": date or _today()}
    return status


# ------------------------------------------------------------------ matching
def _path(r):
    r = r.strip().replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def matches(file, source):
    """Is the changed file covered by the source (folder/, file or pattern with * and **)?"""
    file, source = _path(file), _path(source)
    if not source:
        return False
    if source.endswith("/"):
        return file.startswith(source)
    if any(c in source for c in "*?["):
        # ** crosses folders; fnmatch already makes * cross them too, so normalizing is enough.
        return fnmatch.fnmatchcase(file, source.replace("**/", "*")) or fnmatch.fnmatchcase(file, source)
    return file == source or file.startswith(source.rstrip("/") + "/")


def affected_documents(status, files, repo=""):
    """{document: [files that affect it]} for the documents of that repo (or without a repo)."""
    output = {}
    for doc, info in status["documents"].items():
        if repo and info.get("repo") and info["repo"] != repo:
            continue
        hits = [a for a in files if any(matches(a, f) for f in info.get("sources") or [])]
        if hits:
            output[doc] = hits
    return output


def affected_stories(status, files, docs):
    """Stories of the affected documents + the ones that touch any of the changed files."""
    hs = set()
    for doc in docs:
        hs.update(status["documents"].get(doc, {}).get("stories") or [])
    for key, info in status["stories"].items():
        if any(matches(a, f) for a in files for f in info.get("files") or []):
            hs.add(key)
    return sorted(hs)


def affected_modules(status, docs, stories):
    ms = set()
    for doc in docs:
        ms.update(status["documents"].get(doc, {}).get("modules") or [])
    for h in stories:
        ms.update(status["stories"].get(h, {}).get("modules") or [])
    return sorted(m for m in ms if m)


def case_inventory(root=ROOT):
    """Existing cases: [{file, stories (US-XXX), text}] from output/test-cases and the k0lmena .feature files."""
    files = []
    for base, pattern in (("output/test-cases", "**/*.md"), ("output/test-cases", "**/*.feature"),
                          ("output/test-cases", "**/*.xlsx"), ("tools/k0lmena", "*/features/**/*.feature")):
        folder = Path(root) / base
        if folder.exists():
            files += [p for p in folder.glob(pattern) if p.is_file() and not p.name.endswith("-coverage.md")]
    cases = []
    for p in sorted(set(files)):
        rel = p.relative_to(root).as_posix()
        text = "" if p.suffix == ".xlsx" else p.read_text(encoding="utf-8", errors="replace")
        uss = set(_ID_US.findall(p.name)) | set(_TAG_US.findall(text))
        cases.append({"file": rel, "stories": sorted(uss), "text": text[:20000].lower()})
    return cases


def affected_cases(status, stories, modules, cases):
    """Cases that touch an affected story (by its key or its US-XXX alias) or mention an affected module."""
    ids = set(stories) | {status["stories"].get(h, {}).get("us") for h in stories} - {None, ""}
    output = []
    for c in cases:
        by_story = sorted(ids & set(c["stories"]))
        by_module = [m for m in modules if re.search(r"\b" + re.escape(m.lower()) + r"\b", c["text"])]
        if by_story or by_module:
            reason = (f"story {', '.join(by_story)}" if by_story else "") + \
                     (" · " if by_story and by_module else "") + (f"module {', '.join(by_module)}" if by_module else "")
            output.append({"file": c["file"], "reason": reason})
    return output


def analyze(status, files, repo="", root=ROOT):
    docs = affected_documents(status, files, repo)
    hs = affected_stories(status, files, docs)
    ms = affected_modules(status, docs, hs)
    no_document = [a for a in files if not any(a in v for v in docs.values())]
    return {"repo": repo, "files": files, "documents": docs, "stories": hs, "modules": ms,
            "cases": affected_cases(status, hs, ms, case_inventory(root)), "no_document": no_document}


def mark(status, result, since, until):
    for doc, hits in result["documents"].items():
        status["documents"][doc]["outdated"] = {"since": since, "until": until, "files": hits[:50], "date": _today()}
    return status


# ------------------------------------------------------------------ changes.md
def build_changes_md(r, since, until):
    l = ["---", "title: Changes since the last documentation", "type: changes", f"sources: {r['repo'] or 'repository'} {since}..{until}",
         f"updated: {_today()}", "---", "", "# Changes since the last documentation", "",
         f"{len(r['files'])} file(s) changed in `{r['repo'] or 'the repository'}` between `{since}` and `{until}`.", ""]
    l += ["## Documents to redo", ""]
    if r["documents"]:
        l += ["| Document | Files that changed |", "|---|---|"]
        for doc, hits in sorted(r["documents"].items()):
            sample = ", ".join(f"`{h}`" for h in hits[:6]) + (f" and {len(hits) - 6} more" if len(hits) > 6 else "")
            l.append(f"| `{doc}` | {sample} |")
    else:
        l.append("No document depends on the changed files.")
    l += ["", "## Affected stories", "", ", ".join(r["stories"]) or "None.", ""]
    l += ["## Cases to review", ""]
    if r["cases"]:
        l += ["They may have become outdated because of these changes. Suggestion: hand them to the `case-reviewer`.", "",
              "| File | Why |", "|---|---|"] + [f"| `{c['file']}` | {c['reason']} |" for c in r["cases"]]
    else:
        l.append("There are no existing cases tied to the affected stories or modules.")
    if r["no_document"]:
        l += ["", "## Files that do not feed any document", "",
              "It may be new code to document (or code that does not affect testing):", ""]
        l += [f"- `{a}`" for a in r["no_document"][:40]]
        if len(r["no_document"]) > 40:
            l.append(f"- and {len(r['no_document']) - 40} more")
    return "\n".join(l) + "\n"


def files_from_git(path, since, until="HEAD"):
    r = subprocess.run(["git", "-C", str(path), "diff", "--name-only", f"{since}..{until}"], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git diff failed in {path}: {r.stderr.strip()}")
    return [x for x in r.stdout.splitlines() if x.strip()]


def _format(md):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "format_tables.py"), str(md)], capture_output=True, text=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Status and changes of the project documentation")
    ap.add_argument("--folder", default=str(FOLDER))
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("repo")
    p.add_argument("--provider", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--branch", default="")
    p.add_argument("--commit", required=True)
    p = sub.add_parser("register")
    p.add_argument("--document", required=True)
    p.add_argument("--sources", default="")
    p.add_argument("--repo", default="")
    p.add_argument("--stories", default="")
    p.add_argument("--modules", default="")
    p = sub.add_parser("story")
    p.add_argument("--key", required=True)
    p.add_argument("--us", default="")
    p.add_argument("--story-change", default="")
    p.add_argument("--prs-change", default="")
    p.add_argument("--modules", default="")
    p.add_argument("--files", default="")
    p = sub.add_parser("changes")
    p.add_argument("--repo", default="")
    p.add_argument("--git", help="path of the local clone (REPO_LOCAL_PATH)")
    p.add_argument("--files", default="")
    p.add_argument("--files-from")
    p.add_argument("--from", help="starting commit (by default, the documented one for the repo)")
    p.add_argument("--until", default="HEAD")
    p.add_argument("--mark", action="store_true")
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    status = read_state(folder)

    if a.command == "repo":
        save_state(register_repo(status, a.provider, a.name, a.branch, a.commit), folder)
        print(f"Repository {a.name} documented up to {a.commit}")
    elif a.command == "register":
        save_state(register_document(status, a.document, _list(a.sources), a.repo, _list(a.stories), _list(a.modules)), folder)
        print(f"Document {a.document}: {len(_list(a.sources))} source(s)")
    elif a.command == "story":
        save_state(register_story(status, a.key, a.us, a.story_change, a.prs_change, _list(a.modules), _list(a.files)), folder)
        print(f"Story {a.key} registered")
    else:
        repos = status["repositories"]
        repo = a.repo or (next(iter(repos)) if len(repos) == 1 else "")
        since = getattr(a, "from") or (repos.get(repo) or {}).get("commit")
        if a.git:
            if not since:
                raise SystemExit("There is no documented commit for that repository: pass --from or register it with 'repo'.")
            files = files_from_git(a.git, since, a.until)
        elif a.files_from:
            files = [x.strip() for x in Path(a.files_from).read_text(encoding="utf-8").splitlines() if x.strip()]
        else:
            files = _list(a.files)
        result = analyze(status, files, repo)
        md = folder / CHANGES
        md.write_text(build_changes_md(result, since or "?", a.until), encoding="utf-8")
        _format(md)
        if a.mark:
            save_state(mark(status, result, since or "?", a.until), folder)
        print(json.dumps({k: v for k, v in result.items() if k != "files"} | {"file_count": len(files)},
                         ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
