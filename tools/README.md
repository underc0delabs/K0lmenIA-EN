# Tools

This is where the **external testing tools** that the agents use to *run* (not to generate) are integrated: tools that run from the command line or that need their own configuration files and templates.

Each tool goes in its **own subfolder**, so the repo scales without collisions: adding a tool = adding a folder.

```
tools/
├── newman/          # Postman CLI: runs API test collections (integrated)
├── zap/             # OWASP ZAP: passive web security, in Docker (integrated)
│   └── README.md    # what it is, installation and how the agent uses it
├── k0lmena/         # Automation framework (integrated): web, api, mobile and performance
│   ├── web/ api/ mobile/ performance/
│   └── README.md    # installation, npm test and how the mappers use it
├── streaming/       # ffmpeg/ONVIF: video, cameras and recordings (streaming agents)
├── salesforce/      # sf CLI: QA inventory of a Salesforce org (salesforce-tester)
├── ecommerce/       # Shopify and WordPress/WooCommerce: functional survey of stores (shopify-tester, wordpress-tester)
└── ...              # others: a subfolder + its README
```

The integrated ones:

- **Mailpit** (in `mailpit/`): a test mailbox that catches the app's emails; used by the `email-verifier` agent (`npm run emails`) and the k0lmena email steps.
- **Newman** (in `newman/`): used by the `api-runner` agent to run API tests.
- **OWASP ZAP** (in `zap/`): used by the `security-analyst` agent to scan, in passive mode, your own or authorized sites and build the security report.
- **k0lmena** (in `k0lmena/`): a copy of the [underc0delabs/k0lmena](https://github.com/underc0delabs/k0lmena) framework. The `web-mapper`, `api-mapper` and `mobile-mapper` agents generate the `.feature` files, steps and locators there, and then the suite runs with `npm test` without agents or tokens. The `performance-mapper` generates the k6, Artillery and JMeter scripts, which run with `npm run perf`. The `data-verifier` queries the databases in the `.env` (`npm run db`) and, if asked, adds database checks to the `.feature` files. The `web-explorer` crawls the site with `npm run explore` (links, images, errors, responsive and load times, with screenshots, videos and an HTML report), the `accessibility-analyst` audits WCAG 2.2 with `npm run accessibility` (axe-core, keyboard and reflow), the `web-performance-auditor` measures load speed with `npm run web-performance` (Lighthouse), the `pixel-perfect` agent does visual regression with `npm run pixel-perfect`, the `cross-browser` agent tests on Chromium, Firefox and WebKit with `npm run cross-browser` and the `automation-repairer` diagnoses and repairs locators with `npm run repair` (it uses the DOM the web suite saves on failure in `reports/web/dom/`), the `email-verifier` reviews the emails with `npm run emails`, the `translation-analyst` the languages with `npm run translator`, the `ux-evaluator` usability with `npm run ux` and the `form-tester` validations with `npm run forms`. The `permissions-tester` builds the per-role matrix with `npm run permissions`, the `resilience-tester` simulates API, network and resource failures with `npm run resilience` and `npm run monitor` does read-only synthetic monitoring (with alerts to Slack and Teams). The `project-documenter` builds the site's functional map with `npm run functional-map` (pages, menus, forms with their fields, buttons and messages, without submitting anything) in `input/documentation/`. Each tool keeps its last 5 runs in `history/`, and `npm test` keeps its own in `reports/<suite>/history/`.
- **streaming** (in `streaming/`): ffprobe/ffmpeg and ONVIF for the video and camera agents (`streaming-tester`, `onvif-tester`, `image-quality-analyst`, `recording-verifier`, `camera-security-analyst`). See `tools/streaming/README.md`.
- **salesforce** (in `salesforce/`): the `sf` CLI to survey a Salesforce org read-only (`salesforce-tester`, `npm run salesforce`). See `tools/salesforce/README.md`.
- **ecommerce** (in `ecommerce/`): read-only functional surveys of Shopify stores (`npm run shopify`, optional Admin API and Theme Check) and WordPress / WooCommerce (`npm run wordpress`, optional WooCommerce REST API and WP-CLI), for the `shopify-tester` and the `wordpress-tester`. See `tools/ecommerce/README.md`.

New ones are added with the same pattern: a subfolder + its README.

> How is this different from `scripts/` and `.mcp.json`?
> - **`tools/`** → external tools that run through a CLI (Newman, ZAP, k0lmena with k6, Artillery and JMeter…), with their templates and configs.
> - **`scripts/`** → the repo's own Python utilities (they generate or format the artifacts).
> - **`.mcp.json`** → connections to external systems through the MCP protocol (Jira, Xray, browser via Playwright…).
