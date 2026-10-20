# MCP Connectors

How to connect k0lmenIA over MCP to **Jira and Confluence** (Atlassian), **Figma**, the **application repository** (GitHub, GitLab, Azure Repos or Bitbucket), **other project management tools** (Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack and Shortcut), **QMetry**, **AIO Tests**, **k0lmenaTMT**, **Azure DevOps** and **Appium**. Xray is integrated without MCP (see below).

> **The easy way:** run `npm run configure` in a terminal. It asks which tools your team uses, asks only for their data and activates the connectors that are needed. What follows is the detail, for configuring by hand or for something specific.

Claude Code **starts right away, without asking you to approve connectors**: `.mcp.json` only includes the ones enabled for everyone (Playwright and **Atlassian: Jira and Confluence**). The rest are in a catalog (`scripts/mcp/catalog.json`) and each person activates the ones they use with `npm run connector -- activate <name>`. None of them contain secrets: credentials are read from the root `.env` or authorized with your account (OAuth).

## Summary

```
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| Connector                        | Tool                                    | MCP server                            | Type     | Transport   | Enabled by default   |
+==================================+=========================================+=======================================+==========+=============+======================+
| playwright · playwright-headless | Browser (e2e-runner, web-mapper, web-   | @playwright/mcp                       | Official | stdio       | Yes                  |
|                                  | explorer, accessibility-analyst)        |                                       |          |             |                      |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| atlassian                        | Jira and Confluence (Cloud)             | Atlassian Rovo MCP Server (remote)    | Official | http        | Yes                  |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| azure-devops                     | Azure DevOps (Boards, Test Plans, Wiki) | @azure-devops/mcp (Microsoft)         | Official | stdio       | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| figma                            | Figma (designs)                         | Remote Figma MCP Server               | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| figma-desktop                    | Figma (desktop app)                     | Desktop Figma MCP Server (local)      | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| github                           | GitHub (app repository)                 | Remote GitHub MCP Server (read-only)  | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| gitlab                           | GitLab (app repository)                 | GitLab MCP Server (/api/v4/mcp)       | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| linear                           | Linear (stories)                        | Linear MCP Server (remote, read-only) | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| clickup                          | ClickUp (stories)                       | ClickUp MCP Server (remote)           | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| monday                           | monday.com (stories)                    | monday.com MCP Server (remote)        | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| asana                            | Asana (stories)                         | Asana MCP Server V2 (remote)          | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| trello                           | Trello (stories)                        | Trello MCP Server (remote, Atlassian) | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| notion                           | Notion (documentation and backlogs)     | Notion MCP Server (remote)            | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| youtrack                         | YouTrack (stories)                      | YouTrack built-in MCP (your site)     | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| shortcut                         | Shortcut (stories)                      | Shortcut MCP Server (remote)          | Official | http        | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| qmetry                           | QMetry Test Management                  | @smartbear/mcp                        | Official | stdio       | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| qtm4j                            | QMetry Test Management for Jira (QTM4J) | @smartbear/mcp                        | Official | stdio       | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| aio-tests                        | AIO Tests for Jira                      | AIO Tests remote server (per tenant)  | Official | stdio       | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| k0lmena-tmt                      | k0lmenaTMT                              | k0lmenaTMT MCP server (local or self- | Official | http        | No                   |
|                                  |                                         | hosted)                               |          |             |                      |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| appium-mcp                       | Appium (mobile-mapper)                  | appium-mcp                            | Official | stdio       | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
| salesforce                       | Salesforce (salesforce-tester)          | @salesforce/mcp (Salesforce DX)       | Official | stdio       | No                   |
+----------------------------------+-----------------------------------------+---------------------------------------+----------+-------------+----------------------+
```

> **Creating folders, test cases and cycles and publishing results doesn't require any MCP**: the built-in `scripts/management/` integration does it (agents `test-manager` and `results-publisher`), supporting **Xray Cloud, Xray Server/Data Center, QTM4J and AIO Tests** with their official APIs. Configuration in [`scripts/management/README.md`](scripts/management/README.md). The exception is **Azure DevOps**, which is integrated through its MCP (see [Azure DevOps](#azure-devops)). The MCPs on this page are optional, for querying or exploring the tool from the chat.

---

## What to configure for your team

All connectors are already in `.mcp.json` and all variables are in `.env.example` (one block per tool, commented out). Each QA fills in only what their team's tools need:

