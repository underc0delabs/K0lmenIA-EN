#!/usr/bin/env python3
"""
Checks that the k0lmenIA environment is ready and tells you what is missing and how to fix it.

Usage (from the repo root):
    python scripts/doctor.py [--section <name>] [--quick] [--json]     (on Mac/Linux: python3)
    npm run doctor

Sections: python, node, tools, fonts, env, integrations, connectors, repo and extras.
  --section   checks only one (or several, comma-separated): --section env,integrations
  --quick     skips the slow checks (network, Docker, Mailpit)
  --json      machine-readable output: [{"section", "status": ok|warning|missing, "text", "help"}]

Checks Python and its libraries, Node/npm, k0lmena and the Playwright browsers, Newman, k6, JMeter,
Java, Docker, Mailpit, the fonts for the reports and the website, the .env (and that every block you use
is complete and consistent), the enabled MCP connectors, git and what the portal, monitoring and the
evals need. It never shows .env values: only whether each variable is present, missing or invalid.
Exits with code 1 if something required is missing.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
K0 = ROOT / "tools" / "k0lmena"
sys.path.insert(0, str(ROOT / "scripts"))
from _env import read_env, env_file  # noqa: E402

OK, WARNING, MISSING = "OK  ", "!   ", "X   "
summary = {"ok": 0, "warning": 0, "missing": 0}
RESULTS = []
_OUTPUT = {"json": False, "section": ""}

# Variables each MCP connector needs to work (the OAuth ones need nothing).
# "A|B+C" = A, or else B and C together. ADO_PAT is only needed if authentication is by PAT.
CONNECTOR_VARIABLES = {
    "azure-devops": ["ADO_ORGANIZATION", "ADO_PAT"],
    "qtm4j": ["QTM4J_API_KEY"],
    "qmetry": ["QMETRY_API_KEY"],
    "aio-tests": ["AIO_MCP_URL", "AIO_API_TOKEN"],
    "k0lmena-tmt": ["K0LMENA_TMT_TOKEN"],
    "github": ["GITHUB_TOKEN"],
    "asana": ["ASANA_CLIENT_ID", "ASANA_CLIENT_SECRET"],
    "youtrack": ["YOUTRACK_URL", "YOUTRACK_TOKEN"],
}
# Authorized with your account (OAuth) from /mcp; the optional-token ones, only if that token is empty.
OAUTH_CONNECTORS = ("atlassian", "figma", "figma-desktop", "clickup", "trello", "notion", "shortcut", "asana")
OPTIONAL_TOKEN_CONNECTORS = {"gitlab": "GITLAB_TOKEN", "linear": "LINEAR_API_KEY", "monday": "MONDAY_API_TOKEN"}
MANAGEMENT_VARIABLES = {
    "xray-cloud": ["MANAGEMENT_PROJECT", "XRAY_CLOUD_CLIENT_ID", "XRAY_CLOUD_CLIENT_SECRET", "JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"],
    "xray-dc": ["MANAGEMENT_PROJECT", "XRAY_DC_URL", "XRAY_DC_TOKEN|XRAY_DC_USER+XRAY_DC_PASSWORD"],
    "qtm4j": ["MANAGEMENT_PROJECT", "QTM4J_API_KEY"],
    "aio": ["MANAGEMENT_PROJECT", "AIO_API_TOKEN"],
}
# Connector each app repository provider needs (project-documenter).
REPO_CONNECTOR = {"github": "github", "gitlab": "gitlab", "azure-repos": "azure-devops", "bitbucket": "atlassian"}
DB_ENGINES = ("postgres", "mysql", "mariadb", "sqlserver", "mongodb")
REPORT_SOURCES = ("saira.woff2", "inter.woff2", "jetbrains-mono.woff2")


def missing(names, env):
    """The variables that are missing; "A|B+C" is satisfied by A or by B and C."""
    output = []
    for name in names:
        options = [o.split("+") for o in name.split("|")]
        if not any(all(env.get(v) for v in group) for group in options):
            output.append(" or ".join("+".join(g) for g in options))
    return output


def line(status, text, help=""):
    key = {OK: "ok", WARNING: "warning", MISSING: "missing"}[status]
    summary[key] += 1
    RESULTS.append({"section": _OUTPUT["section"], "status": key, "text": text, "help": help})
    if not _OUTPUT["json"]:
        print(f"  {status}{text}" + (f"\n        → {help}" if help else ""))


def note(text):
    if not _OUTPUT["json"]:
        print(f"        → {text}")


def command(*args, timeout=30):
    try:
        r = subprocess.run(list(args), capture_output=True, text=True, timeout=timeout,
                           shell=(os.name == "nt" and args[0] in ("npm", "npx", "newman", "claude")))
        return (r.stdout or r.stderr).strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def major_version(text):
    m = re.search(r"(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def is_url(value):
    u = urlparse((value or "").strip())
    return u.scheme in ("http", "https") and bool(u.netloc)


def section(key, title):
    _OUTPUT["section"] = key
    if not _OUTPUT["json"]:
        print(f"\n{title}")


def read_environment():
    file = env_file()
    return file, {**read_env(file), **{k: v for k, v in os.environ.items()}}


# ------------------------------------------------------------------ sections
def check_python(ctx):
    section("python", "Python")
    py = ctx["py"]
    v = sys.version_info
    if (v.major, v.minor) >= (3, 10):
        line(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        line(MISSING, f"Python {v.major}.{v.minor} (3.10 or later is required)", "Install Python 3.10+ from https://www.python.org/downloads/")
    lacking = [m for m in ("openpyxl", "tabulate", "requests") if not _importable(m)]
    if lacking:
        line(WARNING, f"Missing libraries: {', '.join(lacking)} (the scripts install them on their own the first time)",
             f"{py} -m pip install -r requirements.txt")
    else:
        line(OK, "Python libraries (openpyxl, tabulate, requests)")
    for module, purpose, package in (("yaml", "Insomnia v5 collections (.yaml)", "pyyaml"),
                                     ("pypdf", "the cover page without footer in the documentation PDF (node docs/generate.js)", "pypdf")):
        if _importable(module):
            line(OK, f"{package} ({purpose})")
        else:
            line(WARNING, f"{package} is not installed (optional: {purpose})", f"{py} -m pip install {package}")


def check_node(ctx):
    section("node", "Node.js and k0lmena")
    node = command("node", "--version")
    if not node:
        line(MISSING, "Node.js is not installed", "Install Node.js 22 LTS from https://nodejs.org")
    elif major_version(node) and major_version(node)[0] >= 20:
        line(OK, f"Node.js {node}" + ("" if major_version(node)[0] >= 22 else " (mobile needs 22+)"))
    else:
        line(MISSING, f"Node.js {node} (20 or later is required; 22 LTS recommended)", "Update Node.js from https://nodejs.org")
    if (K0 / "node_modules").exists():
        line(OK, "k0lmena installed (tools/k0lmena/node_modules)")
        if not (K0 / "node_modules" / "playwright").exists():
            line(MISSING, "Playwright is missing inside k0lmena", "npm install   (from the repo root)")
    else:
        line(MISSING, "k0lmena is not installed", "npm install   (from the repo root)")
    browsers = _playwright_folder()
    if browsers and any(browsers.glob("chromium*")):
        line(OK, "Playwright browsers")
    else:
        line(WARNING, "Can't find the Playwright browsers (web and E2E runs)", "cd tools/k0lmena && npx playwright install chromium")
    lacking = [n for n in ("firefox", "webkit") if not (browsers and any(browsers.glob(f"{n}-*")))]
    if lacking:
        line(WARNING, f"No {' or '.join(lacking)} (optional: only for the cross-browser agent)",
             f"cd tools/k0lmena && npx playwright install {' '.join(lacking)}")
    else:
        line(OK, "Firefox and WebKit (cross-browser)")
    if ctx["quick"]:
        line(WARNING, "Newman not checked (--quick)")
    elif command("newman", "--version", timeout=15):
        line(OK, "Newman (Postman, Bruno and Insomnia collections)")
    else:
        line(WARNING, "Newman is not installed (only for api-runner)", "npm install -g newman")


def check_tools(ctx):
    section("tools", "Performance, security and emails (optional)")
    k6 = K0 / "tools" / "k6" / ("k6.exe" if os.name == "nt" else "k6")
    line(OK, "k6") if k6.exists() or shutil.which("k6") else line(WARNING, "k6 is not installed", "npm run bootstrap:k6")
    jmeter = list((K0 / "tools" / "jmeter").glob("apache-jmeter-*/bin/ApacheJMeter.jar")) if (K0 / "tools" / "jmeter").exists() else []
    line(OK, "JMeter") if jmeter or os.environ.get("JMETER_HOME") else line(WARNING, "JMeter is not installed", "npm run bootstrap:jmeter")
    java = command("java", "-version", timeout=10)
    if java:
        line(OK, f"Java ({java.splitlines()[0]})")
    else:
        line(WARNING, "Java is not installed (JMeter needs it)", "Install Java 8+ (for example, Temurin 21: https://adoptium.net)")
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        line(OK, "ffmpeg and ffprobe (streaming, playback and image quality)")
    else:
        line(WARNING, "ffmpeg/ffprobe are not installed (for streaming-tester and image-quality-analyst)",
             "Install ffmpeg: winget install Gyan.FFmpeg · brew install ffmpeg · apt install ffmpeg")
    if shutil.which("sf"):
        line(OK, "Salesforce CLI (sf) installed (for salesforce-tester)")
    else:
        line(WARNING, "Salesforce CLI (sf) is not installed (only for salesforce-tester)",
             "Install it if you are going to test Salesforce: npm install --global @salesforce/cli")
    if shutil.which("shopify"):
        line(OK, "Shopify CLI installed (shopify-tester Theme Check)")
    else:
        line(WARNING, "Shopify CLI is not installed (only for the shopify-tester Theme Check)",
             "Install it if you are going to review a theme's code: npm install --global @shopify/cli")
    if shutil.which("wp"):
        line(OK, "WP-CLI installed (for wordpress-tester --wp-cli)")
    else:
        line(WARNING, "WP-CLI is not installed (optional for wordpress-tester)",
             "Install it if you have the site locally: https://wp-cli.org (or set WORDPRESS_WP_CLI in the .env if it runs in Docker)")
    for cmd, name, purpose, how in (
            ("pip-audit", "pip-audit", "dependency-analyst Python SCA", "pip install pip-audit"),
            ("osv-scanner", "osv-scanner", "dependency-analyst multi-ecosystem SCA", "https://google.github.io/osv-scanner/"),
            ("semgrep", "semgrep", "secure-code-analyst SAST", "pip install semgrep"),
            ("ruff", "ruff", "code-quality-analyst Python linter", "pip install ruff")):
        if shutil.which(cmd):
            line(OK, f"{name} installed ({purpose})")
        else:
            line(WARNING, f"{name} is not installed (optional, for the {purpose})", f"Install it if you are going to use it: {how}")
    # Python libraries for SAP (pywin32) and desktop (pywinauto) — Windows only
    import importlib.util
    for module, name, purpose, how in (
            ("win32com", "pywin32", "sap-tester SAP GUI Scripting", "pip install pywin32"),
            ("pywinauto", "pywinauto", "desktop-tester control tree", "pip install pywinauto")):
        if importlib.util.find_spec(module):
            line(OK, f"{name} installed ({purpose})")
        elif sys.platform == "win32":
            line(WARNING, f"{name} is not installed (optional, for the {purpose})", f"Install it if you are going to use it: {how}")
        else:
            line(OK, f"{name} does not apply (Windows only, for the {purpose})")
    if importlib.util.find_spec("lizard"):
        line(OK, "lizard installed (code-quality-analyst complexity)")
    else:
        line(WARNING, "lizard is not installed (optional, for the code-quality-analyst complexity)",
             "Install it if you are going to use it: pip install lizard")
    if shutil.which("appium"):
        line(OK, "Appium installed (mobile-tester and, with WinAppDriver, desktop-tester)")
    else:
        line(WARNING, "Appium is not installed (optional, for mobile-tester / WinAppDriver on desktop)",
             "Install it if you are going to automate mobile or desktop with Appium: npm install -g appium (and enable the connector with npm run connector -- activate appium)")
    if not shutil.which("docker"):
        line(WARNING, "Docker is not installed (the ZAP security scan and Mailpit need it)",
             "Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
    elif ctx["quick"]:
        line(OK, "Docker installed (didn't check whether it is running: --quick)")
    elif command("docker", "info", "--format", "{{.ServerVersion}}", timeout=8):
        line(OK, "Docker running")
    else:
        line(WARNING, "Docker is installed but not running", "Open Docker Desktop before a security scan or before using Mailpit")
    mailpit = ctx["env"].get("MAILPIT_URL", "")
    if mailpit and not ctx["quick"]:
        if _responds(mailpit.rstrip("/") + "/api/v1/info"):
            line(OK, "Mailpit responds at MAILPIT_URL")
        else:
            line(WARNING, "Mailpit does not respond at MAILPIT_URL (only for email-verifier)",
                 "docker compose -f tools/mailpit/docker-compose.yml up -d")


def check_sources(ctx):
    section("fonts", "Fonts for the reports and the website")
    for folder, purpose in ((ROOT / "scripts" / "fonts", "the HTML reports"), (ROOT / "docs" / "assets" / "fonts", "the website and the PDF")):
        lacking = [f for f in REPORT_SOURCES if not (folder / f).exists()]
        rel = folder.relative_to(ROOT).as_posix()
        if lacking:
            line(WARNING, f"Fonts missing in {rel}: {', '.join(lacking)} ({purpose} use the system fonts)",
                 "Restore the folder from the repository (git checkout -- " + rel + ")")
        else:
            line(OK, f"Saira, Inter and JetBrains Mono for {purpose}")


def check_env(ctx):
    section("env", "Configuration (.env)")
    file, env = ctx["file"], ctx["env"]
    if not file.exists():
        line(MISSING, f"{file.name} does not exist", "Run npm run configure: it asks you a few questions and creates the .env")
        return
    line(OK, f"{file.name} found")
    # The app URL goes only in APP_URL; k0lmena builds BASEURL from it (tools/k0lmena/env.js).
    app_url, baseurl = env.get("APP_URL", ""), env.get("BASEURL", "")
    if not app_url and not baseurl:
        line(WARNING, "APP_URL is empty: the app under test (agents, tools and web automation)", f"Fill it in {file.name}")
    elif app_url and not is_url(app_url):
        line(MISSING, "APP_URL is not a valid URL (it must start with http:// or https://)", f"Fix it in {file.name}")
    elif app_url:
        line(OK, "APP_URL defined")
    if baseurl:
        if not is_url(baseurl):
            line(MISSING, "BASEURL is not a valid URL (it must start with http:// or https://)", f"Better delete it and keep only APP_URL in {file.name}")
        elif not app_url:
            line(WARNING, "The URL is in BASEURL (old name): it is used anyway", f"Move it to APP_URL and delete BASEURL from {file.name}")
        elif baseurl.rstrip("/") != app_url.rstrip("/"):
            line(WARNING, "BASEURL and APP_URL are different: APP_URL is used", f"Delete BASEURL from {file.name}: the URL goes only in APP_URL")
        else:
            line(WARNING, "BASEURL repeats APP_URL: it is not needed", f"Delete BASEURL from {file.name}")
    if env.get("API_BASEURL") and not is_url(env["API_BASEURL"]):
        line(MISSING, "API_BASEURL is not a valid URL", f"Fix it in {file.name}")
    tool = env.get("MANAGEMENT_TOOL", "")
    if tool:
        if tool not in MANAGEMENT_VARIABLES:
            line(MISSING, f"MANAGEMENT_TOOL={tool} is not valid", "Use xray-cloud, xray-dc, qtm4j or aio")
        else:
            lacking = missing(MANAGEMENT_VARIABLES[tool], env)
            if lacking:
                line(MISSING, f"Management ({tool}): missing {', '.join(lacking)}", "Fill them in the .env (see .env.example)")
            else:
                line(OK, f"Test management: {tool}")
    connections = [c.strip() for c in (env.get("DB_CONNECTIONS") or "").split(",") if c.strip()]
    for c in connections:
        pref = f"DB_{c.upper()}_"
        engine = env.get(pref + "ENGINE", "")
        if engine not in DB_ENGINES:
            line(MISSING, f"Database {c}: {pref}ENGINE {'empty' if not engine else 'invalid'}", f"Use {', '.join(DB_ENGINES)}")
            continue
        lacking = [] if env.get(pref + "URL") else missing([pref + "HOST", pref + "DATABASE"], env)
        if lacking:
            line(MISSING, f"Database {c} ({engine}): missing {', '.join(lacking)} (or {pref}URL)", "Fill them in the .env (see .env.example)")
        else:
            line(OK, f"Database {c} ({engine})")
    authorized = [u.strip() for u in (env.get("SECURITY_AUTHORIZED_URLS") or "").split(",") if u.strip()]
    bad = [u for u in authorized if not is_url(u)]
    if bad:
        line(MISSING, f"SECURITY_AUTHORIZED_URLS has {len(bad)} invalid URL(s)", "Comma-separated, with http:// or https://")
    elif authorized:
        line(OK, f"Web security: {len(authorized)} authorized URL(s)")


def check_integrations(ctx):
    section("integrations", "Repository, roles, notifications and monitoring")
    before = len(RESULTS)
    _integrations(ctx)
    if len(RESULTS) == before:
        note("None configured (they are optional: REPO_*, PERMISSIONS_*, SLACK/TEAMS_WEBHOOK_URL, MONITORING_URLS in .env.example)")


def _integrations(ctx):
    env, active = ctx["env"], ctx["connectors"]
    provider = env.get("REPO_PROVIDER", "")
    if provider:
        if provider not in REPO_CONNECTOR:
            line(MISSING, f"REPO_PROVIDER={provider} is not valid", "Use github, gitlab, azure-repos or bitbucket")
        else:
            connector = REPO_CONNECTOR[provider]
            if not env.get("REPO_NAME"):
                line(MISSING, f"Repository ({provider}): REPO_NAME is missing", "E.g.: my-company/my-app (see .env.example)")
            elif connector not in active:
                line(WARNING, f"Repository ({provider}): the {connector} connector is not active",
                     f"npm run connector -- activate {connector}" if connector not in ("atlassian",) else "atlassian comes active: check .claude/settings.json")
            else:
                line(OK, f"App repository: {provider} ({env['REPO_NAME'].count(',') + 1} repository(ies))")
            if provider == "bitbucket" and (env.get("ATLASSIAN_MCP_AUTHENTICATION") or "oauth") != "token":
                line(MISSING, "Bitbucket needs ATLASSIAN_MCP_AUTHENTICATION=token", "See CONNECTORS.md, Atlassian section")
        path = env.get("REPO_LOCAL_PATH", "")
        if path and not (Path(path) / ".git").exists():
            line(WARNING, "REPO_LOCAL_PATH does not point to a git clone", "Check the path or leave it empty")
    roles = [r.strip() for r in (env.get("PERMISSIONS_ROLES") or "").split(",") if r.strip()]
    for r in roles:
        key = re.sub(r"[^A-Z0-9]+", "_", r.upper().translate(str.maketrans("ÁÉÍÓÚÑÜ", "AEIOUNU"))).strip("_")
        lacking = missing([f"PERMISSIONS_{key}_USER", f"PERMISSIONS_{key}_PASSWORD"], env)
        if lacking and not env.get(f"PERMISSIONS_{key}_TOKEN"):
            line(MISSING, f"Role {r}: missing {', '.join(lacking)}", "Fill them in the .env (Permissions by role block)")
    if roles:
        line(OK, f"Permissions: {len(roles)} role(s) configured")
    for name, pattern, where in (("SLACK_WEBHOOK_URL", r"^https://hooks\.slack\.com/", "Slack (Incoming Webhook)"),
                                 ("TEAMS_WEBHOOK_URL", r"^https://", "Teams (Workflows)")):
        value = env.get(name, "")
        if not value:
            continue
        if re.match(pattern, value):
            line(OK, f"Notifications to {where}")
        else:
            line(MISSING, f"{name} does not have the expected {where} format", "Copy the webhook URL as is (see .env.example)")
    urls = [u.strip() for u in (env.get("MONITORING_URLS") or "").split(",") if u.strip()]
    bad = [u for u in urls if not is_url(u)]
    if bad:
        line(MISSING, f"MONITORING_URLS has {len(bad)} invalid URL(s)", "Comma-separated, with http:// or https://")
    elif urls or (ROOT / "input" / "monitoring.json").exists():
        line(OK, "Synthetic monitoring configured")


def check_connectors(ctx):
    section("connectors", "MCP connectors")
    env, enabled, local = ctx["env"], ctx["enabled"], ctx["local"]
    for name in dict.fromkeys(enabled + local):
        required = CONNECTOR_VARIABLES.get(name, [])
        if name == "azure-devops" and (env.get("ADO_AUTHENTICATION") or "pat").lower() != "pat":
            required = ["ADO_ORGANIZATION"]  # interactive / azcli / env: no PAT
        lacking = missing(required, env)
        origin = " (enabled with npm run connector)" if name in local else ""
        if lacking:
            line(MISSING, f"{name}{origin}: missing {', '.join(lacking)}", "Fill them in the .env (see CONNECTORS.md)")
        elif name in OAUTH_CONNECTORS or (name in OPTIONAL_TOKEN_CONNECTORS and not env.get(OPTIONAL_TOKEN_CONNECTORS[name])):
            line(OK, f"{name}{origin} (authorized with your account from /mcp the first time)")
        else:
            line(OK, name + origin)
    note("To add Azure DevOps, Figma, GitHub, GitLab, Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack, "
         "Shortcut, QMetry, AIO Tests, k0lmenaTMT or Appium: npm run connector")


def check_repo(ctx):
    section("repo", "k0lmenIA repository (git)")
    if not shutil.which("git"):
        line(WARNING, "git is not installed", "Install git: https://git-scm.com/downloads")
        return
    line(OK, "git installed")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
    for pattern, what in ((".env", "the .env (secrets)"), ("/input/documentation/", "the project documentation")):
        if pattern in ignored:
            line(OK, f".gitignore covers {what}")
        else:
            line(MISSING, f".gitignore does not cover {what}", f"Add {pattern} to .gitignore")
    if command("git", "-C", str(ROOT), "config", "user.email", timeout=5):
        line(OK, "git identity configured (for commits)")
    else:
        line(WARNING, "git without user.email (you won't be able to commit)", 'git config user.email "you@mail" && git config user.name "Your name"')


def check_extras(ctx):
    section("extras", "Portal, monitoring and evals")
    if (ROOT / "output").is_dir():
        line(OK, "output/ exists (the output/index.html portal regenerates on its own)")
    else:
        line(WARNING, "output/ does not exist", "It is created on its own with the first report; or mkdir output")
    for wf, what in (("monitoring.yml", "scheduled synthetic monitoring"), ("evals.yml", "manual evals in CI")):
        if (ROOT / ".github" / "workflows" / wf).exists():
            line(OK, f"Workflow {wf} ({what})")
        else:
            line(WARNING, f".github/workflows/{wf} is missing ({what})", "Restore it from the repository")
    if shutil.which("claude"):
        line(OK, "Claude Code CLI available (to run the evals: npm run evals)")
    else:
        line(WARNING, "Can't find the claude command (only needed to run the evals)", "Install Claude Code (see README)")


SECTIONS = {
    "python": check_python, "node": check_node, "tools": check_tools, "fonts": check_sources,
    "env": check_env, "integrations": check_integrations, "connectors": check_connectors,
    "repo": check_repo, "extras": check_extras,
}


def context(quick=False):
    file, env = read_environment()
    enabled = []
    for f in (ROOT / ".claude" / "settings.json", ROOT / ".claude" / "settings.local.json"):
        try:
            enabled += json.loads(f.read_text(encoding="utf-8")).get("enabledMcpjsonServers", [])
        except (OSError, ValueError):
            pass
    local = _local_connectors()
    return {"py": "python" if os.name == "nt" else "python3", "quick": quick, "file": file, "env": env,
            "enabled": enabled, "local": local, "connectors": set(enabled) | set(local)}


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Checks the k0lmenIA environment")
    ap.add_argument("--section", help=f"one or several, comma-separated: {', '.join(SECTIONS)}")
    ap.add_argument("--quick", action="store_true", help="skips the slow checks (network, Docker, Mailpit)")
    ap.add_argument("--json", action="store_true", help="JSON output")
    a = ap.parse_args(argv)
    chosen = [x.strip() for x in a.section.split(",")] if a.section else list(SECTIONS)
    invalid = [x for x in chosen if x not in SECTIONS]
    if invalid:
        ap.error(f"unknown section: {', '.join(invalid)} (options: {', '.join(SECTIONS)})")
    _OUTPUT["json"] = a.json
    summary.update(ok=0, warning=0, missing=0)
    RESULTS.clear()
    if not a.json:
        print("k0lmenIA · environment check" + (" (quick)" if a.quick else ""))
    ctx = context(a.quick)
    for name in chosen:
        SECTIONS[name](ctx)
    if a.json:
        print(json.dumps({"summary": summary, "results": RESULTS}, ensure_ascii=False, indent=2))
    else:
        print(f"\nResult: {summary['ok']} OK · {summary['warning']} warnings · {summary['missing']} missing")
        if summary["missing"]:
            print("Fix what is marked with X and run the doctor again.")
    return 1 if summary["missing"] else 0


def _responds(url, timeout=3):
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 (URL from the person's .env)
            return 200 <= r.status < 500
    except Exception:
        return False


def _local_connectors():
    """Connectors enabled with `npm run connector` (Claude Code local scope); names only."""
    try:
        data = json.loads((Path.home() / ".claude.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    key = str(ROOT).replace("\\", "/").lower()
    for path, project in (data.get("projects") or {}).items():
        if path.replace("\\", "/").lower() == key:
            return list((project.get("mcpServers") or {}).keys())
    return []


def _importable(module):
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def _playwright_folder():
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


if __name__ == "__main__":
    sys.exit(main())
