---
name: api-execution
description: How to run API tests with Newman (the Postman CLI) — run a Postman, Bruno or Insomnia collection (the latter two are converted to Postman) against a real REST or GraphQL API, write validations, handle base_url and token, and interpret the results for the report. Use it when running collections with Newman (api-runner).
---

# API execution with Newman

The "how" for running API tests reliably by running a **Postman collection** with **Newman**. The tool lives in `tools/newman/` (the installation is there).

## The idea

A **Postman collection** (`.json`) describes the requests and their **validations** (the `pm.test(...)` calls). **Newman** runs it against a real API. In this repo, the result is converted and shown in the **same dark HTML report** as the E2E tests. Pipeline:

```
collection .json → newman run (JSON) → newman_to_results.py → generate_report.py → report .html
```

## Where the collection comes from

- **The person brings it**: exported from Postman, saved in `input/api/`. This is the most common case if the tests already live in Postman.
- **It comes from Bruno or Insomnia**: the Bruno folder (with `bruno.json`) or the Insomnia export (v4 `.json` / v5 `.yaml`) is passed directly to `run_newman.py`, which converts them to Postman with `scripts/convert_collection.py` (see *Bruno and Insomnia* below).
- **You build it** from a contract or from the `api-case-generator` cases: you generate the collection `.json` (requests + `pm.test` with the validations) and then run it.

## Validations (what decides passed/failed)

Each request carries its asserts in the Postman *Tests* block, with `pm.test` + `pm.expect`:

```javascript
pm.test("Status is 200", function () {
    pm.response.to.have.status(200);
});
pm.test("Returns an id", function () {
    pm.expect(pm.response.json()).to.have.property("id");
});
```

Validate what matters: **status code**, **key fields** of the body, and if needed the **schema** or a **specific value**. The case status is decided by Newman, not by the model's judgment. A request **without any `pm.test`** comes out **Blocked** ("No validations"), never Passed.

## base_url and token

- **`base_url`** (not a secret): goes in the **environment** (`input/api/*.postman_environment.json`) or as a collection variable. Requests use `{{base_url}}/whatever`.
- **Token / credentials** (secret): **never** in the collection or the environment. It goes in the `.env` (gitignored) and is passed at run time:
  ```bash
  python scripts/run_newman.py <collection> --story US-001   # token from .env; base_url from --base-url, from the environment/collection or, if they don't define it, from API_BASEURL
  ```
  In the collection, the header uses the variable: `Authorization: Bearer {{token}}`. Use a test environment, not production.

## Bruno and Insomnia

`scripts/convert_collection.py` converts them to Postman v2.1 (`run_newman.py` does it automatically; by hand: `python scripts/convert_collection.py <source> --output <folder> [--environment <name>]`):

