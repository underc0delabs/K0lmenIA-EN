#!/usr/bin/env python3
"""
Streaming and playback verification with ffprobe/ffmpeg. Tests that a video source comes up and
checks its properties (codec, resolution, FPS, bitrate, audio, keyframes/GOP), the startup
latency (time-to-first-frame), continuity (decoding errors, dropped frames) and, optionally,
stability over time (soak with reconnection) and load (N connections at once).
Works for IP cameras (RTSP/ONVIF), live broadcasts (RTMP/HLS/DASH), WebRTC served over HTTP
and VOD playback. For camera control (PTZ, snapshot, events) use tools/streaming/onvif.py.

Usage (from the repo root):
    python tools/streaming/probe.py --source rtsp://cam.local/stream [--story US-001]
        [--seconds 10] [--transport tcp] [--stability 60] [--connections 10] [--confirm]
    (--source accepts several, comma-separated)

What it does (read-only; it does not save or rebroadcast the stream):
- Checks that each source is authorized in the .env (STREAMING_AUTHORIZED_SOURCES).
- ffprobe: container and per-track metadata (video and audio), without downloading the stream.
- ffprobe (frames): keyframe interval (GOP), which determines how long it takes to "lock on" and to seek.
- ffmpeg: reads --seconds into a null sink to measure startup latency (TTFF), decoded vs. expected
  frames, dropped/duplicated frames and decoding errors.
- --stability N: reads N seconds (soak) with automatic reconnection (http/rtmp) to detect
  interruptions and reconnections over time.
- --connections N: opens N reads in parallel (bounded load test of the same source) and reports
  how many come up, their FPS and their errors. For load on a whole system, use the performance-mapper.
- Leaves in output/streaming/<story or host>/: streaming.json and streaming-report.html. The previous
  run moves to history/ (last 5).

Requires ffmpeg and ffprobe on the PATH (https://ffmpeg.org/download.html).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

# Default thresholds (can be overridden with STREAMING_* in the .env).
MIN_FPS = 10.0           # below this, the video looks choppy
LATENCY_WARN_S = 3.0      # connecting should be fast
TTFF_WARN_S = 4.0          # time to the first frame
GOP_WARN_S = 4.0           # long keyframe interval = slow lock-on and seek
FRAME_DROP_WARN = 0.05   # 5% dropped or missing frames


def fail(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def read_env():
    """The root .env (or K0LMENA_ENV_FILE), with k0lmenIA's common reader; STREAMING_* variables
    from the environment override those in the file."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith("STREAMING_")})
    return values


def authorized(source, env):
    allowed = [u.strip().rstrip("/") for u in re.split(r"[,\s]+", env.get("STREAMING_AUTHORIZED_SOURCES", "")) if u.strip()]
    if not allowed:
        fail("There are no authorized sources. Add to the root .env:\n"
             "  STREAMING_AUTHORIZED_SOURCES=rtsp://cam.local/stream, https://cdn.my-app.com/live/\n"
             "(only devices or streams you own or have written authorization from their owners for).")
    f = source.rstrip("/")
    if not any(f == a or f.startswith(a + "/") or f.startswith(a) for a in allowed):
        fail(f"{source} is not in STREAMING_AUTHORIZED_SOURCES in the .env. Only authorized sources are tested.")


def binaries():
    for b in ("ffprobe", "ffmpeg"):
        if not shutil.which(b):
            fail(f"Cannot find {b}. Install ffmpeg (it includes ffprobe): https://ffmpeg.org/download.html\n"
                 "Windows: `winget install Gyan.FFmpeg` · Mac: `brew install ffmpeg` · Linux: your distro's ffmpeg package.")


def is_rtsp(source):
    return urlparse(source).scheme.lower() == "rtsp"


def supports_reconnect(source):
    """ffmpeg's -reconnect flags apply to http(s)/rtmp; RTSP has no input reconnection."""
    return urlparse(source).scheme.lower() in ("http", "https", "rtmp", "rtmps")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fps(avg):
    """'30000/1001' -> 29.97; '25/1' -> 25.0."""
    if not avg or avg == "0/0":
        return None
    try:
        n, d = avg.split("/")
        d = float(d)
        return round(float(n) / d, 2) if d else None
    except ValueError:
        return _num(avg)


def ffprobe(source, transport, timeout_s):
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    if is_rtsp(source):
        cmd += ["-rtsp_transport", transport]
    cmd += [source]
    t0 = time.monotonic()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None, None, "ffprobe timed out: the source did not respond."
    latency = round(time.monotonic() - t0, 2)
    if r.returncode != 0 or not r.stdout.strip():
        return None, latency, (r.stderr.strip() or "ffprobe could not read the source.")
    try:
        return json.loads(r.stdout), latency, None
    except json.JSONDecodeError:
        return None, latency, "ffprobe returned an unreadable response."


