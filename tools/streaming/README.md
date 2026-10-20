# Streaming (ffprobe/ffmpeg + ONVIF)

Tools for video QA:

- **`probe.py`** — verifies **streaming and playback**: that a source comes up, its properties (codec, resolution, FPS, bitrate, audio, keyframes/GOP), the startup latency (TTFF), continuity (dropped frames, errors), stability over time (soak with reconnection) and load (N connections at once). Used by the `streaming-tester` agent.
- **`onvif.py`** — tests the **ONVIF control** of an IP camera: device information, profiles and stream URIs, snapshot, PTZ (optional) and event/motion capabilities. Used by the `onvif-tester` agent.

Covers IP cameras (RTSP/ONVIF), live broadcasts (RTMP/HLS/DASH), WebRTC served over HTTP and VOD/files.

## Requirements

- **ffmpeg** and **ffprobe** on the PATH (for `probe.py`): <https://ffmpeg.org/download.html>
  - Windows: `winget install Gyan.FFmpeg` · Mac: `brew install ffmpeg` · Linux: the `ffmpeg` package.
- **onvif-zeep** (for `onvif.py`): installed automatically if missing, or `pip install onvif-zeep`.

## Streaming and playback

```bash
# Basic (properties + continuity):
npm run streaming -- --source rtsp://cam.local/stream --story US-001 --seconds 10 --confirm
# Stability (60 s soak with reconnection) + load (10 connections at once):
npm run streaming -- --source https://cdn.my-app.com/live/index.m3u8 --stability 60 --connections 10 --confirm
```

`--source` accepts several, comma-separated. Options: `--seconds` (continuity capture, 10), `--transport tcp|udp` (RTSP, tcp by default), `--stability N` (soak in seconds), `--connections N` (bounded load), `--confirm`.

Output in `output/streaming/<story or host>/`: `streaming.json`, `streaming-report.html` (`scripts/generate_streaming_report.py`) and `history/` (last 5).

## ONVIF control

```bash
npm run onvif -- --host 192.168.1.50 --port 80 --story US-001 --confirm
# With PTZ (moves the camera; requires --confirm and authorization):
npm run onvif -- --host 192.168.1.50 --ptz --confirm
```

Credentials via `--user/--password` or `ONVIF_USER`/`ONVIF_PASSWORD` in the `.env`. Output in `output/streaming/onvif-<host or story>/`: `onvif.json`, `onvif-report.html`, `snapshot.jpg` and `history/`.

## Authorization and scope

- `probe.py`: only sources in `STREAMING_AUTHORIZED_SOURCES`. `onvif.py`: only hosts in `ONVIF_AUTHORIZED_HOSTS`. Only devices/streams **you own or have written authorization for**.
- They are **read-only** (they do not record or rebroadcast the video; the snapshot is a test image), **except PTZ** in `onvif.py`, which moves the camera (minimally, then stops it) and requires `--confirm`.
- Load (`--connections`) is bounded to one source; for load on a whole system, use the `performance-mapper`.

Optional thresholds (`.env`): `STREAMING_MIN_FPS`, `STREAMING_LATENCY_WARN_S`, `STREAMING_TTFF_WARN_S`, `STREAMING_GOP_WARN_S`.
