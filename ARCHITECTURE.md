# Repository architecture

This repo is designed to grow in an orderly way. It covers both **planning and generating** QA artifacts (test plan, story analysis, manual cases, BDD, API cases, test data, bug reports) and **running** tests (end-to-end in the browser and API) and **reporting** the results (a report for each run and the closure report for the round). So that each new capability fits in without breaking what already works, everything is organized into pieces, each with its own place.

## The pieces

![How the pieces relate](docs/assets/img/relationships.png)

The agent is the center: it loads **skills** (the how), follows the **templates** (the format), runs **scripts** (the mechanical part) and **tools** (from the terminal), and uses **MCP connectors** to talk to external systems; it reads from `input/` and leaves everything in `output/`. The diagram is edited in `docs/diagrams/relationships.html` and regenerated with `node docs/generate.js`.

### Agents — the *who* (`.claude/agents/`)

Each agent is a Claude Code subagent with its role, its process and its rules. It is who you delegate an entire task to. There are forty-two today, grouped into project documentation, analysis and design (including bug triage, product questions and onboarding), live execution (including exploratory, accessibility, web performance, role permissions and resilience testing, visual regression, cross-browser, emails and translations), reports (with failure analysis, coverage and the quality dashboard), automation with k0lmena (with locator repair), case selection by change, security and management (the catalog, with the skills, tools and connectors of each one, is in `AGENTS.md`). Since they run as subagents, they can't ask the person questions mid-task: if they are missing a piece of information, they finish by returning "I need you to confirm" and the main conversation asks and continues them. The key for each one is the `description` in its frontmatter: it is what Claude Code uses to know when to invoke it.

### Skills — the *how* (`.claude/skills/`)

Packaged knowledge that Claude Code loads **on demand** (only when needed). It encapsulates the "how" of a reusable capability, so several agents can use it without repeating instructions. Each skill is a folder with a `SKILL.md` (see `.claude/skills/README.md`).

> What an agent uses to **act** comes in three forms: MCP connections, external tools and internal scripts.

### MCP — connections to external systems (`.mcp.json`)

To touch outside systems (Jira, Xray, a browser…), an agent uses an **MCP server**. **It is a single file, but it scales to as many connections as you want**: `.mcp.json` is a *registry* of servers, where you add one entry per integration.

```json
{
  "mcpServers": {
    "atlassian":  { "type": "http", "url": "https://mcp.atlassian.com/v2/mcp" },
    "qtm4j":      { "type": "stdio", "command": "node", "args": ["scripts/mcp/with-env.js", "qtm4j", "--required", "QTM4J_API_KEY", "--", "@smartbear/mcp"], "env": { "MCP_CLIENTS": "QTM4J" } },
    "playwright": { "type": "stdio", "command": "node", "args": ["scripts/mcp/playwright.js"] }
  }
}
```

In this repo, `.mcp.json` comes **versioned with the connectors everyone uses** (Playwright headed and headless, and Atlassian for Jira and Confluence), all enabled in `.claude/settings.json`: that way Claude Code starts right away, without asking for approvals. The optional ones (Azure DevOps, Figma, GitHub, GitLab, QMetry, AIO Tests, k0lmenaTMT, Appium) are in `scripts/mcp/catalog.json` and each person enables them with `npm run connector -- activate <name>`, which registers them with Claude Code's local scope (only for that person, without touching versioned files). **None of them carries secrets**: the ones that need a token start with a script in `scripts/mcp/` that reads it from `.env`.

> **Golden rule for secrets:** tokens and credentials go in the local `.env` (gitignored) or in environment variables, **never** with the real value in `.mcp.json` or in any other versioned file. There is a `.env.example` template with the variable names; copy it to `.env` and fill in the real values. If a secret gets committed, rotate it immediately.

### Tools — external testing tools (`tools/`)

Tools the agent **runs** from the command line, with their templates and configurations. Four are integrated: **Mailpit**, the test mailbox that `email-verifier` uses to catch the app's emails; **Newman** (the Postman CLI), which `api-runner` uses to run API tests; **OWASP ZAP**, which `security-analyst` uses for passive security scanning; and **k0lmena**, the automation framework (web, api, mobile and performance with k6, Artillery and JMeter, plus checks on PostgreSQL, MySQL / MariaDB, SQL Server and MongoDB databases, the exploratory crawl `npm run explore` used by `web-explorer`, the accessibility audit `npm run accessibility` used by `accessibility-analyst`, the web performance audit `npm run web-performance` (Lighthouse) used by `web-performance-auditor`, the visual regression `npm run pixel-perfect` used by `pixel-perfect`, the Chromium, Firefox and WebKit tests `npm run cross-browser` used by `cross-browser`, the locator repair `npm run repair` used by `automation-repairer`, the email review `npm run emails` used by `email-verifier` and the language review `npm run translator` used by `translation-analyst`). On top of those come **streaming** (ffprobe/ffmpeg and ONVIF) for the video and camera agents, and **Salesforce** (the `sf` CLI), which `salesforce-tester` uses to survey an org in read-only mode. They all keep their last 5 runs in `history/` to compare them. In k0lmena the *mapper* agents write the automation only once and then it runs with `npm test`, **with no agents and no tokens**. Each tool goes in its **own subfolder**, so it scales: adding a tool = adding a folder (see `tools/README.md`).

### Scripts — internal utilities (`scripts/`)

The repo's own Python code for mechanical tasks (generating the `.xlsx` spreadsheet, normalizing tables). It includes `scripts/management/`, the integration with Xray, QMetry (QTM4J) and AIO Tests over their official APIs: the agents decide what to do and the script does it, without depending on MCP servers. New internal utilities live here.

### Evals — agent quality (`evals/`)

The tests (`tests/`) cover the scripts; the **evals** measure the quality of what the agents generate. Each case brings inputs with deliberate traps and versioned deterministic checks; `scripts/evaluate_agents.py` runs them in an isolated workspace with `claude -p` and builds a report with the regressions against the previous run. When you change an agent or a skill, run them before and after.

## In short

- **Agent** = who I ask to do the task.
- **Skill** = the knowledge of how to do it.
- **MCP** = connections to external systems (one file, many connections: Jira, Confluence, Figma, QMetry, AIO Tests, Azure DevOps, Playwright…).
- **Tools** = external tools run from the CLI (Newman and k0lmena).
- **Script** = deterministic internal utility.

All five pieces are already in use today: **agents**, **skills** (context research, design techniques, E2E and API execution, automation with k0lmena), the **MCP connection** with Playwright (for the browser), the **tools** Newman (for API) and k0lmena (token-free automation) and the formatting, reporting and conversion **scripts**. Adding new capabilities means repeating the pattern: a new agent in `.claude/agents/`, a skill in `.claude/skills/`, a connection in `.mcp.json`, a tool in `tools/` or a script in `scripts/`.
