# OWASP ZAP — web security (passive scan)

[OWASP ZAP](https://www.zaproxy.org/) is the reference free and open-source web security scanner. In k0lmenIA it is used in **baseline (passive)** mode: it crawls the site with the spider and analyzes the responses **without sending attacks or modifying data**. It is used by the **`security-analyst`** agent, which also analyzes the results and builds the HTML report.

Among other things, it finds: missing security headers (CSP, HSTS, X-Content-Type-Options…), cookies without `Secure`/`HttpOnly`/`SameSite`, exposed information (versions, comments, errors), mixed content and caching problems with sensitive data.

> [!IMPORTANT]
> Only sites that are **your own or have written authorization** from their owners, declared in `SECURITY_AUTHORIZED_URLS`, are scanned. A passive scan **does not replace** an authorized active scan or a penetration test.

## Requirements

- **Docker** running (Docker Desktop on Windows and macOS). The first time it downloads the official `ghcr.io/zaproxy/zaproxy:stable` image (a few hundred MB).
- **Python 3** (the runner and the report generator).

## Configuration (root `.env`)

```bash
SECURITY_AUTHORIZED_URLS=https://staging.my-app.com,https://qa.my-app.com
# ZAP_IMAGE=ghcr.io/zaproxy/zaproxy:stable     # optional: another image or a pinned version
```

An authorized URL covers its subpaths (`https://staging.my-app.com/login`), but not other domains that start the same way.

## Usage

From the repo root (or ask the agent: *"review the security of https://staging.my-app.com"*):

```bash
python tools/zap/scan.py --url https://staging.my-app.com --story US-001 [--minutes 1] [--confirm]
```

- `--minutes`: spider crawl time (1 to 10).
- Without `--confirm` it asks for confirmation in the terminal.

Output in `output/security/<US or host>/<date>/`:

```
zap.json                 ZAP result (read by the agent and the report)
zap-native.html          ZAP's own report
zap.log                  scan log
analysis.json            the agent's analysis (false positives, notes, recommendations)
security-report.html     k0lmenIA report (dashboard, dark mode)
```

The report can be regenerated with another analysis:

```bash
python scripts/generate_security_report.py <folder>/zap.json <folder>/security-report.html --url <url> --analysis <folder>/analysis.json
```

## Sources

- ZAP Baseline Scan: https://www.zaproxy.org/docs/docker/baseline-scan/
- ZAP in Docker: https://www.zaproxy.org/docs/docker/about/