```
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| If your team uses…            | Connector / integration                  | Variables in the `.env`                  | Enabled by default                  |
+===============================+==========================================+==========================================+=====================================+
| Jira and Confluence           | `atlassian` (MCP)                        | None with OAuth; with a token:           | Yes                                 |
|                               |                                          | `ATLASSIAN_MCP_AUTHENTICATION=token`,    |                                     |
|                               |                                          | `JIRA_EMAIL`, `JIRA_API_TOKEN`           |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Azure DevOps                  | `azure-devops` (MCP)                     | `ADO_ORGANIZATION`, `ADO_PAT`,           | No                                  |
|                               |                                          | `ADO_PROJECT`                            |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Figma                         | `figma` or `figma-desktop` (MCP)         | None (OAuth)                             | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Repository on GitHub          | `github` (MCP)                           | `REPO_PROVIDER=github`, `REPO_NAME`,     | No                                  |
|                               |                                          | `GITHUB_TOKEN`                           |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Repository on GitLab          | `gitlab` (MCP)                           | `REPO_PROVIDER=gitlab`, `REPO_NAME`,     | No                                  |
|                               |                                          | `GITLAB_URL`; `GITLAB_TOKEN` optional    |                                     |
|                               |                                          | (OAuth)                                  |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Repository on Azure Repos     | `azure-devops` (MCP)                     | `REPO_PROVIDER=azure-repos`, `REPO_NAME` | No                                  |
|                               |                                          | + the Azure DevOps ones                  |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Repository on Bitbucket Cloud | `atlassian` (MCP)                        | `REPO_PROVIDER=bitbucket`, `REPO_NAME`,  | Yes (with a token)                  |
|                               |                                          | `ATLASSIAN_MCP_AUTHENTICATION=token` +   |                                     |
|                               |                                          | the Jira ones                            |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Linear                        | `linear` (MCP)                           | None (OAuth); optional `LINEAR_API_KEY`  | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| ClickUp                       | `clickup` (MCP)                          | None (OAuth)                             | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| monday.com                    | `monday` (MCP)                           | None (OAuth); optional                   | No                                  |
|                               |                                          | `MONDAY_API_TOKEN`                       |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Asana                         | `asana` (MCP)                            | `ASANA_CLIENT_ID`, `ASANA_CLIENT_SECRET` | No                                  |
|                               |                                          | (your own MCP app)                       |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Trello                        | `trello` (MCP)                           | None (OAuth)                             | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Notion                        | `notion` (MCP)                           | None (OAuth)                             | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| YouTrack                      | `youtrack` (MCP)                         | `YOUTRACK_URL`, `YOUTRACK_TOKEN`         | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Shortcut                      | `shortcut` (MCP)                         | None (OAuth)                             | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Xray Cloud                    | `scripts/management` (no MCP)            | `MANAGEMENT_TOOL=xray-cloud`,            | Ready once the `.env` is filled in  |
|                               |                                          | `MANAGEMENT_PROJECT`,                    |                                     |
|                               |                                          | `XRAY_CLOUD_CLIENT_ID`,                  |                                     |
|                               |                                          | `XRAY_CLOUD_CLIENT_SECRET` + the Jira    |                                     |
|                               |                                          | ones                                     |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| Xray Server / Data Center     | `scripts/management` (no MCP)            | `MANAGEMENT_TOOL=xray-dc`,               | Ready once the `.env` is filled in  |
|                               |                                          | `MANAGEMENT_PROJECT`, `XRAY_DC_URL`,     |                                     |
|                               |                                          | `XRAY_DC_TOKEN` (or `XRAY_DC_USER` +     |                                     |
|                               |                                          | `XRAY_DC_PASSWORD`)                      |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| QMetry for Jira (QTM4J)       | `scripts/management` + `qtm4j` (MCP)     | `MANAGEMENT_TOOL=qtm4j`,                 | `scripts/management`: yes · MCP: no |
|                               |                                          | `MANAGEMENT_PROJECT`, `QTM4J_API_KEY`    |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| QMetry Test Management        | `qmetry` (MCP)                           | `QMETRY_API_KEY`                         | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| AIO Tests                     | `scripts/management` + `aio-tests` (MCP) | `MANAGEMENT_TOOL=aio`,                   | `scripts/management`: yes · MCP: no |
|                               |                                          | `MANAGEMENT_PROJECT`, `AIO_API_TOKEN`,   |                                     |
|                               |                                          | `AIO_MCP_URL`                            |                                     |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
| k0lmenaTMT                    | `k0lmena-tmt` (MCP)                      | `K0LMENA_TMT_TOKEN`                      | No                                  |
+-------------------------------+------------------------------------------+------------------------------------------+-------------------------------------+
```

**Activating the optional ones** (Azure DevOps, Figma, GitHub, GitLab, Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack, Shortcut, QMetry, AIO Tests, k0lmenaTMT, Appium):

```bash
npm run connector                              # lists the connectors and which ones you have active
npm run connector -- activate azure-devops     # several at once too: activate azure-devops figma
npm run connector -- deactivate azure-devops
```

`activate` registers it with `claude mcp add-json --scope local`: it's **just for you, in this project**, it doesn't touch any versioned file and it doesn't trigger prompts at startup. If variables are missing from the `.env`, it tells you which ones. Then restart Claude Code and check with `/mcp`; `npm run doctor` checks the variables of all active connectors. **The `scripts/management` integrations** (Xray, QTM4J and AIO) don't need to be activated: they work as soon as the `.env` has their variables.

---

## Steps to activate a connector

