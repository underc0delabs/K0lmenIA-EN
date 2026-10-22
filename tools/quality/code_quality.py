#!/usr/bin/env python3
"""
Static code quality survey of a project: best practices, maintainability and performance patterns, read-only.

Usage (from the k0lmenIA repo root):
    python tools/quality/code_quality.py --path C:/projects/my-app [--output output/code-quality/my-app/quality.json]
    python tools/quality/code_quality.py --repo my-company/my-app --provider github [--branch main] [--output ...]

Where the code comes from:
- `--path`: a local copy (or REPO_LOCAL_PATH in the .env).
- `--repo`: a GitHub or GitLab repository (`owner/name` or its https URL). It is cloned **shallow** into
  `--clone-dir` (default: the system temp folder, `k0lmenia-repos/<name>`) with the token from the .env
  (GITHUB_TOKEN or GITLAB_TOKEN; GITLAB_URL for self-hosted). The token travels only as an HTTP header of
  that git call: it is not written into `.git/config` and is never printed. Without a token, public repos still work.

What it measures (it never runs or modifies the project's code):
- **Inventory**: files and lines of code per language.
- **Maintainability**: large files, long lines, TODO/FIXME/HACK markers and **duplicated code**
  (blocks of identical normalized lines across files; built-in, no dependencies).
- **Complexity**: cyclomatic complexity and function length per function with `lizard` if installed
  (`pip install lizard`, multi-language); if it is missing, it says so and doesn't fail.
- **Best practices and performance patterns** (heuristics per language): empty catch blocks, bare except,
  mutable default arguments, debug output left in, synchronous I/O in Node, `await` or queries inside a loop
  (possible N+1), `SELECT *`, `Thread.sleep`… Each one is a **candidate**: the agent confirms it by reading the code.
- **Linters** already configured in the project, without --fix: `ruff` (Python) and the project's own `eslint`
  (JS/TS, only if it has an eslint config and eslint installed in node_modules).

Leaves a JSON for the code-quality-analyst agent to triage.
"""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from _env import read_env  # noqa: E402

IGNORE_DIR = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".next", "out", "vendor",
              "target", "coverage", "bin", "obj", ".idea", ".vscode", ".gradle", "Pods", ".nuxt", ".cache"}
LANGUAGES = {".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
             ".ts": "TypeScript", ".tsx": "TypeScript", ".py": "Python", ".java": "Java", ".kt": "Kotlin",
             ".cs": "C#", ".go": "Go", ".rb": "Ruby", ".php": "PHP", ".swift": "Swift", ".scala": "Scala",
             ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++", ".rs": "Rust", ".sql": "SQL",
             ".vue": "Vue", ".svelte": "Svelte", ".dart": "Dart", ".cls": "Apex", ".trigger": "Apex"}
MAX_BYTES = 1024 * 1024
LARGE_FILE_LINES = 500
LONG_LINE = 200
DUP_WINDOW = 6           # identical normalized lines in a row to count as a duplicated block
COMPLEXITY_LIMIT = 15    # cyclomatic complexity above this = hard to test and maintain
FUNCTION_LINES_LIMIT = 80
MARKER = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
JS = {"JavaScript", "TypeScript", "Vue", "Svelte"}
JVM = {"Java", "Kotlin", "Scala"}
ANY_CODE = set(LANGUAGES.values()) - {"SQL"}