```
+-------------------------------------+---------------------------------------+------------------------------------+
| Source                              | What is converted                     | How                                |
+=====================================+=======================================+====================================+
| Bruno `.bru`                        | requests, folders (ordered by `seq`), | as is                              |
|                                     | headers, query and path params, auth  |                                    |
|                                     | bearer/basic/API key, JSON, text,     |                                    |
|                                     | XML, form, multipart and GraphQL      |                                    |
|                                     | bodies                                |                                    |
+-------------------------------------+---------------------------------------+------------------------------------+
| Bruno `assert`                      | `res.status: eq 200`, `res.body.id:   | one `pm.test` per line             |
|                                     | isDefined`, …                         |                                    |
+-------------------------------------+---------------------------------------+------------------------------------+
| Bruno `tests`, `script:*`, `vars:*` | Bruno's JS (`res`, `req`, `bru`,      | with an adapter over `pm`          |
|                                     | `test`, `expect`)                     |                                    |
+-------------------------------------+---------------------------------------+------------------------------------+
| Bruno `environments/*.bru`          | `vars` (and empty `vars:secret`)      | Postman environment                |
+-------------------------------------+---------------------------------------+------------------------------------+
| Insomnia v4 / v5                    | requests, folders, headers, params,   | its `insomnia.*` is the same as    |
|                                     | auth, bodies (GraphQL included),      | `pm.*`                             |
|                                     | `preRequestScript` and                |                                    |
|                                     | `afterResponseScript`                 |                                    |
+-------------------------------------+---------------------------------------+------------------------------------+
| Insomnia environments               | base + the chosen sub-environment     | Postman environment                |
|                                     | (`--environment`)                     |                                    |
+-------------------------------------+---------------------------------------+------------------------------------+
```

Variables: `{{ _.base_url }}` (Insomnia) and `{{base_url}}` (Bruno) become `{{base_url}}`. Whatever has no equivalent (Insomnia `{% response ... %}` template tags, OAuth2/AWS/Digest, files in multipart, `bru.runRequest`, Insomnia unit tests, Bruno folder or collection scripts) **is listed as a warning**: tell the person along with the result. Bruno secret variables stay empty: the token comes from `API_TOKEN` (`{{token}}`).

## GraphQL

Newman runs GraphQL requests just like REST ones (Postman **GraphQL** mode: `query` + `variables`). What changes is **what to validate**: a GraphQL error usually comes back with **status 200** and the `errors` list, so validating only the status is not enough.

```javascript
pm.test("Returns no errors", function () {
    pm.expect(pm.response.json().errors).to.be.undefined;
});
pm.test("Returns the country", function () {
    pm.expect(pm.response.json().data.country.name).to.eql("Argentina");
});
// Negative case: the expected error
pm.test("Rejects the nonexistent field", function () {
    pm.expect(pm.response.json().errors[0].message).to.include("nonexistentField");
});
```

- Dynamic values go in the **variables** (`{"code": "{{code}}"}`), not concatenated into the query.
- **Mutations** modify data: confirm them like any method with side effects.
- In the report, the case title adds the operation (`[GraphQL query Country]`), taken from the query.
- To learn the schema without reading it in full: `python scripts/summarize_graphql.py <url or .graphql file>`.
- Worked example: `input/api/demo-graphql.postman_collection.json` (against https://countries.trevorblades.com).

## Id and priority in the report

The converter takes the **id** and the **priority** from the **request name** in Postman (both optional):

```
API-001 — Create a post (High)
└─id──┘   └───title───┘ └prio┘
```

- id: a prefix like `API-001` / `TC-API-001` followed by `—`, `-`, `:` or `·`.
- priority: `Critical | High | Medium | Low`, in parentheses at the end.

If you don't set them, the id is auto-numbered (`API-001`, `API-002`…) and the priority stays empty (the per-priority bars simply don't appear).

## How the statuses are interpreted

The converter (`scripts/newman_to_results.py`) translates Newman's output into:

- **Passed** — the request was made, has asserts and **none** failed.
- **Failed** — some `pm.test` failed (the reason is the first assert that failed, e.g. *"Status is 200: expected 200 but got 404"*).
- **Blocked** — the request **could not be made** (connection error, host down, etc.) or **has no `pm.test` at all** (reason *"No validations (pm.test)"*: without asserts nothing was verified).

## Speed and permissions

- Newman runs through **Bash**. The first time, Claude Code may ask permission to run `newman`: choose *Always allow* (or it is already pre-approved in `.claude/settings.json`).
- A single collection runs fast. If you have many, run **only the folder** the person asks for, not everything.
- **Variable data** (data-driven): `run_newman.py ... --data data.csv` (Newman's `-d`) iterates the collection over each row; each iteration is one row in the report.

## Prerequisites

- **Newman** installed: `npm install -g newman` (requires Node.js). Details in `tools/newman/README.md`.
- The **API reachable** (public URL or localhost).

Command details, reporters and a worked example are in [`references/newman.md`](references/newman.md).
