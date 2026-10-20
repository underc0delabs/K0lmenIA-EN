# Synthetic monitoring

`npm run monitor` runs a **light, read-only** smoke test against an environment (production, staging…) and notifies Slack and Teams **only when something breaks or recovers**.

## What it checks

- **URLs** (`MONITORING_URLS` in the `.env`, `--urls` or the `checks` in `input/monitoring.json`): expected status (2xx by default), response time (slow if it exceeds `--slow-ms` or the check's `max_ms`), a text that must be present (`text`) and one that must not (`no_text`). `GET` or `HEAD` only.
- **TLS certificate** of each `https` host: it warns if it expires in less than `--tls-days` days (14 by default).
- **k0lmena scenarios** (optional, `--scenarios` or `"scenarios": {"run": true}`): the web `.feature` files with the `@synthetic` tag.

> The `@synthetic` scenarios run against production: they must be **read-only** (navigate, search, view). Nothing that creates, changes or deletes data, no forms that get submitted, no real users. If a flow needs to write, it is not for monitoring.

Run state: **Down** (some check fails), **Degraded** (something slow or a certificate about to expire) or **OK**. It exits with code 1 if the state is Down.

## Configuration

`input/monitoring.json` (see `input/monitoring.example.json`):

```json
{
  "name": "production",
  "checks": [
    { "name": "Home", "url": "https://my-app.com/", "text": "Sign in", "max_ms": 3000 },
    { "name": "Health", "url": "https://api.my-app.com/health", "method": "HEAD", "status": [200, 204] }
  ],
  "scenarios": { "run": false, "tags": "@synthetic" }
}
```

Without a file, `MONITORING_URLS=https://my-app.com,https://my-app.com/login` in the `.env` is enough. Notifications use `SLACK_WEBHOOK_URL` and `TEAMS_WEBHOOK_URL` (`scripts/notify.py`); `MONITORING_LINK`, if set, is used as the notification link.

## Output

`output/monitoring/<name>/`: `monitoring.json`, `monitoring-report.html` (state, what changed, checks, times, availability per check and the runs) and `history/` with the last 30 runs (`--runs`).

## Scheduling it

- **GitHub Actions**: `.github/workflows/monitoring.yml` (it comes with the `schedule` commented out; load the secrets and uncomment it). It keeps the history between runs with the Actions cache.
- **Windows (Task Scheduler)**, every 30 minutes:
  ```powershell
  schtasks /Create /TN "k0lmenIA monitoring" /SC MINUTE /MO 30 /TR "cmd /c cd /d C:\path\to\k0lmenIA && npm run monitor >> output\monitoring\monitoring.log 2>&1"
  ```
- **Linux / macOS (cron)**, every 30 minutes:
  ```cron
  */30 * * * * cd /path/to/k0lmenIA && npm run monitor >> output/monitoring/monitoring.log 2>&1
  ```

The machine that runs it needs the `.env` (or the variables in the environment), Node and Python.
