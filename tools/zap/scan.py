#!/usr/bin/env python3
"""
Web security scan with OWASP ZAP, in Docker. PASSIVE mode (baseline) by default and
ACTIVE mode (full scan) only with explicit authorization.

Usage (from the repo root):
    python tools/zap/scan.py --url https://staging.my-app.com [--story US-001]
                                        [--minutes 1] [--active] [--confirm]

What it does:
- Verifies that the URL is authorized in the .env (SECURITY_AUTHORIZED_URLS).
- Asks for confirmation (unless --confirm, for when the person already confirmed).
- Passive (zap-baseline.py, the default): crawls the site with the spider for --minutes and
  analyzes the responses without sending attacks or modifying data.
- Active (--active, zap-full-scan.py): besides crawling, ZAP sends attack payloads
  (injection, XSS, etc.) against the authorized URL. It is intrusive and may create or modify data,
  so it requires explicit authorization for active testing (PENTEST_AUTHORIZED=yes in the .env or
  --authorized) and confirmation. Never in production without written authorization. It does not do DoS or
  attack third parties.
- Writes to output/security/<story or host>/<date>/: zap.json (result), zap-native.html
  (ZAP report), zap.log and the k0lmenIA report (security-report.html).

Requires Docker running. The image can be changed with ZAP_IMAGE in the .env.
"""
import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE = "ghcr.io/zaproxy/zaproxy:stable"


def read_env():
    """The root .env (or K0LMENA_ENV_FILE), with the common k0lmenIA reader; the SECURITY_* and
    ZAP_* variables from the environment override the ones in the file."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith(("SECURITY_", "ZAP_"))})
    return values


def exit_with(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def authorized(url, env):
    allowed = [u.strip().rstrip("/") for u in re.split(r"[,\s]+", env.get("SECURITY_AUTHORIZED_URLS", "")) if u.strip()]
    if not allowed:
        exit_with("There are no authorized URLs. Add to the root .env:\n"
              "  SECURITY_AUTHORIZED_URLS=https://staging.my-app.com\n"
              "(only your own sites or sites with written authorization from their owners).")
    u = url.rstrip("/")
    if not any(u == a or u.startswith(a + "/") for a in allowed):
        exit_with(f"{url} is not in SECURITY_AUTHORIZED_URLS in the .env. Only authorized sites are scanned.")


def docker_available():
    if not shutil.which("docker"):
        exit_with("Docker was not found. Install it (Docker Desktop) to run ZAP.")
    r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    if r.returncode != 0:
        exit_with("Docker is installed but not running: open Docker Desktop and try again.")


def main():
    for stream in (sys.stdout, sys.stderr):  # proper accents in the Windows console
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Security scan with OWASP ZAP (passive by default; active with authorization)")
    ap.add_argument("--url", required=True, help="start URL of the site to scan (authorized in the .env)")
    ap.add_argument("--story", help="US-XXX for traceability and the output folder")
    ap.add_argument("--minutes", type=int, default=1, help="spider crawl minutes (1 to 10, default 1)")
    ap.add_argument("--active", action="store_true", help="active scan (full scan): ZAP sends attack payloads; intrusive and authorized only")
    ap.add_argument("--authorized", action="store_true", help="confirms through the CLI the authorization for the active scan (same as PENTEST_AUTHORIZED=yes)")
    ap.add_argument("--confirm", action="store_true", help="do not ask (the person already confirmed)")
    args = ap.parse_args()

    p = urlparse(args.url)
    if p.scheme not in ("http", "https") or not p.netloc:
        exit_with("The URL must start with http:// or https://.")
    if not 1 <= args.minutes <= 10:
        exit_with("--minutes must be between 1 and 10.")
    if args.story and not re.match(r"^[A-Za-z]+-\d+$", args.story):
        exit_with("--story must be an ID like US-001.")
    env = read_env()
    authorized(args.url, env)

    mode = "active" if args.active else "passive"
    if args.active:
        is_authorized = args.authorized or re.match(r"^(y|yes|true|1)$", str(env.get("PENTEST_AUTHORIZED", "")).strip(), re.I)
        if not is_authorized:
            exit_with("The active scan is intrusive (it sends attacks and may modify data). It requires explicit\n"
                  "authorization: add PENTEST_AUTHORIZED=yes to the root .env or pass --authorized, only for your\n"
                  "own site or one with written authorization from its owners, and never in production without that permission.")

    if not args.confirm:
        if not sys.stdin.isatty() or os.environ.get("CI"):
            exit_with("No interactive terminal: add --confirm (only if the person already authorized this scan).")
        notice = (f"ACTIVE scan (intrusive: it sends attack payloads and may create or modify data) of {args.url}"
                 if args.active else f"Passive scan of {args.url} (~{args.minutes} min of crawling)")
        try:
            r = input(f"{notice}. Confirm? (y/N): ")
        except EOFError:
            r = ""
        if not re.match(r"^y(es)?$", r.strip(), re.I):
            exit_with("Cancelled.", 1)

    docker_available()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = ROOT / "output" / "security" / (args.story or p.hostname) / stamp
    folder.mkdir(parents=True, exist_ok=True)

    image = env.get("ZAP_IMAGE") or DEFAULT_IMAGE
    script = "zap-full-scan.py" if args.active else "zap-baseline.py"
    cmd = ["docker", "run", "--rm", "-v", f"{folder}:/zap/wrk:rw", image,
           script, "-t", args.url, "-m", str(args.minutes),
           "-J", "zap.json", "-r", "zap-native.html", "-I"]
    print(f"ZAP {'full scan (active)' if args.active else 'baseline (passive)'} · {args.url} · output in {folder.relative_to(ROOT).as_posix()}")
    # The active scan takes much longer than the passive one: a wider margin for the attack phase.
    margin = 45 if args.active else 15
    with open(folder / "zap.log", "w", encoding="utf-8") as log:
        try:
            r = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "MSYS_NO_PATHCONV": "1"},
                               timeout=(args.minutes + margin) * 60)
        except subprocess.TimeoutExpired:
            exit_with(f"The scan exceeded the maximum time ({args.minutes + margin} min). Check {folder.relative_to(ROOT).as_posix()}/zap.log.", 1)
    # zap-baseline: 0 no alerts, 1 FAIL, 2 WARN, 3 scan error (with -I, WARN does not fail).
    result = folder / "zap.json"
    if not result.exists():
        tail = (folder / "zap.log").read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
        exit_with("ZAP produced no results (code %s). Last lines of the log:\n%s" % (r.returncode, "\n".join(tail)), 1)

    report = folder / "security-report.html"
    g = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_security_report.py"), str(result), str(report),
                        "--url", args.url, "--mode", mode] + (["--story", args.story] if args.story else []),
                       capture_output=True, text=True)
    print(f"Result: {result.relative_to(ROOT).as_posix()}")
    if g.returncode != 0:
        detail = (g.stderr or g.stdout).strip()[-800:]
        exit_with(f"ZAP finished, but the report could not be generated:\n{detail}", 1)
    print(f"Report: {report.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
