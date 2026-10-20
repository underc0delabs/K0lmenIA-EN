# Newman (Postman CLI)

**Newman** is the command-line runner for **Postman** collections. It runs a `.json` collection (the requests + their validations) against a real API and reports what happened. It is the tool the [`api-runner`](../../.claude/agents/api-runner.md) agent uses to **run API tests**.

> It was the first tool in `tools/`. The others follow the same pattern: a subfolder + its README.

## Installation (once)

It requires **Node.js**. Install it globally with npm:

```bash
npm install -g newman
```

Verify:
```bash
newman --version
```

## How it is used in this repo

The agent runs a **Postman collection** and builds the same dark HTML report as the E2E tests, with a single command (the same in PowerShell, bash and zsh; on Mac/Linux, `python3`):

```bash
python scripts/run_newman.py input/api/demo.postman_collection.json --story US-001
```

The script runs Newman (installed or with `npx`) and takes `API_TOKEN` from the `.env`; the URL (`{{base_url}}`) comes from `--base-url`, the environment or the collection, and only if none of them defines it, from `API_BASEURL` in the `.env`; it converts the result (`scripts/newman_to_results.py`) and generates the report (`scripts/generate_report.py`) in `output/runs/report-US-001-<date-time>.html`. Options: `--folder`, `--environment`, `--base-url` and `--title`. The `api-runner` agent uses it on its own; you normally don't run it by hand.

## Bruno, Insomnia and GraphQL

- **Bruno**: pass it the collection folder (the one with `bruno.json`) instead of the `.json`:
  `python scripts/run_newman.py input/api/demo-bruno --environment JSONPlaceholder`.
- **Insomnia**: pass it the export (v4 `.json` or v5 `.yaml`; v5 needs `pip install pyyaml`):
  `python scripts/run_newman.py input/api/demo.insomnia.json --environment JSONPlaceholder`.
- Both are converted to Postman first with `scripts/convert_collection.py` (in a temp folder) and the
  script shows the **warnings** about what has no equivalent in Postman (Insomnia template tags,
  OAuth2, files in multipart, `bru.runRequest`, …). `--environment` is the environment **name**.
  To see the conversion: `python scripts/convert_collection.py <source> --output <folder>`.
- **GraphQL**: GraphQL requests (Postman's GraphQL mode, Bruno's `body:graphql`, Insomnia's `application/graphql`)
  run the same way; the report adds the operation to the title. Validate `data` and `errors`, not just the status:
  a GraphQL error usually comes back with 200. Example: `input/api/demo-graphql.postman_collection.json`.

## Where the collections go

- **Collections** and **environments** go in `input/api/`. There are samples that point to public demo APIs: `demo.postman_collection.json` + `demo.postman_environment.json` (Postman), `demo-bruno/` (Bruno), `demo.insomnia.json` (Insomnia) and `demo-graphql.postman_collection.json` (GraphQL). Export yours and put them there.
- The **id** and **priority** of each case are (optionally) encoded in the **request name** in Postman: `TC-API-001 — Create post (High)`; if it depends on missing data, add its ID: `TC-API-003 — Create user [MI-01]`. The converter uses them for the report. If you don't include them, the id is auto-numbered and the priority is left empty.

## Credentials / token

Secrets **do not go in the collection or the environment** (those are committed). If your API requires a token:

1. Save the token in the `.env` (gitignored) — e.g. `API_TOKEN=...` (see `.env.example`).
2. In the collection, use the variable in the header: `Authorization: Bearer {{token}}`.
3. `scripts/run_newman.py` passes it to Newman: you don't need to load the `.env` in the shell (which is what made `--env-var "token=$API_TOKEN"` fail in PowerShell, where the syntax is different).

That way the token never ends up in a versioned file. For the `base_url` (which is not a secret) you can use the environment.

## Newman's native HTML report (optional)

If instead of the repo report you want Newman's own report, install the `htmlextra` reporter and use it with `-r htmlextra`:
```bash
npm install -g newman-reporter-htmlextra
newman run <collection> -r htmlextra
```
By default we use the repo report so that API and E2E runs look the same.

## The details

The full "how" (building the collection, validations, variable data, interpreting results) is in the [`api-execution`](../../.claude/skills/api-execution/SKILL.md) skill.
