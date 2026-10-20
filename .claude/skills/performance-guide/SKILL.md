---
name: performance-guide
description: Step-by-step guide for planning a performance test together with the person — goal and test type (smoke, load, stress, soak, spike), tool (k6, Artillery + Playwright or JMeter, with a justified recommendation), environment and scope, concurrent users, ramp-up, duration and think time (with suggested calculations), thresholds and run plan — and leaves the confirmed plan for the performance-mapper. Use it in the main conversation when the person asks for a performance, load, stress, soak or spike test, before invoking the performance-mapper, and at the end to put together the final report.
---

# Performance guide

The person doesn't need to know about performance: **you guide them**. You explain each decision in two or three lines, you **suggest** values with the reasoning behind them, and they confirm or change them. Nothing is applied without their confirmation.

**Who does what:** you run the interview in the **main conversation** (subagents can't ask the person questions while they work). With the plan confirmed, the **`performance-mapper`** agent generates the script, validates it, runs the tests and builds the final report.

## How to ask

- **One stage per message**, in order. Use the question tool with concrete options and put the recommended one first, marked "(Recommended)" and with the reason. The person can always type a different answer.
- **Suggesting is not making things up**: every suggestion is presented as such ("I suggest 50 users because…"), and if the person accepts it, it's recorded in the plan as an **accepted assumption**. If a piece of data is needed and nobody can define it, it stays as `MI-XX` (skill `context-research`).
- If the person already gave a piece of data (in the request, the story or the context sheet), don't ask for it again: confirm it in the summary.
- If the person says "you decide" or "whatever you recommend", apply your suggestions and show them all together in the final summary so they can confirm.

## Stage 0 — Context (without asking)

Before the first question, gather what already exists:

- The `output/context/context-<US>.md` sheet or the `context-research` skill: the **non-functional requirements** (response times, expected users, SLA) are often in the epic, in Confluence or in comments.
- What can be measured: a Postman collection, Swagger/OpenAPI, k0lmena automation (`tools/k0lmena/api` or `web`), a `.jmx` the person brings, or test cases.
- If there are previous runs in `tools/k0lmena/reports/performance/`, they serve as a baseline.

## Stage 1 — Goal and test type

Ask **what they want to find out** and suggest the test type that answers it:

```
+------------------------------------------+-----------------+------------------------------------------+
| The person's goal                        | Suggested type  | What it does                             |
+==========================================+=================+==========================================+
| "Can it handle normal usage / the        | `load`          | Ramps up to the target load, holds it    |
| expected peak?"                          |                 | and ramps down                           |
+------------------------------------------+-----------------+------------------------------------------+
| "How far can it go? Where does it        | `stress`        | Increasing steps (1x, 2x, 3x) until it   |
| break?"                                  |                 | degrades                                 |
+------------------------------------------+-----------------+------------------------------------------+
| "Does it degrade over time? (memory,     | `soak`          | Moderate load for hours                  |
| connections)"                            |                 |                                          |
+------------------------------------------+-----------------+------------------------------------------+
| "What happens with a sudden spike?       | `spike`         | Jumps abruptly to several times the load |
| (campaign, launch)"                      |                 | and back                                 |
+------------------------------------------+-----------------+------------------------------------------+
| "I just want to see the script work"     | `smoke`         | 1-2 users, less than 1 minute            |
+------------------------------------------+-----------------+------------------------------------------+
```

`smoke` **always goes first** (it validates the script). Several types can be chosen (the usual: smoke → load → stress).

## Stage 2 — Tool

Show the comparison and recommend one based on what's being measured:

```
+----------------------------+---------------------------------------+----------------------------------------+--------------------------------------+
| Tool                       | Best for                              | Pros                                   | Cons                                 |
+============================+=======================================+========================================+======================================+
| **k6**                     | HTTP APIs                             | Very lightweight: thousands of users   | HTTP/WebSocket/gRPC only; doesn't    |
|                            |                                       | from one PC; versionable TypeScript    | measure the in-browser experience    |
|                            |                                       | scripts                                |                                      |
+----------------------------+---------------------------------------+----------------------------------------+--------------------------------------+
| **Artillery + Playwright** | Web flows in the browser              | Measures what the user sees (time per  | Each user is a Chromium: 10-20       |
|                            |                                       | step, Web Vitals)                      | concurrent per PC                    |
+----------------------------+---------------------------------------+----------------------------------------+--------------------------------------+
| **JMeter**                 | HTTP APIs if the team already uses    | Well-known standard, many protocols,   | Heavier (Java); the `.jmx` is XML,   |
|                            | JMeter, there's a `.jmx` to reuse, or | its own dashboard                      | less readable                        |
|                            | other protocols (JDBC, JMS, SOAP, TCP)|                                        |                                      |
+----------------------------+---------------------------------------+----------------------------------------+--------------------------------------+
```

Recommendation rules: an API with no other condition → **k6**; in-browser experience → **Artillery**; a team using JMeter, an existing `.jmx` or another protocol → **JMeter**. If they ask for the browser with heavy load, suggest combining: k6 against that screen's endpoints + Artillery with few users for the experience.

Requirements: k6 → `npm run bootstrap:k6`; JMeter → Java 8+ and `npm run bootstrap:jmeter`; Artillery → `npm install` in `tools/k0lmena`.

## Stage 3 — Environment and scope

- **Target URL** and confirmation that **it's not production** (if it is, explicit authorization from the system owners; without it you don't continue).
- **What is measured**: endpoints or flow steps and their **weight** if there are several (e.g. 70% reads, 30% creates). Suggest the mix based on real usage if the person knows it.
- **Data and side effects**: authentication (credentials go in the root `.env`, never in the chat), whether POST/PUT/PATCH/DELETE can be run in that environment, with which data, and whether it has to be cleaned up afterwards.

