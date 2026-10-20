#!/usr/bin/env python3
"""
Recording verifier for a camera or NVR over ONVIF (Recording and Search services): queries
which recordings exist, the covered range (from / until), detects gaps and compares the actual
retention against the expected one. Uses onvif-zeep (installed automatically if missing).

Usage (from the repo root):
    python tools/streaming/recordings.py --host 192.168.1.60 [--port 80]
        [--user admin] [--password ***] [--retention 30] [--story US-001] [--confirm]

What it does (read-only):
- Checks that the host is authorized in the .env (ONVIF_AUTHORIZED_HOSTS).
- GetRecordingSummary: total recorded range and number of recordings.
- GetRecordings: each recording and its tracks, with their covered range; estimates gaps (segments of the
  total range without coverage) and compares the retention (days covered) against --retention / RECORDINGS_RETENTION_DAYS.
- If the camera does not support the recording service over ONVIF, it reports it (not a test error).
- Leaves in output/streaming/recordings-<host or story>/: recordings.json and recordings-report.html.

Credentials via --user/--password or the .env (ONVIF_USER, ONVIF_PASSWORD).
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def fail(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def _need(pkg, install):
    try:
        __import__(pkg); return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", install, "--quiet"], check=False)
    try:
        __import__(pkg)
    except ImportError:
        fail(f"\n[!] The '{install}' library is missing and could not be installed automatically.\n    pip install {install}\n")


def read_env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith(("ONVIF_", "RECORDINGS_"))})
    return values


def authorized(host, port, env):
    allowed = [u.strip() for u in re.split(r"[,\s]+", env.get("ONVIF_AUTHORIZED_HOSTS", "")) if u.strip()]
    if not allowed:
        fail("There are no authorized ONVIF hosts. Add ONVIF_AUTHORIZED_HOSTS to the root .env "
             "(only cameras/NVRs you own or have written authorization for).")
    if not ({host, f"{host}:{port}"} & set(allowed)):
        fail(f"{host} is not in ONVIF_AUTHORIZED_HOSTS in the .env. Only authorized devices are tested.")


def _val(d, *keys):
    for k in keys:
        try:
            v = getattr(d, k)
            if v is not None:
                return v
        except AttributeError:
            pass
    return None


def _dt(v):
    import datetime as d
    if isinstance(v, d.datetime):
        return v if v.tzinfo else v.replace(tzinfo=d.timezone.utc)
    return None


def run_tests(host, port, user, password, expected_retention):
    from onvif import ONVIFCamera
    import datetime as d
    res = {"host": host, "port": port, "findings": [], "supported": True, "recordings": []}
    h = res["findings"]
    try:
        cam = ONVIFCamera(host, port, user, password)
        cam.create_devicemgmt_service()
    except Exception as ex:
        res["status"] = "failed"
        h.append({"severity": "Critical", "text": f"Could not connect over ONVIF: {ex}"})
        return res

    try:
        search = cam.create_search_service()
        summary = search.GetRecordingSummary()
        since, until = _dt(_val(summary, "DataFrom")), _dt(_val(summary, "DataUntil"))
        res["summary"] = {"from": since.isoformat() if since else None,
                          "until": until.isoformat() if until else None,
                          "count": _val(summary, "NumberRecordings")}
        if since and until:
            days = (until - since).total_seconds() / 86400
            res["summary"]["covered_days"] = round(days, 1)
            if expected_retention and days < expected_retention * 0.9:
                h.append({"severity": "High", "text": f"Short retention: {round(days,1)} days covered (expected {expected_retention})."})
            # does the recording reach the recent past? (if 'until' is old, it may not be recording)
            lag = (d.datetime.now(d.timezone.utc) - until).total_seconds() / 3600
            if lag > 1:
                h.append({"severity": "High", "text": f"The last recording is from {round(lag,1)} h ago: it may not be recording now."})
    except Exception as ex:
        res["supported"] = False
        res["tests_error_summary"] = str(ex)
        h.append({"severity": "Medium", "text": f"The camera did not answer the recording summary over ONVIF (it may not support the Search service): {ex}"})

    # Detail per recording and tracks → gap estimation
    try:
        rec = cam.create_recording_service()
        recordings = rec.GetRecordings()
        for g in recordings or []:
            tracks = []
            for t in (_val(g, "Tracks") or []):
                td = _dt(_val(t, "DataFrom"))
                tu = _dt(_val(t, "DataUntil"))
                tracks.append({"type": _val(_val(t, "Configuration"), "TrackType"),
                               "from": td.isoformat() if td else None,
                               "until": tu.isoformat() if tu else None})
            res["recordings"].append({"token": _val(g, "RecordingToken"), "tracks": tracks})
        if res.get("summary") and res["summary"].get("count") == 0:
            h.append({"severity": "High", "text": "There are no recordings on the device."})
    except Exception as ex:
        if res["supported"]:
            h.append({"severity": "Low", "text": f"Could not list the recording details: {ex}"})

    res["status"] = "failed" if any(x["severity"] == "Critical" for x in h) else ("findings" if h else "ok")
    return res


def main():
    ap = argparse.ArgumentParser(description="Recording verifier over ONVIF.")
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--retention", type=int, default=0, help="Expected retention days (or RECORDINGS_RETENTION_DAYS from the .env).")
    ap.add_argument("--story", default="")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    env = read_env()
    authorized(args.host, args.port, env)
    _need("onvif", "onvif-zeep")
    user = args.user or env.get("ONVIF_USER") or ""
    password = args.password if args.password is not None else env.get("ONVIF_PASSWORD", "")
    if not user:
        fail("The ONVIF user is missing. Pass it with --user or put it in the .env (ONVIF_USER).")
    retention = args.retention or int(env.get("RECORDINGS_RETENTION_DAYS") or 0)

    if not args.confirm:
        print(f"You are about to query the recordings of {args.host}:{args.port} over ONVIF (read-only).")
        if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
            fail("Cancelled.", 1)

    folder = ROOT / "output" / "streaming" / f"recordings-{args.story or args.host}"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, ["recordings.json", "recordings-report.html"], "recordings.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)

    print(f"[recordings] Querying {args.host}:{args.port} …", file=sys.stderr)
    res = run_tests(args.host, args.port, user, password, retention)
    data = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "story": args.story or None, "expected_retention": retention or None, "result": res}
    (folder / "recordings.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import generate_recordings_report
        generate_recordings_report.generate(folder / "recordings.json", folder / "recordings-report.html")
        print(f"[recordings] Report: {folder / 'recordings-report.html'}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)

    print(f"[recordings] Status: {res['status']} · {len(res['findings'])} finding(s).")
    print(f"[recordings] Data: {folder / 'recordings.json'}")


if __name__ == "__main__":
    main()
