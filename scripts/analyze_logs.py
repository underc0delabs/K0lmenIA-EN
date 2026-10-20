#!/usr/bin/env python3
"""
Analyzes application logs (log-analyst agent): groups the errors by signature, builds the timeline
and cross-references them with the scenarios of a k0lmena run to find the server error behind each failure.

Usage (from the repo root):
    python scripts/analyze_logs.py --logs "input/logs/*.log,input/logs/nginx/error.log*" [--run web|api|mobile|<cucumber-report.json>]
        [--from 2026-10-11T10:00 --until 2026-10-11T11:00] [--zone -03:00] [--margin-s 10] [--name US-001]

Formats it understands (they mix without problems): lines with an ISO date (2026-10-11 10:22:33,123 / ...T10:22:33Z),
nginx and Apache access logs ([11/Oct/2026:10:22:33 -0300] "GET /x" 500), nginx errors (2026/10/11
10:22:33), syslog (Oct 11 10:22:33) and JSON per line ({"time"/"timestamp"/"@timestamp", "level", "message"}).
Stack traces (lines that continue with "at ...", "Caused by", "File ...", "Traceback", indentation) are attached to
their error. .gz files too.

What it builds:
  - signatures: each error or warning normalized (without numbers, ids, uuids, emails or quoted texts), with
    how many times it appeared, the first and the last time, the files and an example with its stack trace;
  - the timeline per minute;
  - with --run: each failed scenario with the errors that happened while it ran (the common k0lmena steps
    save the start and the end of each scenario); without --from/--until, the run's window (± 5 minutes) is analyzed.
Dates without a time zone are taken as local time (or the one in --zone).

Leaves output/logs/<name>/ with logs.json and logs-report.html; the previous analysis moves to history/ (last 5).
"""
import argparse
import datetime as dt
import glob
import gzip
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _history  # noqa: E402

K0 = ROOT / "tools" / "k0lmena" / "reports"
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS.update({"ene": 1, "abr": 4, "ago": 8, "dic": 12})  # Spanish-locale abbreviations, also accepted
R_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:[.,](\d{1,6}))?\s*(Z|[+-]\d{2}:?\d{2})?")
R_ACCESS = re.compile(r"\[(\d{2})/(\w{3})/(\d{4}):(\d{2}):(\d{2}):(\d{2}) ([+-]\d{4})\]")
R_SLASHES = re.compile(r"(\d{4})/(\d{2})/(\d{2}) (\d{2}):(\d{2}):(\d{2})")
R_SYSLOG = re.compile(r"^(\w{3}) +(\d{1,2}) (\d{2}):(\d{2}):(\d{2})")
R_LEVEL = re.compile(r"\b(FATAL|CRITICAL|CRIT|ERROR|ERR|SEVERE|WARNING|WARN|NOTICE|INFO|DEBUG|TRACE)\b", re.I)
R_HTTP = re.compile(r'"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS) ([^ "]+)[^"]*" (\d{3})')
R_EXC = re.compile(r"(Exception|Traceback|Error:|\bat [\w.$]+\(|Unhandled|panic:|Segmentation fault|OutOfMemory|ECONNREFUSED|timed? ?out)", re.I)
# Lines that continue the previous error: Java, Python, Node and .NET stack traces.
R_CONTINUATION = re.compile(r"^(\s+|\tat |at |Caused by|\.\.\. \d+ more|File \"|Traceback|  File|\s*\^|[\w.$]+(Exception|Error)(:|\s*$))")
LEVEL_NORM = {"fatal": "Error", "critical": "Error", "crit": "Error", "error": "Error", "err": "Error", "severe": "Error",
              "warning": "Warning", "warn": "Warning", "notice": "Info", "info": "Info", "debug": "Info", "trace": "Info"}


def _tz(text, zone):
    if not text:
        return zone
    if text == "Z":
        return dt.timezone.utc
    t = text.replace(":", "")
    sign = -1 if t[0] == "-" else 1
    return dt.timezone(sign * dt.timedelta(hours=int(t[1:3]), minutes=int(t[3:5])))