## Stage 4 — Load

Ask for **concurrent users**, **ramp-up**, **duration** and **think time**. If the person doesn't know the users, help them calculate it:

- **From the business** (Little's law): `concurrent users = transactions per second × (response time + think time)`.
  E.g.: 18,000 logins in the peak hour = 5 per second; with 0.5 s response and 5 s think time → 5 × 5.5 ≈ **28 users**.
- **From analytics**: active users in the peak hour × fraction that uses this feature.
- **Margin**: suggest testing `load` at the expected peak and `stress` up to 2-3 times that peak.

Reference values to suggest (always as a suggestion):

```
+--------+--------------------------------+-------------------------------------+---------------------------------+
| Type   | Users                          | Ramp-up                             | Sustained duration              |
+========+================================+=====================================+=================================+
| smoke  | 1-2                            | —                                   | 30 s to 1 min                   |
+--------+--------------------------------+-------------------------------------+---------------------------------+
| load   | the expected peak              | 10-20% of the duration (min. 1 min) | 10-30 min                       |
+--------+--------------------------------+-------------------------------------+---------------------------------+
| stress | steps 1x · 2x · 3x             | 1-2 min per step                    | 5-10 min per step               |
+--------+--------------------------------+-------------------------------------+---------------------------------+
| soak   | 70-80% of the peak             | 2-5 min                             | 1-8 h                           |
+--------+--------------------------------+-------------------------------------+---------------------------------+
| spike  | base → 5-10x in less than 30 s | —                                   | peak 1-3 min and back to base   |
+--------+--------------------------------+-------------------------------------+---------------------------------+
```

- **In k6** the profiles are built by `performance/k6/lib/k0lmena.ts`: stress = 1x · 2x · 3x the users and spike = 1 min at the peak. Any other scheme (1.5x steps, a longer peak) only with JMeter or Artillery.
- **Think time**: 1-5 s between a real person's actions; 0 only if you want to measure maximum throughput (warn that it doesn't represent real users).
- **Machine limits**: k6 handles thousands of users; JMeter, a few hundred per PC (depending on memory); Artillery + browser, 10-20. If the requested load exceeds that, warn that you'd be measuring the PC and not the app, and propose alternatives (another tool, fewer users, distributed generators).

## Stage 5 — Thresholds (acceptance criteria)

First look for the requirement (SLA, story, epic). If there isn't one, suggest reference values **marked as such** and record that there's no requirement (`MI-XX` with the question for the PO):

```
+-----------------------+--------------------------+
| What is measured      | Usual reference          |
+=======================+==========================+
| Read API              | p95 < 500 ms · p99 < 1 s |
+-----------------------+--------------------------+
| Create/process API    | p95 < 1 s · p99 < 2 s    |
+-----------------------+--------------------------+
| Web flow step         | p95 < 3 s                |
+-----------------------+--------------------------+
| Errors                | < 1% (0% in smoke)       |
+-----------------------+--------------------------+
```

You can set thresholds per endpoint or per step (e.g. login stricter than a report).

## Stage 6 — Execution

- **Profiles and order**: smoke → (load) → (stress / spike) → (soak). Each run with load is confirmed right before launching it.
- **Window and notice**: when it can be run and whom to notify (infrastructure or app teams).
- **Monitoring**: ask whether there are server metrics (APM, Grafana, CPU, memory, database). They're not mandatory, but without them the recommendations are based only on what the client sees; if they exist, ask them to watch them during the run and share what they see.

## Stage 7 — Summary and confirmation

Write the plan in `output/performance/<US>/performance-plan-<US>.md` (tables normalized with `python scripts/format_tables.py`) with: goal, test types, tool and why, environment, scope and mix, load per profile, thresholds, data and side effects, window, monitoring, **accepted assumptions** (the suggestions the person approved) and open `MI-XX`. Show them the summary and ask for explicit confirmation.

With the plan confirmed, invoke the **`performance-mapper`**, passing it the path of the plan. The agent comes back after the smoke run and before each run with load: confirm with the person and continue the agent with what they say.

## When finished: final report

When the runs are over, the `performance-mapper` builds the **performance report** (`scripts/generate_performance_report.py`): an HTML dashboard with the verdict, the agreed plan, the metrics of each run (taken from the `npm run perf` summaries, not transcribed), comparative charts of latency, throughput and errors, the evolution over time, the thresholds, the p95 per endpoint, the errors, the findings, the observed capacity and the recommendations. Present the person with the verdict, the top 3 findings, the high-priority recommendations and the path to the report.