def keyframes(source, transport, timeout_s):
    """Keyframe interval (GOP): reads ~6s of frames and measures the distance between keyframes."""
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
           "-show_entries", "frame=key_frame,pkt_pts_time,best_effort_timestamp_time",
           "-read_intervals", "%+6", "-of", "json"]
    if is_rtsp(source):
        cmd += ["-rtsp_transport", transport]
    cmd += [source]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return None
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        frames = json.loads(r.stdout).get("frames", [])
    except json.JSONDecodeError:
        return None
    times = []
    for fr in frames:
        if str(fr.get("key_frame")) == "1":
            t = _num(fr.get("pkt_pts_time")) or _num(fr.get("best_effort_timestamp_time"))
            if t is not None:
                times.append(t)
    if len(times) < 2:
        return {"gop_frames": None, "interval_s": None, "keyframes_seen": len(times)}
    diffs = [b - a for a, b in zip(times, times[1:]) if b > a]
    interval = round(sum(diffs) / len(diffs), 2) if diffs else None
    return {"interval_s": interval, "keyframes_seen": len(times)}


def read_stream(source, transport, seconds, timeout_s, reconnect=False):
    """Reads `seconds` of the stream into a null sink, measuring while it runs the startup latency
    (TTFF), the frames per segment (to spot interruptions) and the reconnections."""
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-progress", "pipe:1", "-loglevel", "warning"]
    if reconnect and supports_reconnect(source):
        cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "2"]
    if is_rtsp(source):
        cmd += ["-rtsp_transport", transport]
    cmd += ["-i", source, "-t", str(seconds), "-f", "null", "-"]

    errors = []
    reconnections = 0

    def drain_stderr(pipe):
        nonlocal reconnections
        for line in pipe:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            errors.append(line)
            if re.search(r"(?i)reconnect|re-?connecting|will reconnect", line):
                reconnections += 1

    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    except OSError as ex:
        return {"error": f"Could not start ffmpeg: {ex}"}

    err_thread = threading.Thread(target=drain_stderr, args=(proc.stderr,), daemon=True)
    err_thread.start()

    # Watchdog: if ffmpeg does not finish on its own (-t) within the margin, we kill it.
    killed = {"v": False}

    def kill():
        if proc.poll() is None:
            killed["v"] = True
            proc.kill()
    wd = threading.Timer(timeout_s, kill)
    wd.start()

    ttff = None
    samples = []  # (t_wall, frame, out_time_s)
    prog = {}
    try:
        for line in proc.stdout:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            prog[k] = v
            if k == "frame":
                fr = int(v) if v.isdigit() else 0
                if ttff is None and fr >= 1:
                    ttff = round(time.monotonic() - t0, 2)
            if k == "progress":  # end of a progress block
                fr = int(prog.get("frame", 0) or 0)
                ot = (int(prog.get("out_time_us", 0) or 0)) / 1_000_000
                samples.append((round(time.monotonic() - t0, 2), fr, round(ot, 2)))
    finally:
        proc.wait()
        wd.cancel()
        err_thread.join(timeout=1)

    if killed["v"] and not samples:
        return {"error": "The read timed out: the source did not respond."}

    final_frame = int(prog.get("frame", 0) or 0)
    # Interruptions: segments where time moved forward but no new frames came in.
    interruptions = 0
    in_gap = False
    for (t1, f1, _), (t2, f2, _) in zip(samples, samples[1:]):
        gap = (t2 - t1) > 1.0 and f2 == f1
        if gap and not in_gap:
            interruptions += 1
        in_gap = gap
    segments = [f2 - f1 for (_, f1, _), (_, f2, _) in zip(samples, samples[1:])]

    return {
        "frames": final_frame,
        "dropped": int(prog.get("drop_frames", 0) or 0),
        "duplicated": int(prog.get("dup_frames", 0) or 0),
        "read_duration_s": round((int(prog.get("out_time_us", 0) or 0)) / 1_000_000, 2),
        "decoding_errors": len(errors),
        "error_sample": errors[:5],
        "ttff_s": ttff,
        "reconnections": reconnections,
        "interruptions": interruptions,
        "segments": segments[:60],
    }


