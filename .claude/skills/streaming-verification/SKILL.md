---
name: streaming-verification
description: The "how" of testing video streaming and playback with ffprobe/ffmpeg — protocols (RTSP/ONVIF, RTMP, HLS, DASH, WebRTC, VOD and files), which properties to check (codec, resolution, FPS, bitrate, audio, keyframes), how to read continuity (dropped frames, decoding errors, latency) and which thresholds to use. Used by the streaming-tester agent.
---

# Streaming and playback verification

Guide for testing that a stream or a video **plays correctly**, with ffprobe (metadata) and ffmpeg (continuity). It is not load testing (that is the `performance-mapper`) or security (that is `security-analyst` / `web-pentester`). Only sources in `STREAMING_AUTHORIZED_SOURCES`.

## Protocols and how they are named

- **RTSP** (`rtsp://…`): IP cameras. Use **TCP** transport by default (more stable than UDP; UDP only if the person asks for it). ONVIF is the control standard for IP cameras: the RTSP URL usually comes from its profile (Profile S). Control itself (PTZ, snapshot, events) is not covered by this flow: it stays as `Missing information` or goes to an extension.
- **RTMP** (`rtmp://…`): live broadcast ingest/output (OBS, live servers).
- **HLS** (`…/index.m3u8`) and **DASH** (`…/manifest.mpd`): adaptive streaming over HTTP; typical for VOD and live on the web. ffprobe reads the manifest and the first representation.
- **WebRTC**: low latency in the browser; if the stream is served over HTTP, the source can be tested, but the real WebRTC negotiation is validated in the browser with `e2e-runner`.
- **File / VOD** (`http(s)://…/video.mp4`, or a path): playback of a complete video; here there is a `duration`.

## What to check (and what it means for the person)

- **Video codec** (`h264`, `hevc/h265`, `av1`, `vp9`): that it is the expected one and that the target player supports it. HEVC and AV1 do not play in every browser.
- **Resolution** (`1920x1080`, …): that it matches what was contracted/expected. Lower resolution = poorer image.
- **FPS**: stable and above the minimum (10 by default, `STREAMING_MIN_FPS`). Low or variable FPS = choppy video.
- **Bitrate**: very low = pixelated; very high = bandwidth use and buffering. Compare with what is expected for the resolution.
- **Audio**: present if applicable. Security cameras often have none: that is expected (Low severity or discarded), not a bug.
- **Keyframes (GOP)**: very long intervals take long to "lock on" to the stream and to seek. (ffprobe shows them per frame if requested; for the MVP it is inferred from errors when connecting.)

## Continuity (the capture of a few seconds)

`ffmpeg` reads `--seconds` into a null sink and reports:

- **frames** read, **dropped** (`drop_frames`) and **duplicated** (`dup_frames`): sustained drops (> 5% of the expected = fps × seconds) = visible interruptions.
- **decoding errors**: corrupt packets or network loss; any > 0 deserves a look.
- **connection latency**: how long ffprobe took to respond (warning above 3 s, `STREAMING_LATENCY_WARN_S`).
- **startup latency (TTFF)**: time to the **first** decoded **frame** (warning above 4 s, `STREAMING_TTFF_WARN_S`). It is what the person feels when pressing play.

## Stability and reconnection (`--stability N`)

Reads N seconds (soak) with automatic reconnection enabled (`-reconnect`, applies to **http/rtmp**; with RTSP ffmpeg has no input reconnection) and reports:

- **interruptions**: segments where time moved forward but no new frames came in (the stream "froze").
- **reconnections**: how many times ffmpeg had to reconnect.

Useful for live streams and cameras you leave running for a while. An interruption or reconnection = interrupted experience: High/Medium finding.

**Real *glass-to-glass* latency** (from the physical event to the screen) needs a visible marker in front of the camera and is not measured on its own: it stays as `Missing information` or a manual test. What we do measure is the TTFF and, for live streams, the implicit buffering delay.

## Bounded load (`--connections N`)

Opens N parallel reads of the **same** source and reports how many come up, their average FPS and their errors. It is a **bounded** load test of that stream's server (for example, how many RTSP sessions an NVR can handle). For load on a **whole system** (many users, ramps, thresholds), the `performance-mapper`.

## Keyframes (GOP)

ffprobe reads ~6 s of frames and measures the **interval between keyframes**. A long interval (warning above 4 s, `STREAMING_GOP_WARN_S`) makes the stream slow to "lock on" and seeking rough.

## Camera control (ONVIF)

PTZ, snapshot, profiles and events/motion detection are tested by the `onvif-tester` agent (skill `onvif-control`), which also returns the RTSP URI to verify the video here.

## Thresholds (overridden in the `.env`)

- `STREAMING_MIN_FPS` (10 by default)
- `STREAMING_LATENCY_WARN_S` (3 by default)
- `STREAMING_TTFF_WARN_S` (4 by default)
- `STREAMING_GOP_WARN_S` (4 by default)
- Frame-drop warning: 5% of the expected (fixed in the runner).

The thresholds are a starting point: if the person defines others (based on the contracted quality), those take precedence and are recorded as an accepted assumption.

## Severity criteria

- **Critical**: the source does not open or has no video.
- **High**: FPS below the minimum, decoding errors, sustained dropped frames.
- **Medium**: resolution cannot be determined, high connection latency.
- **Low**: no audio when it could be expected (on cameras, it is often discarded).
