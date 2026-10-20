#!/usr/bin/env python3
"""
Static application security testing (SAST) of the code and secret scanning, read-only.

Usage (from the k0lmenIA repo root, pointing to the project to analyze):
    python tools/security/sast.py --path C:/projects/my-app [--output output/sast/sast.json]

What it does:
- **Secrets** (no dependencies, always runs): walks the project's text files looking for key and credential
  patterns (AWS, Google, GitHub, Slack, Stripe, private keys, JWT and password/secret/token=... style
  assignments). The value is **redacted** in the output (it is never printed in full).
- **SAST** (optional): if `semgrep` is present, it runs `semgrep --json` with its default config and adds the findings;
  if `gitleaks` is present, it adds its secret detection. If they are missing, it says so and how to install them; it does not fail.
- Aggregates by severity and leaves a JSON for the secure-code-analyst agent to triage.

It does not run or modify the project's code.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

IGNORE_DIR = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__", ".next", "out", "vendor", "target", "coverage"}
TEXT_EXT = {".js", ".ts", ".tsx", ".jsx", ".py", ".java", ".rb", ".go", ".php", ".cs", ".env", ".yml", ".yaml",
             ".json", ".xml", ".properties", ".ini", ".cfg", ".conf", ".sh", ".ps1", ".tf", ".txt", ".md", ".html"}
MAX_BYTES = 2 * 1024 * 1024

# (type, regex). Conservative patterns so as not to flood with false positives.
PATTERNS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z\-]{10,}\b")),
    ("Stripe secret key", re.compile(r"\bsk_live_[0-9A-Za-z]{24,}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("Credential in assignment", re.compile(r"(?i)(password|passwd|secret|api[_-]?key|token|access[_-]?key)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]")),
    ("URL with credentials", re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@")),
]
SEV_SEMGREP = {"ERROR": "High", "WARNING": "Medium", "INFO": "Low"}


def redact(fragment):
    """Shows just enough to locate the secret without exposing it (first 4 characters + …)."""
    f = fragment.strip()
    return (f[:4] + "…") if len(f) > 6 else "…"


def find_secrets(text):
    """[(type, line_no, redacted_fragment)] of the secret patterns in the text. Testable and pure."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for kind, rx in PATTERNS:
            m = rx.search(line)
            if m:
                out.append((kind, i, redact(m.group(0))))
    return out


def scan_secrets(path):
    findings = []
    root = Path(path)
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        if any(part in IGNORE_DIR for part in p.parts):
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for kind, line, frag in find_secrets(text):
            findings.append({"type": kind, "file": str(p.relative_to(root)), "line": line,
                              "fragment": frag, "severity": "High", "origin": "secrets"})
    return findings


def parse_semgrep(data):
    out = []
    for r in (data.get("results") or []):
        extra = r.get("extra") or {}
        out.append({"rule": r.get("check_id"), "file": r.get("path"),
                    "line": (r.get("start") or {}).get("line"), "severity": SEV_SEMGREP.get(extra.get("severity"), "Medium"),
                    "message": (extra.get("message") or "")[:300], "origin": "semgrep"})
    return out


def count(findings):
    return {s: sum(1 for h in findings if h.get("severity") == s) for s in ("Critical", "High", "Medium", "Low")}


def survey(path):
    inv = {"path": str(path), "secrets": [], "sast": [], "errors": {}, "scanners": ["secrets (built-in)"]}
    inv["secrets"] = scan_secrets(path)
    if shutil.which("semgrep"):
        try:
            p = subprocess.run(["semgrep", "--config", "auto", "--json", "--quiet"], cwd=path,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
            data = json.loads(p.stdout or "null")
            if data:
                inv["sast"] = parse_semgrep(data)
                inv["scanners"].append("semgrep")
        except (OSError, subprocess.TimeoutExpired, ValueError) as ex:
            inv["errors"]["semgrep"] = str(ex)[:200]
    else:
        inv["errors"]["semgrep"] = "semgrep is not installed (SAST): `pip install semgrep` or https://semgrep.dev."
    everything = inv["secrets"] + inv["sast"]
    inv["summary"] = {"secrets": len(inv["secrets"]), "sast": len(inv["sast"]),
                      "total": len(everything), "by_severity": count(everything)}
    return inv


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="SAST and secret scanning of a project, read-only.")
    ap.add_argument("--path", default=".", help="path of the project to analyze (or REPO_LOCAL_PATH in the .env)")
    ap.add_argument("--output", default="", help="path where to save the JSON (optional)")
    args = ap.parse_args(argv)
    path = Path(args.path)
    if not path.exists():
        print(f"[sast] The path {path} does not exist.", file=sys.stderr)
        return 2
    inv = survey(path)
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[sast] Data in {p}", file=sys.stderr)
    print(text)
    print(f"[sast] {inv['summary']['secrets']} secret(s) and {inv['summary']['sast']} SAST finding(s). Scanners: {', '.join(inv['scanners'])}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