def concurrent_load(source, transport, connections, seconds, timeout_s):
    """Opens `connections` reads of the same source in parallel and aggregates the result."""
    def one(_):
        return read_stream(source, transport, seconds, timeout_s)
    with ThreadPoolExecutor(max_workers=connections) as ex:
        res = list(ex.map(one, range(connections)))
    ok = [r for r in res if "error" not in r and r.get("frames", 0) > 0]
    fps = []
    for r in ok:
        if r.get("read_duration_s"):
            fps.append(r["frames"] / r["read_duration_s"])
    return {
        "connections": connections,
        "succeeded": len(ok),
        "failed": connections - len(ok),
        "average_fps": round(sum(fps) / len(fps), 1) if fps else None,
        "total_errors": sum(r.get("decoding_errors", 0) for r in ok),
        "reconnections_total": sum(r.get("reconnections", 0) for r in ok),
    }


def analyze(source, probe, latency, kf, cont, stab, load, env):
    """Builds the record for a source and its findings according to the thresholds."""
    fps_min = _num(env.get("STREAMING_MIN_FPS")) or MIN_FPS
    lat_warn = _num(env.get("STREAMING_LATENCY_WARN_S")) or LATENCY_WARN_S
    ttff_warn = _num(env.get("STREAMING_TTFF_WARN_S")) or TTFF_WARN_S
    gop_warn = _num(env.get("STREAMING_GOP_WARN_S")) or GOP_WARN_S

    video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = probe.get("format", {})
    fps = _fps(video.get("avg_frame_rate"))
    width, height = video.get("width"), video.get("height")
    dur = _num(fmt.get("duration"))

    rec = {
        "source": source,
        "connection_latency_s": latency,
        "ttff_s": (cont or {}).get("ttff_s") if isinstance(cont, dict) else None,
        "container": fmt.get("format_long_name") or fmt.get("format_name"),
        "type": "VOD" if dur else "Live / continuous",
        "duration_s": dur,
        "video": {
            "codec": video.get("codec_name"),
            "resolution": f"{width}x{height}" if width and height else None,
            "fps": fps,
            "bitrate_kbps": round(_num(video.get("bit_rate")) / 1000) if _num(video.get("bit_rate")) else None,
            "keyframe_interval_s": (kf or {}).get("interval_s") if kf else None,
        } if video else None,
        "audio": {
            "codec": audio.get("codec_name"),
            "sample_rate": audio.get("sample_rate"),
            "channels": audio.get("channels"),
        } if audio else None,
        "continuity": cont,
        "stability": stab,
        "load": load,
        "findings": [],
    }

    h = rec["findings"]
    if not video:
        h.append({"severity": "Critical", "text": "The source has no video track."})
    else:
        if fps is not None and fps < fps_min:
            h.append({"severity": "High", "text": f"Low FPS: {fps} (expected minimum {fps_min}). The video looks choppy."})
        if not width or not height:
            h.append({"severity": "Medium", "text": "Could not determine the video resolution."})
        ki = (kf or {}).get("interval_s")
        if ki is not None and ki > gop_warn:
            h.append({"severity": "Medium", "text": f"Long keyframe interval: {ki}s (warning above {gop_warn}s). Slow to lock on and to seek."})
    if audio is None:
        h.append({"severity": "Low", "text": "The source has no audio track (may be expected on cameras)."})
    if latency is not None and latency > lat_warn:
        h.append({"severity": "Medium", "text": f"High connection latency: {latency}s (warning above {lat_warn}s)."})
    if isinstance(cont, dict) and "error" not in cont:
        ttff = cont.get("ttff_s")
        if ttff is not None and ttff > ttff_warn:
            h.append({"severity": "Medium", "text": f"High startup latency: {ttff}s to the first frame (warning above {ttff_warn}s)."})
        if cont.get("decoding_errors", 0) > 0:
            h.append({"severity": "High", "text": f"{cont['decoding_errors']} decoding error(s) during the capture."})
        expected = (fps or 0) * cont.get("read_duration_s", 0)
        dropped = cont.get("dropped", 0)
        if expected and dropped / expected > FRAME_DROP_WARN:
            h.append({"severity": "High", "text": f"{dropped} frames dropped out of ~{round(expected)} expected (>{FRAME_DROP_WARN:.0%})."})
    elif isinstance(cont, dict) and cont.get("error"):
        h.append({"severity": "High", "text": cont["error"]})

    if isinstance(stab, dict) and "error" not in stab:
        if stab.get("interruptions", 0) > 0:
            h.append({"severity": "High", "text": f"{stab['interruptions']} stream interruption(s) during the stability test ({stab.get('read_duration_s')}s)."})
        if stab.get("reconnections", 0) > 0:
            h.append({"severity": "Medium", "text": f"{stab['reconnections']} reconnection(s) during the stability test."})
    elif isinstance(stab, dict) and stab.get("error"):
        h.append({"severity": "High", "text": f"Stability: {stab['error']}"})

    if isinstance(load, dict):
        if load.get("failed", 0) > 0:
            sev = "High" if load["failed"] > load["connections"] / 2 else "Medium"
            h.append({"severity": sev, "text": f"Load: {load['failed']} of {load['connections']} connections did not come up."})
        if load.get("total_errors", 0) > 0:
            h.append({"severity": "Medium", "text": f"Load: {load['total_errors']} decoding errors with {load['connections']} connections at once."})

    rec["status"] = "failed" if any(x["severity"] == "Critical" for x in h) else ("findings" if h else "ok")
    return rec


