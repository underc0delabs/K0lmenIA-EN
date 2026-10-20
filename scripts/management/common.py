"""Shared pieces of the integration with test management tools.

- Loading of the single .env at the k0lmenIA root.
- HTTP client with retries and --dry-run mode (shows the requests without sending them).
- Local traceability: which case (TC-001) is which key in the tool (PROJ-T12).
- Status normalization.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANAGEMENT_DIR = ROOT / "output" / "management"

# k0lmenIA statuses (CLAUDE.md) -> normalized status that every adapter understands.
STATUSES = {
    "passed": "passed", "pass": "passed",
    "failed": "failed", "fail": "failed",
    "blocked": "blocked",
    "pending": "pending", "skipped": "pending", "undefined": "pending",
    "ambiguous": "failed", "n/a": "pending",
    "in progress": "in_progress", "in_progress": "in_progress",
}


class ManagementError(Exception):
    """Error with a clear message for the person (shown without a traceback)."""


def need(pkg, install=None):
    """Same as in generate_cases.py: installs the library if it is missing or warns clearly."""
    install = install or pkg
    try:
        return __import__(pkg)
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", install, "--quiet"], check=False)
    try:
        return __import__(pkg)
    except ImportError:
        sys.exit(f"\n[!] The library '{install}' is missing and could not be installed automatically.\n"
                 f"    Install the dependencies with:  pip install -r requirements.txt\n")


def load_env():
    """Loads the root .env without overriding variables already defined in the environment
    (same rules as k0lmena: export, quotes, trailing comments, BOM)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import load_env as _load
    _load()


def env(name, required=True, default=""):
    value = os.environ.get(name, "").strip() or default
    if required and not value:
        raise ManagementError(f"The variable {name} is missing from the root .env (see .env.example).")
    return value


def normalize_status(status):
    key = (status or "").strip().lower()
    if key not in STATUSES:
        raise ManagementError(f"Unknown status: '{status}'.")
    return STATUSES[key]


def _retry_wait(retry_after, attempt):
    """Seconds to wait according to Retry-After (a number or an HTTP date); if missing, exponential backoff."""
    if retry_after:
        try:
            return max(int(float(retry_after)), 1)
        except ValueError:
            from email.utils import parsedate_to_datetime
            try:
                return max(int((parsedate_to_datetime(retry_after).timestamp() - time.time())), 1)
            except (TypeError, ValueError):
                pass
    return 2 ** attempt


class Http:
    """requests with retries on 429/5xx and dry-run mode."""

    def __init__(self, base, headers=None, dry_run=False, name="api", interval=0.0):
        self.base = base.rstrip("/")
        self.headers = headers or {}
        self.dry_run = dry_run
        self.name = name
        self.interval = interval  # minimum seconds between requests (the tool's rate limit)
        self._last = 0.0
        self._counter = 0

    def _url(self, path):
        return path if path.startswith("http") else f"{self.base}/{path.lstrip('/')}"

    def request(self, method, path, *, json_body=None, params=None, files=None, data=None,
                headers=None, expected=(200, 201, 204)):
        url = self._url(path)
        hdrs = {**self.headers, **(headers or {})}
        if self.dry_run:
            self._counter += 1
            body = json.dumps(json_body, ensure_ascii=False)[:600] if json_body is not None else ""
            extra = f" files={list(files)}" if files else ""
            print(f"[dry-run] {self.name} {method} {url} {params or ''} {body}{extra}")
            return {"__dry_run__": True, "id": f"DRY-{self._counter}", "ID": f"DRY-{self._counter}",
                    "key": f"DRY-{self._counter}"}
        requests = need("requests")
        # Attachments are read only once: an open file already read on the first attempt
        # would arrive empty on the retry.
        if files:
            files = {k: tuple(v[:1]) + ((v[1].read() if hasattr(v[1], "read") else v[1]),) + tuple(v[2:])
                     if isinstance(v, tuple) else (v.read() if hasattr(v, "read") else v)
                     for k, v in files.items()}
        r = None
        for attempt in range(5):
            wait = self.interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            try:
                r = requests.request(method, url, json=json_body, params=params, files=files,
                                     data=data, headers=hdrs, timeout=120)
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt == 4:
                    raise ManagementError(f"{self.name}: {method} {url} did not respond ({type(e).__name__}). "
                                          "Check the connection or the URL and try again.")
                time.sleep(min(2 ** attempt, 30))
                continue
            if r.status_code in (429, 502, 503, 504) and attempt < 4:
                time.sleep(min(_retry_wait(r.headers.get("Retry-After"), attempt), 30))
                continue
            break
        if r.status_code not in expected:
            raise ManagementError(f"{self.name}: {method} {url} responded {r.status_code}: {r.text[:800]}")
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return {"text": r.text}

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def put(self, path, **kw):
        return self.request("PUT", path, **kw)


class Traceability:
    """output/management/<story or name>-<tool>.json

    {
      "tool": "xray-cloud", "project": "PROJ", "story": "PROJ-12",
      "folder": {"path": "/US-001 Signup", "id": "..."},
      "cases": {"TC-001": {"key": "PROJ-45", "id": "10045", "title": "..."}},
      "cycles": [{"key": "PROJ-60", "id": "...", "name": "...", "date": "..."}]
    }
    """

    def __init__(self, name, tool):
        if not re.match(r"^[\w.-]+$", str(name)) or str(name).startswith("."):
            raise ManagementError(f"Invalid traceability name: {name!r} (use something like US-001).")
        MANAGEMENT_DIR.mkdir(parents=True, exist_ok=True)
        self.path = MANAGEMENT_DIR / f"{name}-{tool}.json"
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = {"tool": tool, "cases": {}, "cycles": []}

    def save(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def key_of(self, case_id):
        return (self.data["cases"].get(case_id) or {}).get("key")


def output(data):
    """Every command ends by printing a JSON: the agent reads it."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the Windows console is not UTF-8 by default
    print(json.dumps(data, ensure_ascii=False, indent=2))
