---
name: onvif-control
description: The "how" of testing the ONVIF control of an IP camera with the onvif-zeep library — services (device management, media, PTZ, events), what to query (device information, capabilities, profiles, stream and snapshot URIs), how to test PTZ safely (move and stop) and how to read the event/motion detection capabilities. Used by the onvif-tester agent.
---

# ONVIF control

Guide for testing the **control** of an IP camera over ONVIF (not the video itself: that is done by the `streaming-verification` skill on the RTSP URI). Only cameras in `ONVIF_AUTHORIZED_HOSTS`, with test credentials.

## ONVIF in two lines

ONVIF is the standard spoken by almost every IP camera. It exposes SOAP **services**: *device management* (info and capabilities), *media* (profiles, stream and snapshot URIs), *PTZ* (pan/zoom) and *events* (motion and other alarms). **Profiles** (Profile S for streaming, Profile T, etc.) group the configuration; each one has a **token** you use to request its stream.

## The library

`onvif-zeep` (import `from onvif import ONVIFCamera`). The tool installs it automatically if missing. Connection:

```python
cam = ONVIFCamera(host, port, user, password)
dev = cam.create_devicemgmt_service()      # info and capabilities
media = cam.create_media_service()         # profiles, stream URI, snapshot
ptz = cam.create_ptz_service()             # pan/zoom
ev = cam.create_events_service()           # events
```

## What to test (and what it means)

- **GetDeviceInformation**: brand, model, firmware, serial. If it fails with valid credentials, the camera does not implement ONVIF properly.
- **GetCapabilities**: which services it has (PTZ, Events, Media, Imaging). Guides what else makes sense to test.
- **GetProfiles** → for each profile, **GetStreamUri** (the RTSP URI) and the token. Without profiles there is no streaming over ONVIF: High finding.
- **GetSnapshotUri** + download: a still test image. Returning an image (not an error or an HTML page) confirms the snapshot. The download usually requires **digest** (or basic) auth with the same credentials.
- **Events / motion**: if there is an events service, `GetEventProperties` lists the topics (including motion detection). To see detection **live**, the `--events N` mode makes a **pull-point** subscription: `CreatePullPointSubscription`, then `PullMessages` over an N-second window, and finally `Unsubscribe`. While it runs, someone must **create motion in front of the camera** (and its detection must be enabled). It looks for a `NotificationMessage` whose motion `SimpleItem` (`IsMotion`/`State`/`isActive`) comes as `true`; it reports the topics seen, the messages received and whether motion was detected. If nothing arrives, it usually means detection is not enabled, the zone/sensitivity did not trigger it, or the camera does not publish that topic over ONVIF.
- **PTZ**: `GetPresets` (list of saved positions) is read-only. **Moving is an action with side effects**: only with confirmation. The safe pattern is a minimal movement and an immediate stop:

```python
ptz.ContinuousMove({"ProfileToken": token, "Velocity": {"PanTilt": {"x": 0.1, "y": 0.0}}})
time.sleep(0.6)
ptz.Stop({"ProfileToken": token, "PanTilt": True, "Zoom": True})
```

Never leave the camera moving. Do not change presets or the "home" position.

## Clock, time zone and NTP

- **GetSystemDateAndTime**: gives the camera time (UTC), the time zone (`TZ`) and daylight saving time. Compare the camera time with the real time to measure the **clock drift**: a large drift (warning above 60 s, `ONVIF_CLOCK_DRIFT_WARN_S`) makes the time of recordings and events unreliable.
- **GetNTP**: whether it uses NTP and which servers. Without NTP, the clock drifts over time.
- Against the **site standard**: `ONVIF_EXPECTED_TZ`, `ONVIF_EXPECTED_NTP` and `ONVIF_EXPECTED_FIRMWARE` let you flag a camera with a time zone, NTP or firmware different from the standard (or old firmware).

## Recordings (Recording / Search)

To verify that an NVR/camera records correctly, ONVIF's **Recording** and **Search** services:

- **GetRecordingSummary** (Search): the total recorded range (`DataFrom`/`DataUntil`) and the number of recordings. From that you get the **days covered** (to compare with the expected retention) and whether the last recording is recent (if not, it may not be recording now).
- **GetRecordings** (Recording): each recording and its tracks with their range, to estimate **gaps**.
- Many cameras do not implement these services over ONVIF: if they fail, report that it is **not supported** (it is not a recording failure) and suggest the NVR's own API. This is used by the `recording-verifier` agent.

## Security and limits

- **Only the authorized host** (`ONVIF_AUTHORIZED_HOSTS`); do not scan the network or search for cameras.
- **Test credentials** given by the person; do not try default passwords or brute force.
- **PTZ and configuration**: move only with confirmation and stopping it; do **not** change network, users, recording or presets.
- **Data**: do not copy full credentials; if any appear exposed, recommend rotating them.

## Severity

- **Critical**: cannot connect over ONVIF (with valid credentials).
- **High**: device info fails or it does not expose profiles/stream.
- **Medium**: the snapshot or the declared PTZ fails.
- **Low**: an optional service not implemented, or PTZ requested without PTZ capability.

## Afterwards

With the RTSP URI of a profile, the `streaming-tester` agent verifies that the stream plays correctly (codec, resolution, FPS, continuity, stability).