# (rule, category, severity, languages, regex, message). Conservative patterns: each is a candidate to confirm.
PATTERNS = [
    ("empty-catch", "Reliability", "Medium", JS | JVM | {"C#", "PHP", "Dart", "Apex", "Swift"},
     re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}"), "Empty catch block: the error is swallowed silently."),
    ("bare-except", "Reliability", "Medium", {"Python"}, re.compile(r"^\s*except\s*:"),
     "Bare `except:` also catches KeyboardInterrupt/SystemExit and hides the real error."),
    ("except-pass", "Reliability", "Medium", {"Python"}, re.compile(r"^\s*except[^:]*:\s*pass\s*$"),
     "Exception caught and ignored with `pass`."),
    ("mutable-default", "Reliability", "Medium", {"Python"}, re.compile(r"^\s*def \w+\(.*=\s*(\[\]|\{\}|set\(\))"),
     "Mutable default argument: it is shared between calls."),
    ("wildcard-import", "Best practice", "Low", {"Python", "Java"}, re.compile(r"^\s*(from\s+\S+\s+import\s+\*|import\s+[\w.]+\.\*;)"),
     "Wildcard import: hides where names come from."),
    ("debugger", "Best practice", "Medium", JS, re.compile(r"^\s*debugger\s*;?\s*$"), "`debugger` statement left in the code."),
    ("console-log", "Best practice", "Low", JS, re.compile(r"\bconsole\.(log|debug)\("), "Debug output left in the code (`console.log`)."),
    ("print-stack", "Best practice", "Low", JVM, re.compile(r"\.printStackTrace\(\)|System\.out\.println\("),
     "Debug output instead of a logger (`printStackTrace` / `System.out`)."),
    ("ts-any", "Best practice", "Low", {"TypeScript"}, re.compile(r":\s*any\b|<any>|as any\b"), "`any` type: turns off type checking."),
    ("ts-ignore", "Best practice", "Low", {"TypeScript", "JavaScript"}, re.compile(r"@ts-ignore|eslint-disable(?!-next-line)"),
     "Checks disabled (`@ts-ignore` / `eslint-disable`)."),
    ("sync-io", "Performance", "Medium", JS, re.compile(r"\b(readFileSync|writeFileSync|execSync|spawnSync|existsSync)\("),
     "Synchronous I/O in Node blocks the event loop (fine in scripts, bad in a request path)."),
    ("foreach-async", "Reliability", "Medium", JS, re.compile(r"\.forEach\(\s*async\b"),
     "`forEach(async …)` doesn't wait for the promises: errors and ordering are lost."),
    ("thread-sleep", "Performance", "Medium", JVM | {"C#"}, re.compile(r"\bThread\.sleep\(|\bThread\.Sleep\("),
     "Blocking sleep: usually a wait that should be an event or a retry with backoff."),
    ("select-star", "Performance", "Low", set(LANGUAGES.values()), re.compile(r"(?i)\bselect\s+\*\s+from\b"),
     "`SELECT *`: brings columns that aren't used and breaks if the table changes."),
    ("sql-concat", "Reliability", "High", ANY_CODE,
     re.compile(r"(?i)[\"'`]\s*(select|insert|update|delete)\b[^\"'`]*[\"'`]\s*(\+|\.\s*\$|%\s)|\$\{[^}]+\}[^`]*\b(where|values)\b"),
     "SQL built by concatenation: injection risk and no plan reuse (confirm with secure-code-analyst)."),
]
LOOP = re.compile(r"^\s*(for\b|for\s*\(|while\s*\(|while\b.*:|\w[\w.]*\.(forEach|map)\()")
IN_LOOP = [
    ("await-in-loop", "Performance", "Medium", JS, re.compile(r"\bawait\b"),
     "`await` inside a loop: the calls run one by one (consider Promise.all or a batch)."),
    ("query-in-loop", "Performance", "Medium", ANY_CODE,
     re.compile(r"\.(query|execute|executeQuery|executeSql|rawQuery|findOne|findById|findUnique|findFirst|objects\.get|objects\.filter)\("
                r"|\b(fetch|axios\.\w+|requests\.(get|post|put|delete)|httpx\.\w+|http\.(get|request))\("),
     "Query or remote call inside a loop: possible N+1 (confirm whether it runs per item)."),
]
LOOP_SPAN = 6  # lines after the loop header in which a call counts as "inside the loop"
SEV_ORDER = ("Critical", "High", "Medium", "Low")


# ---------------- pure helpers (testable) ----------------
def language_of(path):
    return LANGUAGES.get(Path(path).suffix.lower())


def code_lines(text):
    return sum(1 for ln in text.splitlines() if ln.strip())


