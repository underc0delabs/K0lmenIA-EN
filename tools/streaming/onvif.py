#!/usr/bin/env python3
"""
ONVIF control test of an IP camera: device information, profiles and stream URIs,
snapshot, PTZ (optional, moves the camera) and event capabilities (motion detection).
Uses the onvif-zeep library (installed automatically if missing). The verification of the video
itself (that the stream plays correctly) is done by tools/streaming/probe.py on the RTSP URI this returns.

Usage (from the repo root):
    python tools/streaming/onvif.py --host 192.168.1.50 [--port 80]
        [--user admin] [--password ***] [--story US-001] [--ptz] [--confirm]

What it does (read-only, except --ptz):
- Checks that the host is authorized in the .env (ONVIF_AUTHORIZED_HOSTS).
- GetDeviceInformation: brand, model, firmware, serial.
- GetProfiles + GetStreamUri: profiles and their RTSP URI; GetSnapshotUri: and downloads a test image.
- PTZ and event (motion detection) capabilities, without moving it.
- --ptz (action with side effects, requires --confirm): makes a minimal movement (pan) and stops it; if
  there are presets, it queries the list. It never leaves the camera moving.
- Leaves in output/streaming/onvif-<host or story>/: onvif.json and onvif-report.html.

Credentials come from --user/--password or from the .env (ONVIF_USER, ONVIF_PASSWORD); never from
production unless authorized. It does not try passwords or search for cameras: only the authorized host.
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
        __import__(pkg)
        return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", install, "--quiet"], check=False)
    try:
        __import__(pkg)
    except ImportError:
        fail(f"\n[!] The '{install}' library is missing and could not be installed automatically.\n"
             f"    Install it with:  pip install {install}\n")


def read_env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith("ONVIF_") or k.startswith("STREAMING_")})
    return values


def authorized(host, port, env):
    allowed = [u.strip() for u in re.split(r"[,\s]+", env.get("ONVIF_AUTHORIZED_HOSTS", "")) if u.strip()]
    if not allowed:
        fail("There are no authorized ONVIF hosts. Add to the root .env:\n"
             "  ONVIF_AUTHORIZED_HOSTS=192.168.1.50, camera.local\n"
             "(only cameras you own or have written authorization from their owners for).")
    candidates = {host, f"{host}:{port}"}
    if not (candidates & set(allowed)):
        fail(f"{host} is not in ONVIF_AUTHORIZED_HOSTS in the .env. Only authorized cameras are tested.")


def _val(d, *keys):
    for k in keys:
        try:
            v = getattr(d, k)
            if v is not None:
                return v
        except AttributeError:
            pass
    return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _onvif_date(sdt):
    """Builds a UTC datetime from the UTCDateTime structure of GetSystemDateAndTime."""
    import datetime as _dt
    try:
        u = _val(sdt, "UTCDateTime")
        d, t = _val(u, "Date"), _val(u, "Time")
        return _dt.datetime(int(_val(d, "Year")), int(_val(d, "Month")), int(_val(d, "Day")),
                            int(_val(t, "Hour")), int(_val(t, "Minute")), int(_val(t, "Second")),
                            tzinfo=_dt.timezone.utc)
    except Exception:
        return None


def clock_and_ntp(dev, res, h, env):
    """Clock drift (camera vs. real time), time zone and NTP, checked against the site standard."""
    import datetime as _dt
    drift_warn = _num(env.get("ONVIF_CLOCK_DRIFT_WARN_S")) or 60.0
    expected_tz = (env.get("ONVIF_EXPECTED_TZ") or "").strip()
    expected_ntp = (env.get("ONVIF_EXPECTED_NTP") or "").strip()

    # System date/time → clock drift
    try:
        sdt = dev.GetSystemDateAndTime()
        cam_dt = _onvif_date(sdt)
        tz = _val(_val(sdt, "TimeZone"), "TZ")
        dst = bool(_val(sdt, "DaylightSavings"))
        info = {"timezone": tz, "dst": dst, "type": _val(sdt, "DateTimeType")}
        if cam_dt:
            drift = abs((cam_dt - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
            info["clock_drift_s"] = round(drift, 1)
            if drift > drift_warn:
                h.append({"severity": "High", "text": f"Clock drift: the camera is {round(drift)}s off from real time (warning above {round(drift_warn)}s). It affects the time of recordings and events."})
        else:
            info["clock_drift_s"] = None
            h.append({"severity": "Low", "text": "Could not read the camera's date/time to measure the clock drift."})
        if expected_tz and tz and expected_tz.lower() not in str(tz).lower():
            h.append({"severity": "Medium", "text": f"Time zone differs from the site standard: {tz} (expected {expected_tz})."})
        res["clock"] = info
        res["tests"]["system_date_time"] = "ok"
    except Exception as ex:
        res["tests"]["system_date_time"] = "failed"
        h.append({"severity": "Medium", "text": f"GetSystemDateAndTime failed: {ex}"})

    # NTP
    try:
        ntp = dev.GetNTP()
        from_dhcp = bool(_val(ntp, "FromDHCP"))
        servers = []
        for group in ("NTPFromDHCP", "NTPManual"):
            for s in (_val(ntp, group) or []):
                servers.append(_val(s, "IPv4Address", "DNSname") or str(s))
        res["ntp"] = {"from_dhcp": from_dhcp, "servers": servers}
        res["tests"]["ntp"] = "ok"
        if not servers:
            h.append({"severity": "Medium", "text": "The camera has no NTP servers configured: the clock may drift over time."})
        elif expected_ntp and not any(expected_ntp.lower() in str(s).lower() for s in servers):
            h.append({"severity": "Low", "text": f"NTP differs from the site standard: {', '.join(servers)} (expected {expected_ntp})."})
    except Exception as ex:
        res["tests"]["ntp"] = "failed"
        h.append({"severity": "Low", "text": f"GetNTP failed: {ex}"})


def check_firmware(res, h, env):
    """Flags firmware that differs from the site standard (ONVIF_EXPECTED_FIRMWARE)."""
    expected = (env.get("ONVIF_EXPECTED_FIRMWARE") or "").strip()
    actual = (res.get("device") or {}).get("firmware")
    if expected and actual and expected.strip().lower() != str(actual).strip().lower():
        h.append({"severity": "Medium", "text": f"Firmware differs from the site standard: {actual} (expected {expected}). Check whether it is outdated."})


def download_snapshot(uri, user, password, folder):
    import requests
    from requests.auth import HTTPDigestAuth
    for auth in (HTTPDigestAuth(user, password), (user, password), None):
        try:
            r = requests.get(uri, auth=auth, timeout=10, stream=True)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                dest = folder / "snapshot.jpg"
                dest.write_bytes(r.content)
                return {"ok": True, "file": "snapshot.jpg", "bytes": len(r.content)}
        except Exception:
            continue
    return {"ok": False, "error": "Could not download the snapshot (auth or format)."}


def _parse_notification(nm):
    """From a NotificationMessage, gets the topic and whether it indicates motion (boolean SimpleItem set to true)."""
    topic = ""
    try:
        raw = getattr(getattr(nm, "Topic", None), "_value_1", None)
        if isinstance(raw, str):
            topic = raw
        elif raw is not None:
            topic = getattr(raw, "text", None) or (raw.itertext and "".join(raw.itertext())) or ""
        topic = str(topic).strip()
    except Exception:
        topic = ""
    motion = False
    try:
        el = getattr(getattr(nm, "Message", None), "_value_1", None)
        if el is not None and hasattr(el, "iter"):
            for e in el.iter():
                tag = getattr(e, "tag", "")
                if isinstance(tag, str) and tag.endswith("SimpleItem"):
                    name = (e.get("Name") or "").lower()
                    value = (e.get("Value") or "").lower()
                    if any(k in name for k in ("ismotion", "motion", "state", "isactive")) and value in ("true", "1"):
                        motion = True
    except Exception:
        pass
    return topic, motion


def live_events(cam, seconds):
    """Subscribes an ONVIF PullPoint and waits `seconds` for an event to arrive (e.g. motion)."""
    import datetime as _dt
    import time as _time
    res = {"requested_s": seconds, "subscription": None, "messages": 0, "motion": False, "topics": []}
    try:
        ev = cam.create_events_service()
        ev.CreatePullPointSubscription()
        pull = cam.create_pullpoint_service()
    except Exception as ex:
        res["subscription"] = "failed"
        res["error"] = str(ex)
        return res
    res["subscription"] = "ok"
    topics = set()
    end = _time.monotonic() + seconds
    try:
        while _time.monotonic() < end and not res["motion"]:
            remaining = min(10, max(1, int(end - _time.monotonic())))
            try:
                msgs = pull.PullMessages({"Timeout": _dt.timedelta(seconds=remaining), "MessageLimit": 100})
            except Exception:
                msgs = pull.PullMessages({"Timeout": f"PT{remaining}S", "MessageLimit": 100})
            for nm in (getattr(msgs, "NotificationMessage", None) or []):
                res["messages"] += 1
                topic, motion = _parse_notification(nm)
                if topic:
                    topics.add(topic)
                if motion:
                    res["motion"] = True
    except Exception as ex:
        res["error_pull"] = str(ex)
    finally:
        try:
            pull.Unsubscribe()
        except Exception:
            pass
    res["topics"] = sorted(topics)[:20]
    return res


def run_tests(host, port, user, password, folder, do_ptz, env, events_seconds=0):
    from onvif import ONVIFCamera
    res = {"host": host, "port": port, "findings": [], "tests": {}}
    h = res["findings"]

    try:
        cam = ONVIFCamera(host, port, user, password)
        dev = cam.create_devicemgmt_service()
    except Exception as ex:
        res["status"] = "failed"
        h.append({"severity": "Critical", "text": f"Could not connect over ONVIF: {ex}"})
        return res

    # Device information
    try:
        info = dev.GetDeviceInformation()
        res["device"] = {"brand": _val(info, "Manufacturer"), "model": _val(info, "Model"),
                         "firmware": _val(info, "FirmwareVersion"), "serial": _val(info, "SerialNumber")}
        res["tests"]["device_information"] = "ok"
    except Exception as ex:
        res["tests"]["device_information"] = "failed"
        h.append({"severity": "High", "text": f"GetDeviceInformation failed: {ex}"})

    # Capabilities
    try:
        caps = dev.GetCapabilities({"Category": "All"})
        res["capabilities"] = {"ptz": bool(_val(caps, "PTZ")), "events": bool(_val(caps, "Events")),
                               "media": bool(_val(caps, "Media")), "imaging": bool(_val(caps, "Imaging"))}
        res["tests"]["capabilities"] = "ok"
    except Exception as ex:
        res["tests"]["capabilities"] = "failed"
        h.append({"severity": "Medium", "text": f"GetCapabilities failed: {ex}"})

    # Clock (drift), time zone, NTP and firmware vs. the site standard
    clock_and_ntp(dev, res, h, env)
    check_firmware(res, h, env)

    # Profiles and stream / snapshot URIs
    profiles_out = []
    first_token = None
    try:
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        for p in profiles:
            token = _val(p, "token", "_token")
            if first_token is None:
                first_token = token
            entry = {"name": _val(p, "Name"), "token": token}
            try:
                uri = media.GetStreamUri({"StreamSetup": {"Stream": "RTP-Unicast",
                                          "Transport": {"Protocol": "RTSP"}}, "ProfileToken": token})
                entry["rtsp"] = _val(uri, "Uri")
            except Exception as ex:
                entry["rtsp_error"] = str(ex)
            profiles_out.append(entry)
        res["profiles"] = profiles_out
        res["tests"]["profiles"] = "ok"
        if not profiles_out:
            h.append({"severity": "High", "text": "The camera does not expose media profiles over ONVIF."})
    except Exception as ex:
        res["tests"]["profiles"] = "failed"
        h.append({"severity": "High", "text": f"GetProfiles failed: {ex}"})

    # Snapshot
    if first_token:
        try:
            snap_uri = media.GetSnapshotUri({"ProfileToken": first_token})
            uri = _val(snap_uri, "Uri")
            res["snapshot"] = {"uri": uri}
            res["snapshot"].update(download_snapshot(uri, user, password, folder))
            res["tests"]["snapshot"] = "ok" if res["snapshot"].get("ok") else "failed"
            if not res["snapshot"].get("ok"):
                h.append({"severity": "Medium", "text": "Could not download the camera snapshot."})
        except Exception as ex:
            res["tests"]["snapshot"] = "failed"
            h.append({"severity": "Medium", "text": f"GetSnapshotUri failed: {ex}"})

    # Events / motion detection (capability and, with --events N, live)
    try:
        if res.get("capabilities", {}).get("events"):
            ev = cam.create_events_service()
            props = ev.GetEventProperties()
            res["events"] = {"available": True, "topics": bool(_val(props, "TopicSet"))}
            res["tests"]["events"] = "ok"
            if events_seconds and events_seconds > 0:
                print(f"[onvif]   waiting for events {events_seconds}s (create motion in front of the camera) …", file=sys.stderr)
                live = live_events(cam, events_seconds)
                res["events"]["live"] = live
                if live.get("subscription") != "ok":
                    res["tests"]["events_live"] = "failed"
                    h.append({"severity": "Medium", "text": f"Could not subscribe to live events (pull-point): {live.get('error', 'no details')}"})
                elif live.get("motion"):
                    res["tests"]["events_live"] = "ok"
                else:
                    res["tests"]["events_live"] = "ok"
                    h.append({"severity": "Low", "text": f"No motion event arrived in {events_seconds}s ({live.get('messages', 0)} message(s) received). Did you create motion, and is detection enabled on the camera?"})
        else:
            res["events"] = {"available": False}
            res["tests"]["events"] = "n/a"
            if events_seconds and events_seconds > 0:
                h.append({"severity": "Low", "text": "Waiting for events was requested, but the camera does not declare an events capability over ONVIF."})
    except Exception as ex:
        res["tests"]["events"] = "failed"
        h.append({"severity": "Low", "text": f"Events service present but GetEventProperties failed: {ex}"})

    # PTZ
    if res.get("capabilities", {}).get("ptz") and first_token:
        try:
            ptz = cam.create_ptz_service()
            presets = ptz.GetPresets({"ProfileToken": first_token})
            res["ptz"] = {"presets": len(presets) if presets else 0}
            res["tests"]["ptz_presets"] = "ok"
            if do_ptz:
                ptz.ContinuousMove({"ProfileToken": first_token,
                                    "Velocity": {"PanTilt": {"x": 0.1, "y": 0.0}}})
                import time
                time.sleep(0.6)
                ptz.Stop({"ProfileToken": first_token, "PanTilt": True, "Zoom": True})
                res["ptz"]["movement"] = "ok (minimal pan, then stopped)"
                res["tests"]["ptz_move"] = "ok"
        except Exception as ex:
            res["tests"]["ptz_presets"] = "failed"
            h.append({"severity": "Medium", "text": f"PTZ failed: {ex}"})
    elif do_ptz:
        h.append({"severity": "Low", "text": "PTZ was requested, but the camera does not declare a PTZ capability."})

    res["status"] = "failed" if any(x["severity"] == "Critical" for x in h) else ("findings" if h else "ok")
    return res


def main():
    ap = argparse.ArgumentParser(description="ONVIF control test of an IP camera.")
    ap.add_argument("--host", required=True, help="IP or hostname of the camera.")
    ap.add_argument("--port", type=int, default=80, help="ONVIF port (80 by default).")
    ap.add_argument("--user", default=None, help="ONVIF user (or ONVIF_USER from the .env).")
    ap.add_argument("--password", default=None, help="ONVIF password (or ONVIF_PASSWORD from the .env).")
    ap.add_argument("--story", default="", help="US-XXX for traceability and the output folder.")
    ap.add_argument("--ptz", action="store_true", help="Makes a minimal PTZ movement (action with side effects; requires --confirm).")
    ap.add_argument("--events", type=int, default=0, help="Seconds to wait for live events (pull-point) to check motion detection (0 = off).")
    ap.add_argument("--confirm", action="store_true", help="Skips the confirmation (the person already authorized it).")
    args = ap.parse_args()

    env = read_env()
    authorized(args.host, args.port, env)
    _need("onvif", "onvif-zeep")
    _need("requests", "requests")

    user = args.user or env.get("ONVIF_USER") or ""
    password = args.password if args.password is not None else env.get("ONVIF_PASSWORD", "")
    if not user:
        fail("The ONVIF user is missing. Pass it with --user or put it in the .env (ONVIF_USER).")

    if args.ptz and not args.confirm:
        fail("--ptz moves the camera (action with side effects). Run again with --confirm if you are authorized.")
    if not args.confirm:
        print(f"You are about to query camera {args.host}:{args.port} over ONVIF (read-only).")
        if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
            fail("Cancelled.", 1)

    name = args.story or args.host
    folder = ROOT / "output" / "streaming" / f"onvif-{name}"
    folder.mkdir(parents=True, exist_ok=True)

    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, ["onvif.json", "onvif-report.html", "snapshot.jpg"], "onvif.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)

    print(f"[onvif] Querying {args.host}:{args.port} …", file=sys.stderr)
    events_seconds = args.events or int(env.get("ONVIF_EVENTS_WAIT_S") or 0)
    res = run_tests(args.host, args.port, user, password, folder, args.ptz, env, events_seconds)
    data = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "story": args.story or None,
        "ptz_executed": bool(args.ptz),
        "expected_events_s": events_seconds or None,
        "result": res,
    }
    (folder / "onvif.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        import generate_onvif_report
        generate_onvif_report.generate(folder / "onvif.json", folder / "onvif-report.html")
        print(f"[onvif] Report: {folder / 'onvif-report.html'}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)

    print(f"[onvif] Status: {res['status']} · {len(res['findings'])} finding(s).")
    print(f"[onvif] Data: {folder / 'onvif.json'}")


if __name__ == "__main__":
    main()
