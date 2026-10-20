#!/usr/bin/env python3
"""
Generates the Streaming and playback report in HTML (dashboard, dark mode) from the
ffprobe/ffmpeg verification (streaming.json, from `npm run streaming`) and, optionally, from the
streaming-tester agent's analysis. `npm run streaming` already generates it on its own when it
finishes; the agent regenerates it with its analysis.

Usage:
    python scripts/generate_streaming_report.py <streaming.json> <output.html> [--analysis analysis.json]

What it shows: verdict, indicators (sources tested, OK, with findings, failed and
average latency), one card per source with its properties (container, type, video, audio and
continuity) and the findings from all sources with their severity.

The analysis (optional) provides:
{
  "verdict": "...", "verdict_tone": "ok" | "warn" | "bad",
  "summary": "Summary for a non-technical reader...",
  "missing_info": [{"id": "MI-01", "what_is_missing": "...", "question": "..."}],
  "recommendations": [{"action": "...", "reason": "...", "priority": "High"}],
  "next_steps": ["..."]
}
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _report_styles import (page, meta, section, kpi_tiles, banner, table, two_col, doc_list,
                              level_badge, missing_info, e, OK, WARNING, CRITICAL)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def _prop_table(rec):
    v = rec.get("video") or {}
    a = rec.get("audio") or {}
    c = rec.get("continuity") or {}
    stab = rec.get("stability") or {}
    load = rec.get("load") or {}
    kf = v.get("keyframe_interval_s")
    rows = [
        ["Container", e(rec.get("container") or "—")],
        ["Type", e(rec.get("type") or "—")],
        ["Connection latency", f'{rec.get("connection_latency_s")} s' if rec.get("connection_latency_s") is not None else "—"],
        ["Startup latency (TTFF)", f'{rec.get("ttff_s")} s' if rec.get("ttff_s") is not None else "—"],
        ["Video", e(f'{v.get("codec") or "?"} · {v.get("resolution") or "?"} · {v.get("fps") or "?"} fps · {v.get("bitrate_kbps") or "?"} kbps') if rec.get("video") else "No video"],
        ["Keyframes (GOP)", f'every {kf} s' if kf is not None else "—"],
        ["Audio", e(f'{a.get("codec") or "?"} · {a.get("sample_rate") or "?"} Hz · {a.get("channels") or "?"} channel(s)') if rec.get("audio") else "No audio"],
    ]
    if isinstance(c, dict) and "error" not in c:
        rows.append(["Continuity", e(f'{c.get("frames", 0)} frames read · {c.get("dropped", 0)} dropped · '
                                     f'{c.get("duplicated", 0)} duplicated · {c.get("decoding_errors", 0)} errors')])
    if isinstance(stab, dict) and "error" not in stab and stab:
        rows.append(["Stability", e(f'{stab.get("read_duration_s", "?")} s read · {stab.get("interruptions", 0)} interruptions · '
                                    f'{stab.get("reconnections", 0)} reconnections')])
    if isinstance(load, dict) and load:
        rows.append(["Load", e(f'{load.get("succeeded", 0)}/{load.get("connections", 0)} connections ok · '
                               f'{load.get("average_fps", "?")} avg. fps · {load.get("total_errors", 0)} errors')])
    return table(["Property", "Value"], rows)


def _source_card(rec):
    status = rec.get("status")
    tone = {"ok": "ok", "findings": "warn", "failed": "bad"}.get(status, "warn")
    label = {"ok": "OK", "findings": "With findings", "failed": "Failed"}.get(status, status)
    body = banner(label, tone) + _prop_table(rec)
    return section(rec.get("source", "Source"), body, sub=rec.get("type", ""))


def generate(streaming_json, output, analysis_json=None):
    data = json.loads(Path(streaming_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    sources = data.get("sources", [])
    r = data.get("summary", {})

    lats = [f["connection_latency_s"] for f in sources if f.get("connection_latency_s") is not None]
    lat_avg = round(sum(lats) / len(lats), 2) if lats else None

    kpis = [
        ("Sources tested", str(r.get("total", len(sources))), ""),
        ("OK", str(r.get("ok", 0)), "ok" if r.get("ok") else ""),
        ("With findings", str(r.get("with_findings", 0)), "warn" if r.get("with_findings") else ""),
        ("Failed", str(r.get("failed", 0)), "bad" if r.get("failed") else ""),
        ("Average latency", f"{lat_avg} s" if lat_avg is not None else "—", ""),
    ]

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], TONE.get(analysis.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""))

    # Findings from all sources, sorted by severity.
    findings = []
    for f in sources:
        for h in f.get("findings", []):
            findings.append((f["source"], h.get("severity", "Medium"), h.get("text", "")))
    findings.sort(key=lambda x: SEV_ORDER.get(x[1], 9))
    if findings:
        rows = [[level_badge(sev), e(src), e(txt)] for src, sev, txt in findings]
        body += section("Findings", table(["Severity", "Source", "Detail"], rows),
                        sub=f"{len(findings)} in total")
    else:
        body += section("Findings", banner("No findings: all sources responded within the thresholds.", "ok"))

    for f in sources:
        body += _source_card(f)

    if analysis.get("recommendations"):
        rows = [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))]
                for x in analysis["recommendations"]]
        body += section("Recommendations", table(["Priority", "Action", "Why"], rows))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))

    meta_html = meta([("Generated", data.get("generated")), ("Story", data.get("story")),
                      ("Capture", f'{data.get("capture_seconds")} s'), ("Transport", data.get("transport"))])
    html = page("Streaming and playback", "Streaming verification", meta_html, body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    ap = argparse.ArgumentParser(description="Streaming and playback HTML report.")
    ap.add_argument("streaming_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    out = generate(args.streaming_json, args.output, args.analysis)
    print(out)


if __name__ == "__main__":
    main()
