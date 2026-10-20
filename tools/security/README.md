# Static security (SCA and SAST)

**Static, read-only** security analysis of the application repository. It complements the **dynamic** analysis (OWASP ZAP) in `tools/zap/`, used by `security-analyst` and `web-pentester`.

- **`dependencies.py`** (`npm run dependencies`) — **SCA**: detects the project's ecosystems (Node, Python, Java, Go, Ruby, PHP) and runs the available scanners (`npm audit`, `pip-audit`, `osv-scanner`) to list known vulnerabilities (CVE) aggregated by severity. Used by the `dependency-analyst`.
- **`sast.py`** (`npm run sast`) — **SAST + secrets**: includes a built-in secret scanner (pure Python, always runs; it redacts the value) and, if present, runs `semgrep` for code findings (injection, XSS, crypto, etc.). Used by the `secure-code-analyst`.

```bash
npm run dependencies -- --path C:/projects/my-app --output output/dependencies/my-app/sca.json
npm run sast         -- --path C:/projects/my-app --output output/sast/my-app/sast.json
```

Both are **read-only**: they do not run or modify the project, and they do not install or update anything. The HTML reports are built by `scripts/generate_dependencies_report.py` and `scripts/generate_sast_report.py` from the `analysis.json` the agent triages.

**Requirements (optional)**: `npm` (Node), `pip install pip-audit` (Python), `osv-scanner` (multi-ecosystem) and `semgrep` (SAST). If any is missing, the tool says so and continues with whatever is available; the secret scanner needs nothing. `npm run doctor` checks which ones are present.