1. **Fill in its variables in the root `.env`** (they're in `.env.example` and in each connector's section). `atlassian` and `figma` don't use variables: they're authorized with your account.
2. **Activate it** (if it's not one of those enabled by default): `npm run connector -- activate <name>`.
3. **Restart Claude Code** and check the connection with `/mcp`.

**How tokens reach the server without ending up in `.mcp.json`:** connectors with credentials don't call the server directly, but a script in `scripts/mcp/` that reads the variables from the environment or, if they're not there, from the `.env`, and starts the server passing them only as environment variables:

```
+--------------------------+---------------------------------+------------------------------------------+
| Script                   | Connectors                      | What it does                             |
+==========================+=================================+==========================================+
| `playwright.js`          | playwright, playwright-headless | Starts Playwright with the evidence      |
|                          |                                 | folder and, if the `.env` exists, with   |
|                          |                                 | `--secrets .env` (hides those values in  |
|                          |                                 | the responses)                           |
+--------------------------+---------------------------------+------------------------------------------+
| `with-env.js`            | qmetry, qtm4j, appium-mcp       | Passes the server the variables its      |
|                          |                                 | entry asks for (and nothing else from    |
|                          |                                 | the `.env`)                              |
+--------------------------+---------------------------------+------------------------------------------+
| `azure-devops.js`        | azure-devops                    | Builds the PAT in the server's format    |
|                          |                                 | and chooses the enabled areas            |
+--------------------------+---------------------------------+------------------------------------------+
| `salesforce.js`          | salesforce                      | Points to the `SALESFORCE_ORG` org (from |
|                          |                                 | the authorized list) and limits the      |
|                          |                                 | server to read-only SOQL and Apex tests  |
+--------------------------+---------------------------------+------------------------------------------+
| `aio-tests.js`           | aio-tests                       | Connects to your tenant's URL through    |
|                          |                                 | `mcp-remote`, with the token in the      |
|                          |                                 | header                                   |
+--------------------------+---------------------------------+------------------------------------------+
| `k0lmena-tmt-headers.js` | k0lmena-tmt                     | Returns the `Authorization` header (it's |
|                          |                                 | a `headersHelper`)                       |
+--------------------------+---------------------------------+------------------------------------------+
| `atlassian-headers.js`   | atlassian                       | With                                     |
|                          |                                 | `ATLASSIAN_MCP_AUTHENTICATION=token` it  |
|                          |                                 | builds the header with the API token;    |
|                          |                                 | with `oauth` (default) it adds nothing   |
+--------------------------+---------------------------------+------------------------------------------+
| `github-headers.js`      | github                          | Returns the token as `Bearer`, read-only |
|                          |                                 | mode and the toolsets (it's a            |
|                          |                                 | `headersHelper`)                         |
+--------------------------+---------------------------------+------------------------------------------+
| `gitlab-headers.js`      | gitlab                          | Chooses the toolsets and, if there's a   |
|                          |                                 | `GITLAB_TOKEN`, adds the `Bearer`;       |
|                          |                                 | without a token, OAuth from `/mcp`       |
+--------------------------+---------------------------------+------------------------------------------+
| `bearer-headers.js`      | linear, monday, youtrack        | Sends the token from the `.env` as       |
|                          |                                 | `Bearer`; in linear and monday it's      |
|                          |                                 | optional (without a token, OAuth)        |
+--------------------------+---------------------------------+------------------------------------------+
| `launch.js`              | all the `npx` ones              | Pinned versions of each package,         |
|                          |                                 | launching on Windows and shutting down   |
|                          |                                 | the process tree                         |
+--------------------------+---------------------------------+------------------------------------------+
| `read-env.js`            | all                             | Reads the `.env` with the same rules as  |
|                          |                                 | k0lmena and `scripts/_env.py`            |
+--------------------------+---------------------------------+------------------------------------------+
```

If a variable is missing, the script stops right away with a clear message (for example *"qtm4j: QTM4J_API_KEY missing from the root .env"*), which you can see in `/mcp`.

**Pinned versions**: the servers installed with `npx` (Playwright, Azure DevOps, QMetry/QTM4J, Appium and AIO's `mcp-remote`) use a specific version, defined in `scripts/mcp/launch.js`, never `@latest`: that way a new, unreviewed version doesn't receive your tokens without someone deciding so. To update, change the version there (to try one without touching the file: `PLAYWRIGHT_MCP_MCP_VERSION=0.0.84`, `AZURE_DEVOPS_MCP_MCP_VERSION=…`, etc.).

> Never put a token's real value in `.mcp.json`. To add a new connector with credentials, use `with-env.js` or your own script in `scripts/mcp/`.

---

## Xray

Xray **has no official MCP server** and the community ones don't cover folders, links to stories or evidence. That's why Xray (Cloud and Server/Data Center) is integrated with the built-in scripts in `scripts/management/`, on top of Xray's official API, and has no entry in `.mcp.json`. See [`scripts/management/README.md`](scripts/management/README.md).

## QMetry

It uses SmartBear's official server, [`@smartbear/mcp`](https://github.com/SmartBear/smartbear-mcp), which requires **Node.js 20+**. There are two connectors depending on which QMetry product you use; activate only yours.

**`qmetry` — QMetry Test Management (standalone):**

```
+-----------------+------------+------------------------------------------+
| Variable        | Required   | Description                              |
+=================+============+==========================================+
| QMETRY_API_KEY  | Yes        | QMetry Open API Key                      |
+-----------------+------------+------------------------------------------+
| QMETRY_BASE_URL | No         | https://testmanagement.qmetry.com by     |
|                 |            | default; change it if your instance uses |
|                 |            | another URL                              |
+-----------------+------------+------------------------------------------+
```

**`qtm4j` — QMetry Test Management for Jira (Cloud):**

```
+--------------------------+------------+------------------------------------------+
| Variable                 | Required   | Description                              |
+==========================+============+==========================================+
| QTM4J_API_KEY            | Yes        | QTM4J API Key                            |
+--------------------------+------------+------------------------------------------+
| QTM4J_BASE_URL           | No         | US (default):                            |
|                          |            | https://qtmcloud.qmetry.com · Australia: |
|                          |            | https://syd-qtmcloud.qmetry.com ·        |
|                          |            | Europe: https://eu-                      |
|                          |            | qtm4j-cloud.qmetry.com                   |
+--------------------------+------------+------------------------------------------+
| QTM4J_AUTOMATION_API_KEY | No         | Only for the automation tools; empty     |
|                          |            | disables them                            |
+--------------------------+------------+------------------------------------------+
```

Both entries run `scripts/mcp/with-env.js`, which takes these variables from the environment or, if they're not there, from the `.env`.

## AIO Tests

It uses AIO Tests' **official** MCP server, which is remote (nothing to install). Each tenant has its own URL.

```
+---------------+------------+------------------------------------------+
| Variable      | Required   | Description                              |
+===============+============+==========================================+
| AIO_MCP_URL   | Yes        | Server URL; copy it from **My Settings > |
|               |            | MCP Authorization** in AIO Tests         |
+---------------+------------+------------------------------------------+
| AIO_API_TOKEN | Yes        | Public API Token, from **My Settings >   |
|               |            | API Token**                              |
+---------------+------------+------------------------------------------+
```

The entry runs `scripts/mcp/aio-tests.js`, which takes both variables from the `.env` and connects to the remote server with [`mcp-remote`](https://github.com/geelen/mcp-remote) (through `npx`), passing the token only as an environment variable. Since the URL is specific to each tenant, it can't be hardcoded in `.mcp.json`.

**Token-free alternative (OAuth):** AIO Tests also accepts OAuth 2.1 if you use the Forge version of the app. In that case register the remote server just for you (`claude mcp add --transport http --scope local aio-tests <your AIO_MCP_URL>`), which takes precedence over the project entry, and authorize from `/mcp` > *Authenticate*.

---

## k0lmenaTMT

Connects the agents to **k0lmenaTMT** through its MCP server, to load and query test cases from the chat. It authenticates with a **personal token** (`kolm_pat_...`) generated in k0lmenaTMT.

```
+-------------------+------------+----------------------------------------+
| Variable          | Required   | Description                            |
+===================+============+========================================+
| K0LMENA_TMT_TOKEN | Yes        | k0lmenaTMT personal token. Goes in the |
|                   |            | root .env                              |
+-------------------+------------+----------------------------------------+
| K0LMENA_TMT_URL   | No         | http://localhost:4000/api/v1/mcp by    |
|                   |            | default; for another URL, define it in |
|                   |            | the .env before activating (or in the  |
|                   |            | environment)                           |
+-------------------+------------+----------------------------------------+
```

**The token is read from the `.env`**: the entry uses `headersHelper`, which runs `scripts/mcp/k0lmena-tmt-headers.js` every time Claude Code connects. The script takes `K0LMENA_TMT_TOKEN` from the environment or, if it's not there, from the `.env`, and builds the `Authorization: Bearer …` header. The token never ends up in `.mcp.json`.

To activate it:

1. Add `K0LMENA_TMT_TOKEN=<your token>` to the root `.env`.
2. Activate it: `npm run connector -- activate k0lmena-tmt`.
3. With k0lmenaTMT running, restart Claude Code and check with `/mcp`.

> Don't use `claude mcp add ... --header "Authorization: Bearer <token>"`: it leaves the token written in Claude Code's configuration.

Usage examples:

> *"Load the test cases from `output/test-cases/manual/cases-US-001.xlsx` into k0lmenaTMT."* · *"Which US-001 test cases are in k0lmenaTMT?"*

---

## Atlassian: Jira and Confluence

The `atlassian` connector is **Atlassian's official** MCP server (Rovo MCP Server). With **a single connection** it gives access to **Jira and Confluence** Cloud, with your user's permissions: the agents can read stories and their criteria from Jira and the functional documentation from Confluence pages, instead of copying them into `input/`.

**It comes enabled by default.** It has two ways to authenticate, chosen with `ATLASSIAN_MCP_AUTHENTICATION` in the `.env`:

- **`oauth` (default, recommended for interactive use)**: no token. The first time, run `/mcp`, choose `atlassian` and authorize access with your account in the browser.
- **`token`**: uses `JIRA_EMAIL` and `JIRA_API_TOKEN` (the same ones the Xray Cloud integration uses) and builds the `Authorization: Basic …` header. For a service account, put its API key in `ATLASSIAN_API_KEY` and it's sent as `Bearer`. **Requirement**: an Atlassian admin has to enable the API token in *Atlassian Administration > Rovo > Rovo MCP server > Authentication*. The token is created at https://id.atlassian.com/manage-profile/security/api-tokens.

The `.mcp.json` entry uses `headersHelper` (`scripts/mcp/atlassian-headers.js`): with `oauth` it adds nothing and with `token` it builds the header by reading the `.env`. The token never ends up in `.mcp.json`.

If your organization restricts AI apps, an Atlassian admin has to enable the Rovo MCP Server for the site.

**Bitbucket Cloud**: the same connector gives access to Bitbucket Cloud repositories (files, commits and pull requests), but **only with `ATLASSIAN_MCP_AUTHENTICATION=token`** (Bitbucket doesn't accept OAuth on the Rovo MCP Server yet) and with a workspace linked to the Atlassian organization. The `project-documenter` uses it (see [Application repository](#application-repository)).

Usage examples:

> *"Read Jira story PROJ-12 and analyze it."* · *"Generate the test cases for PROJ-12 using the Confluence page 'Billing rules' as documentation."*

---

## Figma

The `figma` connector is **Figma's official** MCP server. It gives the agents a design's context from a **link to a frame, a layer or a file**: texts, components, states and screenshots. It's useful for designing UI test cases (expected texts, visible validations, empty and error states), comparing the app against the design and giving context to the `web-mapper`.

- **Requirements**: a Figma **Full** or **Dev** seat (other seats have usage limits) and edit or view permission on the file.
- **No token**: it authenticates with your Figma account through OAuth.
- To activate it, either of these two options:
  - **Official plugin (recommended by Figma)**: `claude plugin install figma@claude-plugins-official`, restart Claude Code, go to `/plugin` → *Installed* → `figma` and authorize access. It includes the server and Figma skills.
  - **Server only**: `npm run connector -- activate figma` (or `figma-desktop` for the desktop app), restart and authorize from `/mcp`.
- **Desktop variant** (`figma-desktop`): for organizations that don't allow the remote server. It requires the Figma desktop app with the MCP server enabled (Dev mode → right panel) and connects to `http://127.0.0.1:3845/mcp`.

Usage examples:

> *"Generate the test cases for US-001 using this design as reference: https://www.figma.com/design/…?node-id=…"* · *"Compare the signup screen at https://your-app.com with the Figma design and report the differences."*

---

## Azure DevOps

It uses **Microsoft's official** MCP server, [`@azure-devops/mcp`](https://github.com/microsoft/azure-devops-mcp) (requires **Node.js 20+**). With a single connection the agents can:

- **Query stories** (*User Story*, *Product Backlog Item*, *Bug*) from Azure Boards with their comments, child tasks, parent (*Feature* / *Epic*) and links, and read the project **Wiki**. The `context-research` skill uses it, just like Jira and Confluence.
- **Read the repository in Azure Repos** (`repositories` domain, read-only for the `project-documenter`): files and folders, pull requests with their comments, and commit search.
- **Manage tests in Azure Test Plans**: create plans and suites, create test cases (*Test Case*) with their steps and expected result, link them to the story (*Tests* / *Tested By*) and add them to a suite. The `test-manager` agent does this.

```
+--------------------+----------------+------------------------------------------+
| Variable           | Required       | Description                              |
+====================+================+==========================================+
| ADO_ORGANIZATION   | Yes            | Organization name, the one in            |
|                    |                | `https://dev.azure.com/<organization>`   |
|                    |                | (not the URL)                            |
+--------------------+----------------+------------------------------------------+
| ADO_PAT            | Yes (with PAT) | Personal Access Token. Goes in the root  |
|                    |                | .env                                     |
+--------------------+----------------+------------------------------------------+
| ADO_PROJECT        | No             | Default project; if missing, it's        |
|                    |                | specified in each request                |
+--------------------+----------------+------------------------------------------+
| ADO_TEAM           | No             | Default team (backlog, iterations)       |
+--------------------+----------------+------------------------------------------+
| ADO_AUTHENTICATION | No             | `pat` (default), `interactive` (login in |
|                    |                | the browser) or `azcli` (`az login`      |
|                    |                | session)                                 |
+--------------------+----------------+------------------------------------------+
| ADO_TENANT         | No             | Microsoft Entra tenant, only with        |
|                    |                | `interactive` or `azcli`                 |
+--------------------+----------------+------------------------------------------+
| ADO_DOMAINS        | No             | Enabled areas. Default: `core work work- |
|                    |                | items repositories test-plans wiki       |
|                    |                | search`; add `pipelines` if you need it  |
+--------------------+----------------+------------------------------------------+
```

Just like k0lmenaTMT, **the configuration is read from the `.env`**: the entry runs `scripts/mcp/azure-devops.js`, which takes the variables from the environment or, if they're not there, from the `.env`, and starts the server passing it the PAT only as an environment variable. The token never ends up in `.mcp.json`.

**The PAT** is created in Azure DevOps > *User settings* > *Personal access tokens*, with the right organization and these minimum scopes:

```
+------------------+--------------+----------------------------------------+
| Scope            | Permission   | What for                               |
+==================+==============+========================================+
| Work Items       | Read & write | Read stories and comments; create test |
|                  |              | cases and links                        |
+------------------+--------------+----------------------------------------+
| Test Management  | Read & write | Plans, suites and test cases           |
+------------------+--------------+----------------------------------------+
| Project and Team | Read         | List projects and teams                |
+------------------+--------------+----------------------------------------+
| Wiki             | Read         | Read the project Wiki                  |
+------------------+--------------+----------------------------------------+
| Code             | Read         | Code search and `repositories` (Azure  |
|                  |              | Repos, project-documenter)             |
+------------------+--------------+----------------------------------------+
```

To activate it:

1. Add `ADO_ORGANIZATION`, `ADO_PAT` and, if you want, `ADO_PROJECT` to the root `.env` (see `.env.example`).
2. Activate it: `npm run connector -- activate azure-devops` (it's just for you; it tells you if any variable is missing).
3. Restart Claude Code and check with `/mcp`.

**Without a PAT:** with `ADO_AUTHENTICATION=interactive` the server opens the Microsoft login in the browser; with `azcli` it uses your `az login` session. Microsoft also offers a remote server (`https://mcp.dev.azure.com/<organization>`) that authenticates with Microsoft Entra; it doesn't accept a PAT.

**Limitations:** the server doesn't record run results (*test runs*) or upload evidence to Test Plans, so `results-publisher` doesn't support Azure DevOps yet. There's also no integration in `scripts/management/`: operations go through the MCP.

Usage examples:

> *"Read Azure DevOps story 1234 and analyze it."* · *"Upload the test cases from `cases-US-001.xlsx` to Azure Test Plans, in the 'Sprint 5' plan, 'US-001 Signup' suite, linked to story 1234."*

---

## Application repository

The `project-documenter` agent reads the application repository **read-only** (README and docs, validations, messages, statuses, permissions, routes, API contracts and the PRs and commits for each story) to leave the project context in `input/documentation/`. It's configured in the *App repository* block of the `.env`:

```
+-----------------+-----------------------------------------+
| Variable        | Description                             |
+=================+=========================================+
| REPO_PROVIDER   | `github`, `gitlab`, `azure-repos` or    |
|                 | `bitbucket`                             |
+-----------------+-----------------------------------------+
| REPO_NAME       | One or more, comma-separated:           |
|                 | `owner/repo` (GitHub), `group/project`  |
|                 | (GitLab), `project/repo` (Azure Repos), |
|                 | `workspace/repo` (Bitbucket)            |
+-----------------+-----------------------------------------+
| REPO_BRANCH     | Branch to document (empty = the default |
|                 | branch)                                 |
+-----------------+-----------------------------------------+
| REPO_LOCAL_PATH | Optional: a local clone of the same     |
|                 | repository. The code is read from there |
|                 | (faster and without spending connector  |
|                 | tokens); PRs and commits still go       |
|                 | through the connector                   |
+-----------------+-----------------------------------------+
```

Each provider uses its official MCP server:

- **GitHub** — `github` connector: the official remote server (`https://api.githubcopilot.com/mcp/readonly`) in **read-only mode** (`X-MCP-Readonly`), with the `context,repos,issues,pull_requests` toolsets (`GITHUB_TOOLSETS` to change them). It needs `GITHUB_TOKEN`: a *fine-grained* token with read-only permissions on the repositories (*Contents*, *Pull requests*, *Issues* and *Metadata*: Read-only). `scripts/mcp/github-headers.js` reads it from the `.env` and sends it as `Bearer`. The remote server doesn't support GitHub Enterprise Server.
- **GitLab** — `gitlab` connector: GitLab's official server at `<GITLAB_URL>/api/v4/mcp` (GitLab.com, or Self-Managed and Dedicated from 19.5, on all plans; on GitLab.com the group has to allow access to the MCP server). Without `GITLAB_TOKEN` you authorize with your account (OAuth) from `/mcp`; with a token, it has to be a *fine-grained* personal access token with the *MCP tool* resource and the *Execute* permission (classic tokens are rejected with 403). `scripts/mcp/gitlab-headers.js` limits the toolsets to `meta,core,merge_requests,work_items,repository,wikis` (`GITLAB_TOOLSETS`). The URL is taken from the `.env` when you activate it: if you change `GITLAB_URL`, activate the connector again.
- **Azure Repos** — `azure-devops` connector, with the `repositories` domain (included by default in `ADO_DOMAINS`) and the PAT with *Code (Read)*. See [Azure DevOps](#azure-devops).
- **Bitbucket Cloud** — `atlassian` connector with `ATLASSIAN_MCP_AUTHENTICATION=token` and an API token with the Bitbucket permissions. Bitbucket Data Center isn't supported by the Rovo MCP Server. See [Atlassian](#atlassian-jira-and-confluence).

To activate GitHub or GitLab:

1. Fill in the *App repository* block of the `.env` (see `.env.example`).
2. `npm run connector -- activate github` (or `gitlab`).
3. Restart Claude Code and check with `/mcp` (with GitLab without a token, authorize with your account the first time).

**Read-only**: GitHub already starts in read-only mode. GitLab, Azure DevOps and Atlassian also expose write tools (creating branches, files or PRs): the `project-documenter` is forbidden from using them, Claude Code asks for confirmation before each one, and the token should have read permissions.

Usage examples:

> *"Document the project"* · *"Gather all the context for PROJ-12 before writing the test cases"*

---

## Other project management tools

If your team doesn't work with Jira or Azure DevOps, stories are read just the same from your tool: each one has its **official** MCP server and the `context-research` skill goes through the same sources (description, criteria, comments, subtasks or checklists, parent, links) using each tool's names. That way the analyst, the strategist, the test case generators, the mappers and the `project-documenter` all benefit from it.

```
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| Connector   | Server                              | Authentication                         | What it provides                        |
+=============+=====================================+========================================+=========================================+
| linear      | https://mcp.linear.app/mcp/readonly | OAuth, or `LINEAR_API_KEY` (read-only  | Issues, comments, sub-issues, projects, |
|             |                                     | key)                                   | cycles and relations. Read-only         |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| clickup     | https://mcp.clickup.com/mcp         | OAuth only                             | Tasks, subtasks, checklists, comments   |
|             |                                     |                                        | and Docs                                |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| monday      | https://mcp.monday.com/mcp          | OAuth, or `MONDAY_API_TOKEN` (personal | Board items, subitems, updates          |
|             |                                     | token)                                 | (comments) and docs                     |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| asana       | https://mcp.asana.com/v2/mcp        | OAuth with your own MCP app            | Tasks, subtasks, comments, projects and |
|             |                                     | (`ASANA_CLIENT_ID`,                    | sections                                |
|             |                                     | `ASANA_CLIENT_SECRET`)                 |                                         |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| trello      | https://mcp.trello.com/v1           | OAuth only                             | Cards, lists, checklists and comments   |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| notion      | https://mcp.notion.com/mcp          | OAuth only                             | Pages, databases (backlogs) and wikis   |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| youtrack    | `<YOUTRACK_URL>/mcp`                | `YOUTRACK_TOKEN` (permanent token)     | Issues, comments, links, tags and       |
|             |                                     |                                        | knowledge base articles                 |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
| shortcut    | https://mcp.shortcut.com/mcp        | OAuth only                             | Stories, epics, comments, tasks and     |
|             |                                     |                                        | documents                               |
+-------------+-------------------------------------+----------------------------------------+-----------------------------------------+
```

To activate any of them:

1. If it uses variables, fill them in the *Other project management tools* block of the `.env` (see `.env.example`).
2. `npm run connector -- activate <name>` (for example `linear`).
3. Restart Claude Code, go to `/mcp` and, if it's OAuth, authorize with your account.

Details per tool:

- **Linear**: the connector points to the **read-only** endpoint (`/mcp/readonly`), which is enough for reading stories. With `LINEAR_API_KEY` (a key with *Read* permission) OAuth is skipped.
- **ClickUp**: OAuth only; when authorizing you choose the Workspace. ClickUp doesn't accept API tokens on its MCP server.
- **monday.com**: with OAuth an account admin may need to approve the connection; with `MONDAY_API_TOKEN` (your personal token, no admin approval) the `headersHelper` sends it as `Bearer`.
- **Asana**: the V2 server **doesn't accept automatic OAuth client registration**, so you need your own app: at https://app.asana.com/0/my-apps, *Create new app* > *MCP app*, redirect URL `http://localhost:8080/callback`, and the workspaces in *Manage distribution*. Copy the Client ID and Client secret to the `.env`; `npm run connector -- activate asana` registers it with `claude mcp add --client-id … --client-secret --callback-port 8080`. The secret is stored in the system keychain (if Claude Code doesn't pick it up from the variable, it asks for it, hidden, in the terminal). The old server (`/sse`, V1) is no longer available.
- **Trello**: it's Trello's official server (separate from Atlassian's Rovo MCP Server). When authorizing you choose the workspaces and the permissions (*Read*, *Write*, *Search*); it doesn't delete anything (it only archives). In Enterprise organizations, an admin can restrict it from *Atlassian Administration > Connectors*.
- **Notion**: OAuth only (it doesn't accept tokens). It reads what the connection can see in your workspace; useful for backlogs built as databases and for project documentation.
- **YouTrack**: the MCP server is built into YouTrack Cloud and recent YouTrack Server, at `<your site>/mcp`. YouTrack doesn't accept dynamic OAuth client registration, so the connector uses a *permanent token* (Profile > *Account Security* > *New token*, with the YouTrack scope) that `bearer-headers.js` reads from the `.env`. The URL is taken from the `.env` when you activate it.
- **Shortcut**: the official remote server (the `@shortcut/mcp` npx package was archived); OAuth only.
- **GitHub Issues and Projects, GitLab Issues and work items**: they don't need another connector, `github` and `gitlab` read them (see [Application repository](#application-repository)).

**Write tools modify shared data**: except for Linear (read-only), these servers can also create or edit tasks. The k0lmenIA agents only read them, and Claude Code asks for confirmation before each write action.

Usage examples:

> *"Analyze Linear story ENG-142"* · *"Generate the test cases for the Trello card 'Checkout with coupons'"* · *"Gather the context of the Asana task 'Customer signup' before writing the test cases"*

---

## Appium (for the mobile-mapper)

It isn't a test management tool: it's **Appium's official** MCP server, [`appium-mcp`](https://github.com/appium/appium-mcp), which the `mobile-mapper` agent uses to walk through an app on a device or emulator. It requires **Node.js 22+**, a JDK and, for Android, the Android SDK (the UiAutomator2 and XCUITest drivers are included). For iOS you need macOS with Xcode.

```
+--------------+---------------+-------------------------+
| Variable     | Required      | Description             |
+==============+===============+=========================+
| ANDROID_HOME | Yes (Android) | Path to the Android SDK |
+--------------+---------------+-------------------------+
```

Activate it with `npm run connector -- activate appium-mcp`. `ANDROID_HOME` is taken from the environment or, if it's not there, from the `.env` (with `scripts/mcp/with-env.js`). The suite the mapper generates then runs without MCP, with `npm run test:mobile`, on a device, emulator or BrowserStack (see `tools/k0lmena/README.md`).

---

## Salesforce (for the salesforce-tester)

It's the **official Salesforce DX** MCP server, [`@salesforce/mcp`](https://github.com/salesforcecli/mcp), which the `salesforce-tester` agent uses to query an org. **k0lmenIA starts it restricted to read-only**: it enables only the `data` toolset (**SOQL** queries) and the `run_apex_test` tool (Apex tests). It doesn't enable metadata (deploy/retrieve) or user/permission management.

It requires the **Salesforce CLI** (`npm install --global @salesforce/cli`, Node.js 18+) and the org **authorized locally** before using it:

```bash
sf org login web --alias my-qa-sandbox --instance-url https://test.salesforce.com
```

```
+----------------------------+------------+----------------------------------------+
| Variable                   | Required   | Description                            |
+============================+============+========================================+
| SALESFORCE_AUTHORIZED_ORGS | Yes        | Aliases of the allowed orgs (sandbox), |
|                            |            | comma-separated                        |
+----------------------------+------------+----------------------------------------+
| SALESFORCE_ORG             | Yes        | The alias of the org it connects to    |
|                            |            | (from the list)                        |
+----------------------------+------------+----------------------------------------+
```

The connector points to **one** specific org (`SALESFORCE_ORG`), which has to be in `SALESFORCE_AUTHORIZED_ORGS`; never `ALLOW_ALL_ORGS`. The authorization lives in the local CLI, so **no token travels through `.mcp.json`**. Activate it with `npm run connector -- activate salesforce`. The read-only survey (without this MCP, with the CLI directly) is done by `npm run salesforce` (see `tools/salesforce/README.md`).

---

## Best practices

- **Write tools modify shared data** (creating or editing test cases, importing results). That's why the connectors aren't added to `permissions.allow`: Claude Code asks for confirmation before each action.
- Use a **test project** or a **service user** with limited permissions when testing the connection.
- If a token leaks (for example, if it gets committed), **rotate it immediately**.

## Sources

- Atlassian Rovo MCP Server: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/getting-started-with-the-atlassian-remote-mcp-server/
- Atlassian Rovo MCP Server, API token authentication: https://support.atlassian.com/atlassian-rovo-mcp-server/docs/configuring-authentication-via-api-token/
- Figma MCP Server (remote): https://help.figma.com/hc/en-us/articles/35281350665623
- Figma MCP Server with Claude Code: https://help.figma.com/hc/en-us/articles/39888612464151
- SmartBear MCP (QMetry and QTM4J): https://github.com/SmartBear/smartbear-mcp
- AIO Tests MCP Server, setup guide: https://aiosupport.atlassian.net/wiki/spaces/AioTests/pages/3097624764/AIO+Tests+MCP+Server+Setup+Configuration+Guide
- AIO MCP Tools: https://aiosupport.atlassian.net/wiki/spaces/AioTests/pages/3115253762/AIO+MCP+Tools
- Xray Cloud GraphQL API (built-in integration): https://docs.getxray.app/display/XRAYCLOUD/GraphQL+API
- Xray Server/DC REST API (built-in integration): https://docs.getxray.app/display/XRAY/REST+API
- Appium MCP (official): https://github.com/appium/appium-mcp
- Salesforce DX MCP Server (official): https://github.com/salesforcecli/mcp
- Azure DevOps MCP Server (official): https://github.com/microsoft/azure-devops-mcp
- Linear MCP Server: https://linear.app/docs/mcp
- ClickUp MCP Server: https://developer.clickup.com/docs/connect-an-ai-assistant-to-clickups-mcp-server-1
- monday.com MCP: https://developer.monday.com/api-reference/docs/integrate-with-monday-mcp
- Asana MCP Server V2: https://developers.asana.com/docs/integrating-with-asanas-mcp-server · with Claude Code: https://developers.asana.com/docs/connecting-mcp-clients-to-asanas-v2-server
- Trello MCP: https://support.atlassian.com/trello/docs/connect-trello-to-ai-assistants-with-trello-mcp/
- Notion MCP: https://developers.notion.com/docs/get-started-with-mcp
- YouTrack MCP Server: https://www.jetbrains.com/help/youtrack/cloud/model-context-protocol-server.html · Server: https://www.jetbrains.com/help/youtrack/server/model-context-protocol-server.html
- Shortcut MCP: https://www.shortcut.com/help/integrations/mcp-server
- Azure DevOps MCP, tools by domain: https://github.com/microsoft/azure-devops-mcp/blob/main/docs/TOOLSET.md
- GitHub MCP Server: https://github.com/github/github-mcp-server (remote server: https://github.com/github/github-mcp-server/blob/main/docs/remote-server.md)
- GitLab MCP Server: https://docs.gitlab.com/user/model_context_protocol/mcp_server/
- Bitbucket Cloud on the Atlassian Rovo MCP Server: https://www.atlassian.com/blog/bitbucket/the-atlassian-rovo-mcp-server-now-supports-bitbucket-cloud
- Azure DevOps MCP, authentication: https://github.com/microsoft/azure-devops-mcp/blob/main/docs/GETTINGSTARTED.md
