#!/usr/bin/env python3
"""
Generates the ONVIF control report in HTML (dashboard, dark mode) from the onvif-zeep
test (onvif.json, from `npm run onvif`) and, optionally, from the onvif-tester agent's analysis.

Usage:
    python scripts/generate_onvif_report.py <onvif.json> <output.html> [--analysis analysis.json]

What it shows: overall status, device information (brand, model, firmware), the ONVIF tests
run (device info, profiles, snapshot, events, PTZ) with their result, the profiles and their
RTSP URIs, the downloaded snapshot and the findings by severity.

The analysis (optional) provides: verdict, verdict_tone, summary, missing_info,
recommendations, next_steps (same format as the streaming report).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _report_styles import (page, meta, section, kpi_tiles, banner, table, doc_list,
                              level_badge, status_pill, missing_info, e)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}
TEST_NAME = {
    "device_information": "Device information", "capabilities": "Capabilities",
    "system_date_time": "Clock / time zone", "ntp": "NTP",
    "profiles": "Profiles and stream URI", "snapshot": "Snapshot", "events": "Events / motion",
    "events_live": "Live events (pull-point)", "ptz_presets": "PTZ · presets", "ptz_move": "PTZ · movement",
}
TEST_TONE = {"ok": "ok", "failed": "bad", "n/a": "blk"}


def generate(onvif_json, output, analysis_json=None):
    data = json.loads(Path(onvif_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    res = data.get("result", {})
    dev = res.get("device", {})
    tests = res.get("tests", {})

    status = res.get("status", "—")
    tone = {"ok": "ok", "findings": "warn", "failed": "bad"}.get(status, "warn")

    kpis = [
        ("Status", {"ok": "OK", "findings": "With findings", "failed": "Failed"}.get(status, status), tone),
        ("Tests ok", str(sum(1 for v in tests.values() if v == "ok")), "ok"),
        ("Tests failed", str(sum(1 for v in tests.values() if v == "failed")), "bad" if any(v == "failed" for v in tests.values()) else ""),
        ("Profiles", str(len(res.get("profiles", []))), ""),
        ("PTZ", "Yes" if res.get("capabilities", {}).get("ptz") else "No", ""),
    ]

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], TONE.get(analysis.get("verdict_tone"), "ok"))
    extra_summary = f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""
    body += section("Summary", kpi_tiles(kpis) + extra_summary)

    # Device
    if dev:
        rows = [["Brand", e(dev.get("brand") or "—")], ["Model", e(dev.get("model") or "—")],
                ["Firmware", e(dev.get("firmware") or "—")], ["Serial", e(dev.get("serial") or "—")]]
        body += section("Device", table(["Field", "Value"], rows))

    # Clock and NTP
    clock = res.get("clock") or {}
    ntp = res.get("ntp") or {}
    if clock or ntp:
        rows = []
        if clock:
            d = clock.get("clock_drift_s")
            rows += [["Clock drift", f'{d} s' if d is not None else "—"],
                     ["Time zone", e(clock.get("timezone") or "—")],
                     ["Daylight saving time", "Yes" if clock.get("dst") else "No"]]
        if ntp:
            rows += [["NTP from DHCP", "Yes" if ntp.get("from_dhcp") else "No"],
                     ["NTP servers", e(", ".join(ntp.get("servers") or []) or "—")]]
        body += section("Clock and NTP", table(["Field", "Value"], rows),
                        sub="Clock drift affects the time of recordings and events")

    # ONVIF tests
    if tests:
        rows = [[e(TEST_NAME.get(k, k)), status_pill({"ok": "Passed", "failed": "Failed", "n/a": "N/A"}.get(v, v))]
                for k, v in tests.items()]
        body += section("ONVIF tests", table(["Test", "Result"], rows))

    # Profiles
    profiles = res.get("profiles", [])
    if profiles:
        rows = [[e(p.get("name") or "—"), e(p.get("token") or "—"), e(p.get("rtsp") or p.get("rtsp_error") or "—")]
                for p in profiles]
        body += section("Profiles and stream", table(["Profile", "Token", "RTSP URI"], rows),
                        sub="Pass the RTSP URI to the streaming-tester to verify the video")

    # Live events (pull-point)
    ev = (res.get("events") or {}).get("live")
    if ev:
        if ev.get("subscription") != "ok":
            body += section("Live events", banner(f"Could not subscribe to the pull-point: {e(ev.get('error', 'no details'))}", "bad"))
        else:
            tone = "ok" if ev.get("motion") else "warn"
            txt = ("Live motion was detected." if ev.get("motion")
                   else f"No motion event arrived in {ev.get('requested_s')}s.")
            rows = [["Subscription", "OK (pull-point)"],
                    ["Wait", f"{ev.get('requested_s')} s"],
                    ["Messages received", e(ev.get("messages", 0))],
                    ["Motion detected", "Yes" if ev.get("motion") else "No"],
                    ["Topics seen", e(", ".join(ev.get("topics") or []) or "—")]]
            body += section("Live events", banner(txt, tone) + table(["Field", "Value"], rows),
                            sub="ONVIF pull-point subscription to check motion detection")

    # Snapshot
    snap = res.get("snapshot", {})
    if snap.get("ok"):
        body += section("Snapshot", f'<div class="cardbody"><img src="snapshot.jpg" alt="Camera snapshot" '
                        f'style="max-width:100%;border-radius:12px"><p class="muted">{e(snap.get("bytes", 0))} bytes</p></div>')

    # Findings
    findings = sorted(res.get("findings", []), key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    if findings:
        rows = [[level_badge(x.get("severity", "Medium")), e(x.get("text", ""))] for x in findings]
        body += section("Findings", table(["Severity", "Detail"], rows), sub=f"{len(findings)} in total")
    else:
        body += section("Findings", banner("No findings: all ONVIF tests responded correctly.", "ok"))

    if analysis.get("recommendations"):
        rows = [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))]
                for x in analysis["recommendations"]]
        body += section("Recommendations", table(["Priority", "Action", "Why"], rows))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))

    meta_html = meta([("Generated", data.get("generated")), ("Story", data.get("story")),
                      ("Host", f'{res.get("host")}:{res.get("port")}'),
                      ("PTZ executed", "Yes" if data.get("ptz_executed") else "No")])
    html = page("ONVIF control", "IP camera · ONVIF", meta_html, body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    ap = argparse.ArgumentParser(description="ONVIF control HTML report.")
    ap.add_argument("onvif_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    print(generate(args.onvif_json, args.output, args.analysis))


if __name__ == "__main__":
    main()