def probe_source(source, args, env):
    print(f"[streaming] Testing {source} …", file=sys.stderr)
    timeout_probe = max(15, args.seconds + 10)
    timeout_cont = max(30, args.seconds * 3 + 15)

    probe, latency, err = ffprobe(source, args.transport, timeout_probe)
    if err:
        return {"source": source, "connection_latency_s": latency, "status": "failed",
                "findings": [{"severity": "Critical", "text": f"Could not open the source: {err}"}],
                "video": None, "audio": None, "continuity": None, "stability": None, "load": None}

    kf = keyframes(source, args.transport, timeout_probe)
    cont = read_stream(source, args.transport, args.seconds, timeout_cont)

    stab = None
    if args.stability:
        print(f"[streaming]   stability: {args.stability}s …", file=sys.stderr)
        stab = read_stream(source, args.transport, args.stability, args.stability * 2 + 20, reconnect=True)

    load = None
    if args.connections and args.connections > 1:
        print(f"[streaming]   load: {args.connections} connections …", file=sys.stderr)
        load = concurrent_load(source, args.transport, args.connections, min(args.seconds, 10), timeout_cont)

    return analyze(source, probe, latency, kf, cont, stab, load, env)


def main():
    ap = argparse.ArgumentParser(description="Streaming and playback verification with ffprobe/ffmpeg.")
    ap.add_argument("--source", required=True, help="Stream URL or file (several, comma-separated).")
    ap.add_argument("--story", default="", help="US-XXX for traceability and the output folder.")
    ap.add_argument("--seconds", type=int, default=10, help="Capture seconds for the continuity test.")
    ap.add_argument("--transport", default="tcp", choices=["tcp", "udp"], help="RTSP transport (tcp by default, more stable).")
    ap.add_argument("--stability", type=int, default=0, help="Soak seconds to measure interruptions and reconnections (0 = off).")
    ap.add_argument("--connections", type=int, default=0, help="N parallel reads of the same source (bounded load test).")
    ap.add_argument("--confirm", action="store_true", help="Skips the confirmation (the person already authorized it).")
    args = ap.parse_args()

    env = read_env()
    binaries()
    sources = [f.strip() for f in args.source.split(",") if f.strip()]
    for f in sources:
        authorized(f, env)

    if not args.confirm:
        print("You are about to test these sources (read-only, without saving or rebroadcasting):")
        for f in sources:
            print(f"  - {f}")
        if args.connections and args.connections > 1:
            print(f"  (+ load test: {args.connections} connections at once)")
        if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
            fail("Cancelled.", 1)

    results = [probe_source(f, args, env) for f in sources]

    host = urlparse(sources[0]).hostname or "streaming"
    folder = ROOT / "output" / "streaming" / (args.story or host)
    folder.mkdir(parents=True, exist_ok=True)

    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, ["streaming.json", "streaming-report.html"], "streaming.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)

    data = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "story": args.story or None,
        "capture_seconds": args.seconds,
        "transport": args.transport,
        "stability_s": args.stability or None,
        "connections": args.connections or None,
        "sources": results,
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r["status"] == "ok"),
            "with_findings": sum(1 for r in results if r["status"] == "findings"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
    }
    (folder / "streaming.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        import generate_streaming_report
        generate_streaming_report.generate(folder / "streaming.json", folder / "streaming-report.html")
        print(f"[streaming] Report: {folder / 'streaming-report.html'}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)

    r = data["summary"]
    print(f"[streaming] Done: {r['total']} source(s) · {r['ok']} ok · {r['with_findings']} with findings · {r['failed']} failed.")
    print(f"[streaming] Data: {folder / 'streaming.json'}")


if __name__ == "__main__":
    main()