def find_patterns(text, language):
    """[(rule, category, severity, line, message)] of the heuristic patterns in the text."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        for rule, cat, sev, langs, rx, msg in PATTERNS:
            if language in langs and rx.search(line):
                out.append((rule, cat, sev, i, msg))
    seen = set()
    for i, line in enumerate(lines):
        if not LOOP.search(line):
            continue
        for j in range(i + 1, min(i + 1 + LOOP_SPAN, len(lines))):
            for rule, cat, sev, langs, rx, msg in IN_LOOP:
                if language in langs and rx.search(lines[j]) and (rule, j + 1) not in seen:
                    seen.add((rule, j + 1))
                    out.append((rule, cat, sev, j + 1, msg))
    return out


def _normalize(line):
    s = re.sub(r"\s+", " ", line.strip())
    return s if len(s) > 3 and s not in {"{", "}", "};", "});", "end", "else {", "} else {", "return;", "pass"} \
        and not s.startswith(("//", "#", "*", "/*", "import ", "from ", "using ", "package ", "@")) else ""


def find_duplicates(files, window=DUP_WINDOW):
    """files: {name: text}. Blocks of `window` identical normalized lines repeated in more than one place.
    Returns (blocks, duplicated_lines) with blocks = [{"lines": n, "locations": [(file, line)…]}]."""
    index, norms = {}, {}
    for name, text in files.items():
        norm = [(i + 1, _normalize(ln)) for i, ln in enumerate(text.splitlines())]
        norms[name] = [(n, s) for n, s in norm if s]
        for k in range(len(norms[name]) - window + 1):
            chunk = "\n".join(s for _, s in norms[name][k:k + window])
            index.setdefault(hashlib.sha1(chunk.encode("utf-8")).hexdigest(), []).append((name, k))
    dup = {loc for locs in index.values() if len(locs) > 1 for loc in locs}
    dup_lines = {(f, norms[f][k + d][0]) for f, k in dup for d in range(window)}
    blocks = []
    for locs in index.values():
        # a block starts where the previous window wasn't duplicated; it grows while the next ones are
        if len(locs) < 2 or any((f, k - 1) in dup for f, k in locs):
            continue
        f0, k0 = locs[0]
        extra = 0
        while (f0, k0 + extra + 1) in dup:
            extra += 1
        blocks.append({"lines": window + extra, "locations": [[f, norms[f][k][0]] for f, k in sorted(locs)]})
    return blocks, len(dup_lines)


def count(findings):
    return {s: sum(1 for h in findings if h.get("severity") == s) for s in SEV_ORDER}


# ---------------- getting the code ----------------
def _repo_url(repo, provider, env):
    if repo.startswith(("https://", "http://")):
        return repo
    if provider == "gitlab":
        return f"{(env.get('GITLAB_URL') or 'https://gitlab.com').rstrip('/')}/{repo}.git"
    return f"https://github.com/{repo}.git"


def auth_header(provider, token):
    """HTTP header for git with the token (Basic, accepted by GitHub and GitLab). None without a token."""
    if not token:
        return None
    user = "oauth2" if provider == "gitlab" else "x-access-token"
    return "Authorization: Basic " + base64.b64encode(f"{user}:{token}".encode()).decode()


def clone(repo, provider, branch, clone_dir, env):
    """Shallow clone (or update of an earlier clone). Returns (path, commit, error)."""
    if not shutil.which("git"):
        return None, None, "git is not installed."
    url = _repo_url(repo, provider, env)
    token = env.get("GITLAB_TOKEN" if provider == "gitlab" else "GITHUB_TOKEN") or ""
    header = auth_header(provider, token)
    base = ["git"] + (["-c", f"http.extraHeader={header}"] if header else [])
    dest = Path(clone_dir)
    if (dest / ".git").exists():
        cmd = base + ["-C", str(dest), "pull", "--depth", "1", "--ff-only"]
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        cmd = base + ["clone", "--depth", "1"] + (["--branch", branch] if branch else []) + [url, str(dest)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900)
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "").replace(token, "***") if token else (p.stderr or p.stdout or "")
        return None, None, f"git clone failed: {err.strip()[:300]}"
    c = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], capture_output=True, text=True)
    return dest, (c.stdout or "").strip()[:12] or None, None


# ---------------- scanners ----------------
def walk(root):
    for p in Path(root).rglob("*"):
        if p.is_file() and language_of(p) and not any(part in IGNORE_DIR for part in p.relative_to(root).parts):
            try:
                if p.stat().st_size <= MAX_BYTES and not p.name.endswith((".min.js", ".bundle.js")):
                    yield p
            except OSError:
                continue


def run_lizard(root, files):
    try:
        import lizard
    except ImportError:
        return None, "lizard is not installed (complexity per function): `pip install lizard`."
    funcs = []
    for p in files:
        try:
            info = lizard.analyze_file(str(p))
        except Exception:  # lizard can't parse some files; skip them
            continue
        for f in info.function_list:
            funcs.append({"file": str(p.relative_to(root)), "function": f.name, "line": f.start_line,
                          "complexity": f.cyclomatic_complexity, "lines": f.nloc, "parameters": len(f.parameters)})
    return funcs, None


def run_ruff(root):
    if not shutil.which("ruff"):
        return None, "ruff is not installed (Python linter): `pip install ruff`."
    p = subprocess.run(["ruff", "check", "--output-format", "json", "--exit-zero", "."], cwd=root,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    try:
        data = json.loads(p.stdout or "[]")
    except ValueError:
        return None, f"ruff output could not be read: {(p.stderr or '')[:200]}"
    return [{"rule": d.get("code"), "file": os.path.relpath(d.get("filename", ""), root),
             "line": (d.get("location") or {}).get("row"), "message": (d.get("message") or "")[:200]} for d in data], None


def run_eslint(root):
    has_config = any((Path(root) / n).exists() for n in (
        "eslint.config.js", "eslint.config.mjs", "eslint.config.cjs", ".eslintrc", ".eslintrc.js", ".eslintrc.cjs",
        ".eslintrc.json", ".eslintrc.yml", ".eslintrc.yaml"))
    binary = Path(root) / "node_modules" / ".bin" / ("eslint.cmd" if os.name == "nt" else "eslint")
    if not has_config:
        return None, "The project has no eslint config: the built-in JS/TS heuristics were used."
    if not binary.exists():
        return None, "The project has an eslint config but no node_modules: run `npm ci` in the project to use its eslint."
    p = subprocess.run([str(binary), "-f", "json", "."], cwd=root, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    try:
        data = json.loads(p.stdout or "[]")
    except ValueError:
        return None, f"eslint output could not be read: {(p.stderr or '')[:200]}"
    out = []
    for f in data:
        for m in f.get("messages") or []:
            out.append({"rule": m.get("ruleId"), "file": os.path.relpath(f.get("filePath", ""), root),
                        "line": m.get("line"), "message": (m.get("message") or "")[:200],
                        "severity": "Medium" if m.get("severity") == 2 else "Low"})
    return out, None


def survey(root, use_linters=True):
    root = Path(root)
    inv = {"path": str(root), "scanners": ["heuristics (built-in)", "duplication (built-in)"], "errors": {},
           "languages": {}, "findings": [], "large_files": [], "markers": 0, "long_lines": 0,
           "functions": [], "duplicates": [], "linters": {}}
    files, texts = list(walk(root)), {}
    for p in files:
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel, lang = str(p.relative_to(root)), language_of(p)
        texts[rel] = text
        loc = code_lines(text)
        stats = inv["languages"].setdefault(lang, {"files": 0, "loc": 0})
        stats["files"] += 1
        stats["loc"] += loc
        if loc > LARGE_FILE_LINES:
            inv["large_files"].append({"file": rel, "loc": loc})
        inv["markers"] += len(MARKER.findall(text))
        inv["long_lines"] += sum(1 for ln in text.splitlines() if len(ln) > LONG_LINE)
        for rule, cat, sev, line, msg in find_patterns(text, lang):
            inv["findings"].append({"rule": rule, "category": cat, "severity": sev, "file": rel, "line": line,
                                    "message": msg, "origin": "heuristics"})
    blocks, dup_lines = find_duplicates(texts)
    inv["duplicates"] = sorted(blocks, key=lambda b: -b["lines"] * len(b["locations"]))[:50]
    total_loc = sum(v["loc"] for v in inv["languages"].values())

    funcs, err = run_lizard(root, files)
    if err:
        inv["errors"]["lizard"] = err
    else:
        inv["scanners"].append("lizard")
        inv["functions"] = sorted([f for f in funcs if f["complexity"] > COMPLEXITY_LIMIT or f["lines"] > FUNCTION_LINES_LIMIT],
                                  key=lambda f: -f["complexity"])[:100]
        for f in inv["functions"]:
            sev = "High" if f["complexity"] > 2 * COMPLEXITY_LIMIT else "Medium"
            inv["findings"].append({"rule": "complex-function", "category": "Maintainability", "severity": sev,
                                    "file": f["file"], "line": f["line"], "origin": "lizard",
                                    "message": f"{f['function']}: complexity {f['complexity']}, {f['lines']} lines."})
        inv["complexity"] = {"functions": len(funcs),
                             "average": round(sum(f["complexity"] for f in funcs) / len(funcs), 1) if funcs else 0,
                             "max": max((f["complexity"] for f in funcs), default=0),
                             "over_limit": sum(1 for f in funcs if f["complexity"] > COMPLEXITY_LIMIT)}
    if use_linters:
        for name, fn in (("ruff", run_ruff), ("eslint", run_eslint)):
            if name == "ruff" and "Python" not in inv["languages"]:
                continue
            if name == "eslint" and not (JS & set(inv["languages"])):
                continue
            res, err = fn(root)
            if err:
                inv["errors"][name] = err
            else:
                inv["scanners"].append(name)
                by_rule = {}
                for r in res:
                    by_rule[r.get("rule") or "?"] = by_rule.get(r.get("rule") or "?", 0) + 1
                inv["linters"][name] = {"total": len(res), "by_rule": dict(sorted(by_rule.items(), key=lambda x: -x[1])[:30]),
                                        "sample": res[:200]}
    inv["summary"] = {"files": len(texts), "loc": total_loc, "findings": len(inv["findings"]),
                      "by_severity": count(inv["findings"]),
                      "by_category": {c: sum(1 for h in inv["findings"] if h["category"] == c)
                                      for c in sorted({h["category"] for h in inv["findings"]})},
                      "duplicated_lines": dup_lines,
                      "duplication_pct": round(100 * dup_lines / total_loc, 1) if total_loc else 0,
                      "large_files": len(inv["large_files"]), "markers": inv["markers"],
                      "linter_issues": sum(v["total"] for v in inv["linters"].values())}
    return inv


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    env = {**read_env(), **os.environ}
    ap = argparse.ArgumentParser(description="Static code quality survey (best practices, maintainability, performance), read-only.")
    ap.add_argument("--path", default="", help="local path of the project (or REPO_LOCAL_PATH in the .env)")
    ap.add_argument("--repo", default="", help="GitHub/GitLab repository to clone: owner/name or https URL")
    ap.add_argument("--provider", default=env.get("REPO_PROVIDER") or "github", choices=["github", "gitlab"])
    ap.add_argument("--branch", default="", help="branch to clone (default: the repo's default branch)")
    ap.add_argument("--clone-dir", default="", help="where to clone (default: <temp>/k0lmenia-repos/<name>)")
    ap.add_argument("--no-linters", action="store_true", help="don't run ruff/eslint")
    ap.add_argument("--output", default="", help="path where to save the JSON (optional)")
    args = ap.parse_args(argv)

    source = {}
    if args.repo:
        name = re.sub(r"\.git$", "", args.repo.rstrip("/")).split("/")[-1]
        dest = args.clone_dir or str(Path(tempfile.gettempdir()) / "k0lmenia-repos" / name)
        path, commit, err = clone(args.repo, args.provider, args.branch, dest, env)
        if err:
            print(f"[code-quality] {err}", file=sys.stderr)
            return 2
        source = {"repo": args.repo, "provider": args.provider, "branch": args.branch or "(default)", "commit": commit}
    else:
        path = Path(args.path or env.get("REPO_LOCAL_PATH") or ".")
    if not Path(path).exists():
        print(f"[code-quality] The path {path} does not exist.", file=sys.stderr)
        return 2
    inv = survey(path, use_linters=not args.no_linters)
    inv["source"] = source
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[code-quality] Data in {p}", file=sys.stderr)
    else:
        print(text)
    s = inv["summary"]
    print(f"[code-quality] {s['files']} file(s), {s['loc']} lines of code, {s['findings']} finding(s), "
          f"{s['duplication_pct']}% duplicated. Scanners: {', '.join(inv['scanners'])}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