def date_of(line, zone):
    """(datetime with zone, text of the date) of a line, or (None, None)."""
    m = R_ISO.search(line)
    if m:
        y, mo, d, h, mi, s, frac, tz = m.groups()
        micro = int((frac or "0").ljust(6, "0")[:6])
        return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), micro, tzinfo=_tz(tz, zone)), m.group(0)
    m = R_ACCESS.search(line)
    if m:
        d, mon, y, h, mi, s, tz = m.groups()
        return dt.datetime(int(y), MONTHS.get(mon.lower()[:3], 1), int(d), int(h), int(mi), int(s), tzinfo=_tz(tz, zone)), m.group(0)
    m = R_SLASHES.search(line)
    if m:
        y, mo, d, h, mi, s = m.groups()
        return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(s), tzinfo=zone), m.group(0)
    m = R_SYSLOG.match(line)
    if m and m.group(1).lower()[:3] in MONTHS:
        mon, d, h, mi, s = m.groups()
        return dt.datetime(dt.date.today().year, MONTHS[mon.lower()[:3]], int(d), int(h), int(mi), int(s), tzinfo=zone), m.group(0)
    return None, None


def signature(message):
    s = re.sub(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<uuid>", message, flags=re.I)
    s = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "<email>", s)
    s = re.sub(r"\b\d{1,3}(\.\d{1,3}){3}(:\d+)?\b", "<ip>", s)
    s = re.sub(r"\b0x[0-9a-f]+\b|\b[0-9a-f]{12,}\b", "<hex>", s, flags=re.I)
    s = re.sub(r"(['\"])(?:(?!\1).){1,80}\1", r"\1<s>\1", s)
    s = re.sub(r"\?[^\s\"]*", "?<q>", s)
    s = re.sub(r"\d+", "<n>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180]


def read_file(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()


def entries(paths, zone):
    """One entry per event (with its stack trace attached)."""
    output, sources = [], []
    for path in paths:
        try:
            lines = read_file(path)
        except OSError as e:
            print(f"[!] Could not read {path}: {e}", file=sys.stderr)
            continue
        sources.append({"file": str(path), "lines": len(lines)})
        current = None
        for line in lines:
            if not line.strip():
                continue
            if current and R_CONTINUATION.match(line) and not R_ISO.match(line.strip()):
                current["stack"].append(line.rstrip())
                continue
            level, message, ts, ts_txt = None, line.strip(), None, None
            if line.lstrip().startswith("{"):
                try:
                    j = json.loads(line)
                    t = j.get("time") or j.get("timestamp") or j.get("@timestamp") or j.get("ts") or ""
                    ts, ts_txt = date_of(str(t), zone) if t else (None, None)
                    level = str(j.get("level") or j.get("severity") or j.get("lvl") or "").lower()
                    message = str(j.get("message") or j.get("msg") or j.get("error") or line)
                    if j.get("stack") or j.get("stack_trace"):
                        current = None
                except ValueError:
                    pass
            if ts is None:
                ts, ts_txt = date_of(line, zone)
            http = R_HTTP.search(line)
            if http:
                code = int(http.group(3))
                level = "error" if code >= 500 else "warn" if code >= 400 else "info"
                message = f"{http.group(1)} {http.group(2)} → {code}"
            if not level:
                m = R_LEVEL.search(line[:160])
                level = m.group(1).lower() if m else ("error" if R_EXC.search(line) else "info")
            if ts_txt and not http:
                message = message.replace(ts_txt, "").strip(" -|[]:")
            clean = re.sub(r"^\W*" + R_LEVEL.pattern + r"\s*", "", message, flags=re.I)
            clean = re.sub(r"^(?:\[[^\]]{0,60}\]\s*)+", "", clean).strip()  # [thread] [request-id]
            message = clean or message
            current = {"ts": ts, "level": LEVEL_NORM.get(level, "Info"), "message": message[:500], "file": Path(path).name, "stack": [], "line": line[:500]}
            output.append(current)
    return output, sources


def run_times(arg):
    """Scenarios of a cucumber-report.json with their start and end (k0lmena TIME attachment)."""
    import base64
    paths = []
    for x in (arg or "").split(","):
        x = x.strip()
        if not x:
            continue
        paths.append(K0 / x / "cucumber-report.json" if x in ("web", "api", "mobile") else Path(x))
    output = []
    for r in paths:
        try:
            features = json.loads(Path(r).read_text(encoding="utf-8") or "[]")
        except (OSError, ValueError):
            print(f"[!] Could not read the run {r}", file=sys.stderr)
            continue
        for f in features:
            for sc in f.get("elements") or []:
                if sc.get("type") == "background":
                    continue
                tags = [t["name"].lstrip("@") for t in (f.get("tags") or []) + (sc.get("tags") or [])]
                statuses = [(p.get("result") or {}).get("status") for p in sc.get("steps") or []]
                start = end = None
                error = ""
                for p in sc.get("steps") or []:
                    if (p.get("result") or {}).get("status") == "failed" and not error:
                        error = re.sub(r"\x1b\[[0-9;]*m", "", (p["result"].get("error_message") or "")).strip().splitlines()[0][:200] if p["result"].get("error_message") else ""
                    for emb in p.get("embeddings") or []:
                        if emb.get("mime_type") != "text/plain":
                            continue
                        try:
                            t = base64.b64decode(emb["data"]).decode("utf-8", "replace")
                        except (ValueError, KeyError):
                            continue
                        m = re.search(r"TIME: start=(\S+) end=(\S+)", t)
                        if m:
                            start, end = dt.datetime.fromisoformat(m.group(1).replace("Z", "+00:00")), dt.datetime.fromisoformat(m.group(2).replace("Z", "+00:00"))
                output.append({"scenario": sc.get("name"), "uri": f.get("uri"), "line": sc.get("line"),
                               "story": next((t for t in tags if re.fullmatch(r"US-\d+", t, re.I)), None),
                               "case": next((t for t in tags if re.fullmatch(r"TC(-API)?-\d+", t)), None),
                               "status": "Failed" if "failed" in statuses else "Passed" if statuses and all(s == "passed" for s in statuses) else "Other",
                               "error": error, "start": start, "end": end})
    return output


def analyze(ents, scenarios, since, until, margin):
    if since or until:
        ents = [x for x in ents if x["ts"] is None or ((not since or x["ts"] >= since) and (not until or x["ts"] <= until))]
    problems = [x for x in ents if x["level"] in ("Error", "Warning")]
    groups = defaultdict(list)
    for x in problems:
        groups[(x["level"], signature(x["message"]))].append(x)
    signatures = []
    for (level, f), xs in sorted(groups.items(), key=lambda kv: (kv[0][0] != "Error", -len(kv[1]))):
        with_ts = [x for x in xs if x["ts"]]
        ex = next((x for x in xs if x["stack"]), xs[0])
        signatures.append({"level": level, "signature": f, "count": len(xs), "example": ex["message"], "stack": ex["stack"][:25],
                           "first": min(x["ts"] for x in with_ts).astimezone().isoformat() if with_ts else None, "last": max(x["ts"] for x in with_ts).astimezone().isoformat() if with_ts else None,
                           "files": sorted({x["file"] for x in xs}), "exception": next((m.group(0) for x in xs for m in [re.search(r"\b[\w.]*(Exception|Error)\b", x["message"] + " " + " ".join(x["stack"][:2]))] if m), None)})
    for i, fi in enumerate(signatures):
        fi["id"] = f"L-{i + 1:02d}"
    by_signature = {(fi["level"], fi["signature"]): fi["id"] for fi in signatures}
    per_minute = Counter()
    for x in problems:
        if x["ts"]:
            per_minute[(x["ts"].astimezone().strftime("%Y-%m-%d %H:%M"), x["level"])] += 1
    minutes = sorted({k[0] for k in per_minute})
    timeline = [{"minute": m, "errors": per_minute[(m, "Error")], "warnings": per_minute[(m, "Warning")]} for m in minutes]
    # Cross-reference with the scenarios: errors while each one ran (with margin).
    crossings = []
    for e in scenarios:
        if not e["start"]:
            continue
        ini, fin = e["start"] - dt.timedelta(seconds=margin), e["end"] + dt.timedelta(seconds=margin)
        in_window = [x for x in problems if x["ts"] and ini <= x["ts"] <= fin]
        c = Counter(by_signature[(x["level"], signature(x["message"]))] for x in in_window)
        crossings.append({**{k: e[k] for k in ("scenario", "uri", "line", "story", "case", "status", "error")},
                          "start": e["start"].astimezone().isoformat(), "end": e["end"].astimezone().isoformat(),
                          "errors": [{"signature": fid, "count": n} for fid, n in c.most_common(8)],
                          "lines": [x["line"] for x in in_window if x["level"] == "Error"][:8]})
    for fi in signatures:
        fi["scenarios"] = [f'{c["case"] or ""} {c["scenario"]}'.strip() for c in crossings if any(x["signature"] == fi["id"] for x in c["errors"])]
    return ents, signatures, timeline, crossings


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Application log analysis")
    ap.add_argument("--logs", help="comma-separated files or patterns (input/logs/*.log)")
    ap.add_argument("--run", help="web, api, mobile or the path to a cucumber-report.json (several, comma-separated)")
    ap.add_argument("--from")
    ap.add_argument("--until")
    ap.add_argument("--zone", help="time zone of the dates without a zone (for example -03:00); local by default")
    ap.add_argument("--margin-s", type=int, default=10, help="seconds before and after each scenario")
    ap.add_argument("--name", help="output folder in output/logs/ (by default 'app')")
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument("--output")
    a = ap.parse_args()
    since_arg, until_arg = getattr(a, "from"), a.until
    folder = Path(a.output) if a.output else ROOT / "output" / "logs" / (a.name or "app")
    data_file = folder / "logs.json"
    if not a.report_only:
        if not a.logs:
            sys.exit("Tell me which logs to analyze: --logs input/logs/app.log (or a pattern like input/logs/*.log).")
        paths = sorted({Path(x) for p in a.logs.split(",") for x in (glob.glob(p.strip()) or [p.strip()]) if Path(x).is_file()})
        if not paths:
            sys.exit(f"Found no log files in: {a.logs}")
        zone = _tz(a.zone, None) if a.zone else dt.datetime.now().astimezone().tzinfo
        ents, sources = entries(paths, zone)
        scenarios = run_times(a.run) if a.run else []
        conv = lambda s: dt.datetime.fromisoformat(s).replace(tzinfo=dt.datetime.fromisoformat(s).tzinfo or zone) if s else None
        since, until = conv(since_arg), conv(until_arg)
        with_t = [e for e in scenarios if e["start"]]
        if with_t and not (since or until):
            since = min(e["start"] for e in with_t) - dt.timedelta(minutes=5)
            until = max(e["end"] for e in with_t) + dt.timedelta(minutes=5)
        ents, signatures, timeline, crossings = analyze(ents, scenarios, since, until, a.margin_s)
        failed = [c for c in crossings if c["status"] == "Failed"]
        now = dt.datetime.now()
        data = {"name": a.name or "app", "date": now.isoformat(timespec="seconds"), "stamp": now.strftime("%Y%m%d-%H%M%S"),
                "sources": sources, "run": a.run, "window": {"from": since.astimezone().isoformat() if since else None, "until": until.astimezone().isoformat() if until else None},
                "summary": {"files": len(sources), "lines": sum(f["lines"] for f in sources), "events": len(ents),
                            "errors": sum(f["count"] for f in signatures if f["level"] == "Error"), "warnings": sum(f["count"] for f in signatures if f["level"] == "Warning"),
                            "signatures": len(signatures), "error_signatures": sum(1 for f in signatures if f["level"] == "Error"),
                            "scenarios": len(scenarios), "scenarios_with_time": len(with_t), "failed": len(failed),
                            "failed_with_errors": sum(1 for c in failed if c["errors"]), "no_date": sum(1 for x in ents if x["ts"] is None)},
                "signatures": signatures, "timeline": timeline, "scenarios": crossings}
        _history.archive(folder, ["logs.json", "analysis.json", "logs-report.html"], "logs.json")
        folder.mkdir(parents=True, exist_ok=True)
        data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        r = data["summary"]
        print(f'Lines: {r["lines"]} in {r["files"]} file(s) · errors: {r["errors"]} ({r["error_signatures"]} signatures) · warnings: {r["warnings"]}')
        if scenarios:
            print(f'Scenarios: {r["scenarios"]} ({r["scenarios_with_time"]} with time) · failed: {r["failed"]}, with server errors: {r["failed_with_errors"]}')
        for f in signatures[:5]:
            print(f'  {f["id"]} {f["level"]:11} ×{f["count"]:<4} {f["example"][:90]}')
    args = [sys.executable, str(ROOT / "scripts" / "generate_logs_report.py"), str(data_file), str(folder / "logs-report.html")]
    if (folder / "analysis.json").exists():
        args += ["--analysis", str(folder / "analysis.json")]
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    print(res.stdout.strip() or res.stderr.strip())


if __name__ == "__main__":
    main()
