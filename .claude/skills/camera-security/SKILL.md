---
name: camera-security
description: The "how" of passive security analysis of IP cameras / NVRs — which well-known ports to check, which services are insecure (Telnet, FTP, HTTP without TLS, RTSP without authentication), how to detect RTSP without auth with a harmless DESCRIBE, and how to handle firmware and its CVEs without making things up. Passive and only on AUTHORIZED_CAMERAS. Used by the camera-security-analyst agent.
---

# Camera security (passive)

Guide to review the security exposure of IP cameras and NVRs **without attacking**. Same criteria as the `security-analyst`'s passive ZAP scan: only devices in `AUTHORIZED_CAMERAS`, no brute force, exploitation or default-password testing.

## What is checked

- **Well-known ports** (TCP connect, no payloads): 21 FTP, 22 SSH, 23 Telnet, 80 HTTP, 443 HTTPS, 554 RTSP, 8000/8080/8554/9000, 37777 (Dahua), 34567 (Sofia NVR).
- **Insecure services**:
  - **Telnet (23) or FTP (21) open** → they should be disabled (plain text, exposed credentials).
  - **HTTP (80) without HTTPS (443)** → the panel and the credentials travel unencrypted.
  - **RTSP (554) without authentication** → detected with a `DESCRIBE` without credentials: **200** = it answers without asking for auth (insecure); **401** = it asks for auth (correct). The `DESCRIBE` is harmless; it is not an attack.
- **Firmware**: if there are ONVIF credentials, the brand/model/firmware is read. There is **no** in-house CVE database: the recommendation is to **review the known CVEs** for that version. Do not make up a specific CVE; if you cite one, it must be verifiable.

## What is NOT done

- No passwords are tested (not even factory defaults), no brute force, no DoS or exploitation.
- No network ranges are scanned and no cameras are searched for: only the declared hosts.
- If a control blocks you, **report that it exists**; do not evade it.

## Severity

- **High**: Telnet/FTP open; RTSP without authentication.
- **Medium**: HTTP without HTTPS; management ports exposed to an untrusted network.
- **Low**: reminder to review the firmware's CVEs; open ports that are expected on the LAN.

## Typical fix (for the recommendations)

Disable Telnet/FTP, enforce HTTPS and move the panel to TLS, require strong authentication on RTSP, update the firmware, and segment the cameras into a VLAN without internet access.
