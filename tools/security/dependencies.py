#!/usr/bin/env python3
"""
Software composition analysis (SCA) of a project's dependencies: known vulnerabilities (CVE) and, when
possible, licenses. Read-only — it does not modify the project or install anything.

Usage (from the k0lmenIA repo root, pointing to the project to analyze):
    python tools/security/dependencies.py --path C:/projects/my-app [--output output/dependencies/sca.json]

What it does:
- Detects the project's manifests (package.json, requirements.txt/pyproject, pom.xml, go.mod, Gemfile,
  composer.json).
- Runs the available scanners in read mode: `npm audit --json` (Node), `pip-audit --format json`
  (Python) and, if present, `osv-scanner --format json` (multi-ecosystem). If one is missing, it says so and
  how to install it; it does not fail.
- Aggregates the vulnerabilities by severity (Critical/High/Medium/Low) and leaves a JSON for the
  dependency-analyst agent to triage.

It does not run or modify the project's code. Exploitation and dynamic scanning belong to security-analyst
and web-pentester.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

SEV = {"critical": "Critical", "high": "High", "moderate": "Medium", "medium": "Medium",
       "low": "Low", "info": "Low", "negligible": "Low", "unknown": "Medium"}
ORDER = ("Critical", "High", "Medium", "Low")


def norm_sev(s):
    return SEV.get((s or "").strip().lower(), "Medium")


def manifests(path):
    """Which ecosystems are in the project, based on its manifests."""
    r = Path(path)
    checks = {"package.json": "Node", "requirements.txt": "Python", "pyproject.toml": "Python",
              "pom.xml": "Java (Maven)", "build.gradle": "Java (Gradle)", "go.mod": "Go",
              "Gemfile": "Ruby", "composer.json": "PHP"}
    return sorted({eco for file, eco in checks.items() if (r / file).exists()})


def parse_npm_audit(data):
    """(vulnerabilities, metadata count). Supports the npm v7+ format."""
    vulns = []
    for name, v in (data.get("vulnerabilities") or {}).items():
        if not isinstance(v, dict):
            continue
        fix = v.get("fixAvailable")
        vulns.append({"package": name, "severity": norm_sev(v.get("severity")), "range": v.get("range"),
                      "fix": bool(fix) if not isinstance(fix, dict) else True, "ecosystem": "Node"})
    meta = ((data.get("metadata") or {}).get("vulnerabilities")) or {}
    return vulns, meta


def parse_pip_audit(data):
    """pip-audit --format json: list of {name, version, vulns:[{id, fix_versions}]}."""
    vulns = []
    items = data if isinstance(data, list) else (data.get("dependencies") if isinstance(data, dict) else []) or []
    for dep in items:
        for v in dep.get("vulns") or []:
            vulns.append({"package": f'{dep.get("name")} {dep.get("version", "")}'.strip(), "id": v.get("id"),
                          "severity": norm_sev(v.get("severity")), "fix": bool(v.get("fix_versions")), "ecosystem": "Python"})
    return vulns


def count(vulns):
    return {s: sum(1 for v in vulns if v.get("severity") == s) for s in ORDER}


def _run(cmd, path):
    try:
        p = subprocess.run(cmd, cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    except (OSError, subprocess.TimeoutExpired) as ex:
        return None, str(ex)[:200]
    try:
        return json.loads(p.stdout or "null"), None
    except ValueError:
        return None, (p.stderr or "non-JSON output").strip()[:200]


def survey(path):
    ecos = manifests(path)
    inv = {"path": str(path), "ecosystems": ecos, "vulnerabilities": [], "errors": {}, "scanners": []}
    if "Node" in ecos:
        if shutil.which("npm"):
            data, err = _run(["npm", "audit", "--json"], path)
            if data:
                v, _ = parse_npm_audit(data)
                inv["vulnerabilities"] += v
                inv["scanners"].append("npm audit")
            elif err:
                inv["errors"]["npm"] = err
        else:
            inv["errors"]["npm"] = "npm is not installed (required for Node SCA)."
    if "Python" in ecos:
        if shutil.which("pip-audit"):
            data, err = _run(["pip-audit", "--format", "json"], path)
            if data is not None:
                inv["vulnerabilities"] += parse_pip_audit(data)
                inv["scanners"].append("pip-audit")
            elif err:
                inv["errors"]["pip-audit"] = err
        else:
            inv["errors"]["pip-audit"] = "pip-audit is not installed: `pip install pip-audit` (Python SCA)."
    # osv-scanner covers several ecosystems at once
    if shutil.which("osv-scanner"):
        data, err = _run(["osv-scanner", "--format", "json", "-r", "."], path)
        if data:
            for res in (data.get("results") or []):
                for pkg in res.get("packages") or []:
                    name = (pkg.get("package") or {}).get("name")
                    for v in pkg.get("vulnerabilities") or []:
                        inv["vulnerabilities"].append({"package": name, "id": v.get("id"), "severity": "Medium",
                                                        "ecosystem": (pkg.get("package") or {}).get("ecosystem"), "fix": None})
            inv["scanners"].append("osv-scanner")
        elif err:
            inv["errors"]["osv-scanner"] = err
    elif not inv["scanners"]:
        inv["errors"]["osv-scanner"] = "osv-scanner is not installed (optional, multi-ecosystem): https://google.github.io/osv-scanner/"
    inv["summary"] = {"ecosystems": ecos, "total": len(inv["vulnerabilities"]), "by_severity": count(inv["vulnerabilities"])}
    return inv


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Dependency SCA (CVEs) of a project, read-only.")
    ap.add_argument("--path", default=".", help="path of the project to analyze (or REPO_LOCAL_PATH in the .env)")
    ap.add_argument("--output", default="", help="path where to save the JSON (optional)")
    args = ap.parse_args(argv)
    path = Path(args.path)
    if not path.exists():
        print(f"[dependencies] The path {path} does not exist.", file=sys.stderr)
        return 2
    if not manifests(path):
        print(f"[dependencies] No dependency manifests were found in {path}.", file=sys.stderr)
        return 2
    inv = survey(path)
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[dependencies] Data in {p}", file=sys.stderr)
    print(text)
    c = inv["summary"]["by_severity"]
    print(f"[dependencies] {inv['summary']['total']} vulnerability(ies): {c['Critical']} critical, {c['High']} high. Scanners: {', '.join(inv['scanners']) or 'none'}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
