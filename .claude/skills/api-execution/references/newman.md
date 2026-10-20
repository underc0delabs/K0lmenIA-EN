# Newman — reference

Command details and a worked example. The concepts are in the `SKILL.md`; the installation, in `tools/newman/README.md`.

## Basic commands

```bash
# Run a collection
newman run collection.json

# With an environment (defines base_url and other non-secret variables)
newman run collection.json -e environment.json

# Pass a secret without writing it in any file: in this repo scripts/run_newman.py does it,
# taking API_TOKEN from the .env (in bash it would be --env-var "token=$API_TOKEN"; in PowerShell, $env:API_TOKEN)
python scripts/run_newman.py collection.json --story US-001

# Reporters: console + JSON exported to a file
newman run collection.json -r cli,json --reporter-json-export output.json

# Variable data (one run per row of the CSV/JSON); in this repo: run_newman.py ... --data data.csv
newman run collection.json -d data.csv

# Without a global install: with npx (slower per run)
npx newman run collection.json
```

Useful flags:
- `--folder "<name>"` → runs only one folder of the collection (to run a subset).
- `--timeout-request <ms>` → cuts off hanging requests.
- `--bail` → stops at the first failure.
- `--suppress-exit-code` → does not return an error code (useful if a script must not stop on a failure).

## The repo's full pipeline

```bash
DATE=$(date +%Y%m%d-%H%M)

# 1) Newman → JSON
newman run input/api/demo.postman_collection.json \
  -e input/api/demo.postman_environment.json \
  -r cli,json --reporter-json-export output/runs/_newman-$DATE.json

# 2) Newman JSON → report format (it has no "story": the closure report and the coverage of a story
#    don't see this run; that's why run_newman.py --story US-XXX is preferable)
python scripts/newman_to_results.py \
  output/runs/_newman-$DATE.json \
  output/runs/_results-API-$DATE.json "Demo API k0lmenIA"

# 3) → HTML report (dark dashboard)
python scripts/generate_report.py \
  output/runs/_results-API-$DATE.json \
  output/runs/report-API-$DATE.html
```

## Anatomy of a collection (v2.1)

Each request lives in `item[]` with its `request` (method, headers, url, body) and its validations in an `event` of type `test`:

```json
{
  "name": "API-001 — Get an existing post (High)",
  "request": {
    "method": "GET",
    "url": { "raw": "{{base_url}}/posts/1", "host": ["{{base_url}}"], "path": ["posts", "1"] }
  },
  "event": [
    { "listen": "test", "script": { "exec": [
      "pm.test('Status is 200', function () { pm.response.to.have.status(200); });"
    ] } }
  ]
}
```

> The name `API-001 — … (High)` is not decorative: the converter takes the **id** and the **priority** for the report from it.

## Common validations

```javascript
// Status
pm.response.to.have.status(200);

// Body: property and value
var data = pm.response.json();
pm.expect(data).to.have.property("id");
pm.expect(data.title).to.eql("k0lmenIA");

// Response time
pm.expect(pm.response.responseTime).to.be.below(800);

// Header
pm.response.to.have.header("Content-Type");

// Save a value for the next request (e.g. login token)
var token = pm.response.json().token;
pm.environment.set("token", token);
```

## How the converter maps the result

`scripts/newman_to_results.py` reads Newman's output and builds the report JSON:

```
+----------------------------------+------------------------+----------------------------+
| Situation in Newman              | Status in the report   | Reason                     |
+==================================+========================+============================+
| Request OK, no failed asserts    | **Passed**             | —                          |
+----------------------------------+------------------------+----------------------------+
| Request without any `pm.test`    | **Blocked**            | No validations (pm.test)   |
+----------------------------------+------------------------+----------------------------+
| Some `pm.test` failed            | **Failed**             | the first assert that      |
|                                  |                        | failed                     |
+----------------------------------+------------------------+----------------------------+
| The request could not be made    | **Blocked**            | the connection error       |
+----------------------------------+------------------------+----------------------------+
```

The report **title** comes from the collection name (or the one you pass as the 3rd argument). The **base_url** is taken from the environment/collection to show it in the report. The **date** comes from the actual time of the run.

## Worked example

The demo collection `input/api/demo.postman_collection.json` has three cases against a public API (JSONPlaceholder): get a post (expects 200 + fields), create a post (expects 201 + id) and request a nonexistent one (expects 404). Running the pipeline above, all three come out **Passed** and the report shows 100%. Change `base_url` to your API and replace the collection with yours to test against your service.
