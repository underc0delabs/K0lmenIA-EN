# Scripts

The repo's own **Python** utilities: mechanical, repeatable tasks that are better done by code than by the model (exact formatting, calculations, file generation).

Current ones:

- `generate_cases.py` — generates the `.xlsx` spreadsheet and the `.md` of test cases (sorted by priority). Accepts `--clean`.
- `format_tables.py` — normalizes the tables of any `.md` to an aligned format.
- `documentation_index.py` — builds `input/documentation/INDEX.md` from the header of each document: type, sources, date and whether it should be reviewed (`project-documenter`).
- `generate_report.py` — generates a self-contained HTML report (dashboard) of a run, from a results JSON.
- `newman_to_results.py` — converts the Newman output (JSON) to the format consumed by `generate_report.py`, so the API tests use the same report.
- `generate_plan.py` — generates the **test plan** in HTML (dark dashboard) from a JSON.
- `generate_closure_report.py` — generates the **closure report** of a round in HTML (dark dashboard) from a JSON.
- `generate_performance_report.py` — generates the **performance report** in HTML (dark dashboard): takes the metrics from the `npm run perf` summaries and adds the plan, the findings and the recommendations from the `performance-mapper` JSON.
- `management/` — integration with **Xray (Cloud and Server/DC), QMetry for Jira (QTM4J) and AIO Tests**: folders, cases, links to stories, cycles and result publishing. Includes `to_azure_devops.py`, which converts the cases (`.xlsx` / `.feature`) to the Azure Test Plans format for the `azure-devops` MCP connector. Used by the `test-manager` and `results-publisher` agents (results are uploaded with their evidence).
- `mcp/` — launchers for the MCP connectors in `.mcp.json`: they read the credentials from `.env` and pass them to the server without writing them to any versioned file; the `npx` servers use pinned versions (`launch.js`). See `CONNECTORS.md`.
- `run_newman.py` — runs a Postman collection with the token and URL from `.env` (PowerShell, bash and zsh) and leaves its HTML report (`api-runner`).
- `collect_results.py` — gathers the results of a story (live runs, `npm test`, bugs, performance and security) for the closure report.
- `generate_security_report.py` — generates the **web security report** in HTML from the OWASP ZAP `zap.json` and the agent's analysis.
- `generate_exploratory_report.py` — generates the **exploratory testing report** in HTML from the `exploration.json` of `npm run explore` and the analysis of the `web-explorer` agent.
- `generate_accessibility_report.py` — generates the **accessibility report** in HTML from the `audit.json` of `npm run accessibility` and the analysis of the `accessibility-analyst` agent.
- `generate_web_performance_report.py` — generates the **web performance report** in HTML from the `web-performance.json` of `npm run web-performance` (Lighthouse) and the analysis of the `web-performance-auditor` agent.
- `_report_styles.py` — the design system of every HTML report, in the k0lmena.com style (sidebar with an index, bento grid, indicators, charts and tables with search and filters); `fonts/` holds the k0lmena.com typefaces (Saira, Inter and JetBrains Mono) that are embedded in each report.
- `analyze_failures.py` + `generate_failures_report.py` — classify the `npm test` failures, compare with retries to detect flaky tests, recover the evidence and build the **failure analysis report** (`failure-analyst`).
- `analyze_coverage.py` + `generate_coverage_report.py` — build the **coverage and traceability matrix** per story (criteria, cases, automation, management, results and bugs) and the report with the gaps (`coverage-analyst`).
- `select_cases.py` + `generate_selection_report.py` — cross a change (git, PR, Jira, release notes) with the case inventory and build the **risk-prioritized selection** with the `npm test` command, the CSV of the manual part and the changes without coverage (`test-case-selector`).
- `generate_pixel_perfect_report.py` — generates the **visual regression report** from the `pixel-perfect.json` of `npm run pixel-perfect`, with the reference/actual slider comparator (`pixel-perfect`).
- `generate_cross_browser_report.py` — generates the **cross-browser report** from the `cross-browser.json` of `npm run cross-browser` (`cross-browser`).
- `generate_repair_report.py` — generates the **automation repair report** from the `repairs.json` of `npm run repair` (`automation-repairer`).
- `generate_emails_report.py` — generates the **emails report** from the `emails.json` of `npm run emails` (`email-verifier`).
- `generate_translation_report.py` — generates the **translations report** from the `translator.json` of `npm run translator` (`translation-analyst`).
- `_history.py` — keeps the **last 5 runs** of each tool in `history/` and builds the "Run history" section of the reports (new, resolved, indicators over time).
- `estimation.py` — **estimated manual run time** of each case and each step (formula in `templates/time-estimation.md`); also from the console: `python scripts/estimation.py cases.xlsx`.
- `review_cases.py` + `generate_review_report.py` — review of the quality of the cases (`case-reviewer`).
- `generate_charters.py` — session sheets and the report of the exploratory sessions (`charter-generator`).
- `generate_ux_report.py` and `generate_forms_report.py` — the reports of `npm run ux` and `npm run forms` (`ux-evaluator`, `form-tester`).
- `analyze_logs.py` + `generate_logs_report.py` — logs grouped and cross-referenced with the run (`log-analyst`).
- `generate_permissions_report.py` and `generate_resilience_report.py` — the reports of `npm run permissions` and `npm run resilience` (`permissions-tester`, `resilience-tester`).
- `find_duplicates.py` — similarity between bugs: duplicates, possible regressions and related ones (`bug-triager`).
- `quality_dashboard.py` — quality dashboard per sprint or release (`quality-dashboard`).
- `reports_portal.py` — `output/index.html` with the latest report of each tool; `_report_styles.page()` schedules it to regenerate when each report finishes (`K0LMENIA_PORTAL=0` turns it off).
- `notify.py` — notifications to Slack and Teams via the `.env` webhook; `--from-cucumber` summarizes an `npm test`.
- `generate_monitoring_report.py` — report of `npm run monitor` (synthetic monitoring) with availability and timings.
- `documentation_changes.py` — incremental documentation for the `project-documenter`: status of what was documented and which documents and cases a change affects.
- `convert_collection.py` — Bruno and Insomnia to Postman v2.1 (used by `run_newman.py`); `summarize_graphql.py` — summary of a GraphQL schema (introspection, SDL or JSON); `summarize_openapi.py` — summary of a Swagger/OpenAPI to automate it (base URL, authentication, endpoints, bodies and statuses).
- `evaluate_agents.py` — agent evals (`evals/`): prepare the isolated workspace, run with `claude -p`, verify and build the report with regressions.
- `token_metrics.py` — token usage and estimated cost per agent from the Claude Code transcripts (counts only).
- `generate_onboarding.py` — onboarding plan for the `onboarding-guide` (HTML with a checklist and Markdown).
- `doctor.py` — checks the environment (Python, Node, k0lmena, Playwright, Newman, Java, Docker, `.env` and connectors) and says what is missing. Also: `npm run doctor`.
- `_env.py` — reads the root `.env` with the same rules as k0lmena and `scripts/mcp/read-env.js` (used by the Python scripts).
- `_report_styles.py` — design system of every HTML report (plan, run, closure, performance and security): dark mode, categorical and status palettes validated for color blindness and contrast, indicators, pills with icons, tooltips and charts (donut, bars, stacked bars, grouped columns and lines with crosshair, always with a single axis). The k0lmena reports use the same colors (`tools/k0lmena/reports/dark-theme.js` and the performance report).

They need **Python 3** (see `requirements.txt`).

> Not to be confused with `tools/` (external testing tools such as JMeter, which the agents run from the CLI) or with `.mcp.json` (connections to external systems over MCP, such as Jira or Xray).
