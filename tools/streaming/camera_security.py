#!/usr/bin/env python3
"""
PASSIVE security analysis of IP cameras / NVRs: checks open ports and insecure services
(Telnet, FTP, HTTP without TLS, RTSP without authentication) and records the firmware so its
CVEs can be reviewed. It does not try default credentials unless explicitly enabled on a device you own.

Usage (from the repo root):
    python tools/streaming/camera_security.py --host 192.168.1.50 [--story US-001]
        [--onvif-user admin --onvif-password ***] [--confirm]
    (--host accepts several, comma-separated)

What it does (read-only, non-intrusive):
- Checks that each host is authorized in the .env (AUTHORIZED_CAMERAS).
- Scans well-known camera ports (TCP connect, no attack payloads).
- Detects insecure services: open Telnet/FTP, HTTP without HTTPS, RTSP that answers DESCRIBE without auth.
- If ONVIF credentials are given, reads the firmware and reminds you to check its CVEs (it keeps no CVE database).
- Leaves in output/streaming/camera-security-<host or story>/: camera-security.json and the report.

It does no DoS, brute force or exploitation. It does not try default passwords (that would be another mode,
only on devices you own). Same approach as the security-analyst's passive ZAP scan.
"""
import argparse
import datetime
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Well-known camera/NVR ports and what they mean.
PORTS = {
    21: ("FTP", "insecure"), 23: ("Telnet", "insecure"), 22: ("SSH", "ok"),
    80: ("HTTP", "review"), 443: ("HTTPS", "ok"), 554: ("RTSP", "review"),
    8000: ("HTTP alt / SDK", "review"), 8080: ("HTTP alt", "review"), 8554: ("RTSP alt", "review"),
    37777: ("Dahua SDK", "review"), 34567: ("NVR (Sofia)", "review"), 9000: ("HTTP alt", "review"),
}


def fail(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def read_env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith(("AUTHORIZED_CAMERAS", "ONVIF_"))})
    return values


def authorized(host, env):
    allowed = [u.strip() for u in re.split(r"[,\s]+", env.get("AUTHORIZED_CAMERAS", "")) if u.strip()]
    if not allowed:
        fail("There are no authorized cameras. Add to the root .env:\n"
             "  AUTHORIZED_CAMERAS=192.168.1.50, 192.168.1.51\n"
             "(only devices you own or have written authorization from their owners for).")
    # accepts host or host:port in the list
    if not any(host == a or a.startswith(host + ":") for a in allowed):
        fail(f"{host} is not in AUTHORIZED_CAMERAS in the .env. Only authorized cameras are analyzed.")


def open_port(host, port, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    except OSError:
        return False
    finally:
        s.close()


def rtsp_no_auth(host, port=554, timeout=2.0):
    """Sends a DESCRIBE without credentials. 200 = answers without asking for auth (insecure); 401 = asks for auth (ok)."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            s.settimeout(timeout)
            request = (f"DESCRIBE rtsp://{host}:{port}/ RTSP/1.0\r\nCSeq: 1\r\n"
                       "User-Agent: k0lmenIA\r\nAccept: application/sdp\r\n\r\n")
            s.sendall(request.encode())
            resp = s.recv(1024).decode("latin-1", "ignore")
        m = re.search(r"RTSP/1\.0 (\d{3})", resp)
        code = int(m.group(1)) if m else None
        return code, resp.splitlines()[0] if resp else ""
    except OSError:
        return None, ""


def onvif_firmware(host, env):
    user = env.get("ONVIF_USER")
    password = env.get("ONVIF_PASSWORD", "")
    if not user:
        return None
    try:
        from onvif import ONVIFCamera
    except ImportError:
        return None
    for port in (80, 8000):
        try:
            cam = ONVIFCamera(host, port, user, password)
            info = cam.create_devicemgmt_service().GetDeviceInformation()
            return {"brand": getattr(info, "Manufacturer", None), "model": getattr(info, "Model", None),
                    "firmware": getattr(info, "FirmwareVersion", None)}
        except Exception:
            continue
    return None


def analyze_host(host, env):
    res = {"host": host, "open_ports": [], "findings": []}
    h = res["findings"]
    open_list = []
    for port, (name, rating) in sorted(PORTS.items()):
        if open_port(host, port):
            open_list.append({"port": port, "service": name})
            if rating == "insecure":
                h.append({"severity": "High", "text": f"{name} open (port {port}): insecure service, it should be disabled."})
    res["open_ports"] = open_list
    ports = {p["port"] for p in open_list}

    # HTTP without HTTPS
    if 80 in ports and 443 not in ports:
        h.append({"severity": "Medium", "text": "HTTP (80) open without HTTPS (443): the panel travels unencrypted."})

    # RTSP without authentication
    if 554 in ports:
        code, line = rtsp_no_auth(host, 554)
        res["rtsp"] = {"code": code, "response": line}
        if code == 200:
            h.append({"severity": "High", "text": "RTSP (554) answers DESCRIBE without asking for authentication: the stream is accessible without credentials."})
        elif code == 401:
            pass  # asks for auth: correct
        elif code is not None:
            h.append({"severity": "Low", "text": f"RTSP (554) answered {code} to a DESCRIBE without auth (review manually)."})

    # Firmware → CVE reminder (no CVE database of its own)
    fw = onvif_firmware(host, env)
    if fw:
        res["device"] = fw
        if fw.get("firmware"):
            h.append({"severity": "Low", "text": f"Firmware {fw.get('brand') or ''} {fw.get('model') or ''} {fw['firmware']}: check known CVEs for that version."})

    res["status"] = "failed" if any(x["severity"] == "Critical" for x in h) else ("findings" if h else "ok")
    return res


def main():
    ap = argparse.ArgumentParser(description="Passive security analysis of IP cameras.")
    ap.add_argument("--host", required=True, help="IP/hostname of the camera (several, comma-separated).")
    ap.add_argument("--story", default="")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    env = read_env()
    hosts = [x.strip() for x in args.host.split(",") if x.strip()]
    for hst in hosts:
        authorized(hst, env)

    if not args.confirm:
        print("You are about to analyze these cameras (passive, no attacks):")
        for hst in hosts:
            print(f"  - {hst}")
        if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
            fail("Cancelled.", 1)

    folder = ROOT / "output" / "streaming" / f"camera-security-{args.story or hosts[0]}"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, ["camera-security.json", "camera-security-report.html"], "camera-security.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)

    results = []
    for hst in hosts:
        print(f"[camera-security] {hst} …", file=sys.stderr)
        results.append(analyze_host(hst, env))

    data = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "story": args.story or None, "hosts": results,
            "summary": {"total": len(results),
                        "ok": sum(1 for r in results if r["status"] == "ok"),
                        "with_findings": sum(1 for r in results if r["status"] != "ok")}}
    (folder / "camera-security.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import generate_camera_security_report
        generate_camera_security_report.generate(folder / "camera-security.json", folder / "camera-security-report.html")
        print(f"[camera-security] Report: {folder / 'camera-security-report.html'}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)

    r = data["summary"]
    print(f"[camera-security] Done: {r['total']} host(s) · {r['ok']} ok · {r['with_findings']} with findings.")
    print(f"[camera-security] Data: {folder / 'camera-security.json'}")


if __name__ == "__main__":
    main()
