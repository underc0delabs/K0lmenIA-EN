# Agent evals

The repo tests (`tests/`) verify the **scripts**. The evals measure something else: the **quality of what the agents generate**. They tell you whether a change to an agent, a skill or `CLAUDE.md` makes it better or worse, before you push it.

Each case gives an agent an input with **deliberate traps** (an ambiguity, a contradiction between the description and a criterion, a message that is not defined, a bounded field, a secret in a configuration file) and uses **deterministic checks** to confirm it did the right thing: that it flags the Missing information instead of inventing, applies boundary values, follows the template, and does not copy secrets.

## Cases

```
+--------------------------------+----------------------------+------------------------------------------+
| Case                           | Agent                      | What it measures                         |
+================================+============================+==========================================+
| `story-analyst-signup-story`   | `story-analyst`            | Detects the 16/18 years contradiction,   |
|                                |                            | the "secure" password with no rules, the |
|                                |                            | undefined message and the open question; |
|                                |                            | records MI-XX                            |
+--------------------------------+----------------------------+------------------------------------------+
| `manual-cases-signup-story`    | `manual-case-generator`    | Valid spreadsheet (columns, IDs,         |
|                                |                            | priorities and order),                   |
|                                |                            | positive/negative/boundary, boundary     |
|                                |                            | values, `@missing-info`, does not invent |
|                                |                            | messages                                 |
+--------------------------------+----------------------------+------------------------------------------+
| `bdd-signup-story`             | `bdd-case-generator`       | Valid Gherkin, English keywords and      |
|                                |                            | content, `@US`/`@TC`, Scenario Outline,  |
|                                |                            | `@missing-info @MI-XX`                   |
+--------------------------------+----------------------------+------------------------------------------+
| `api-cases-auth`               | `api-case-generator`       | Every endpoint and response code of the  |
|                                |                            | contract, lockout, not revealing whether |
|                                |                            | the email exists, bodies in JSON         |
+--------------------------------+----------------------------+------------------------------------------+
| `bug-report-coupon`            | `bug-report-generator`     | Every template field in order, data from |
|                                |                            | the observation, Missing information,    |
|                                |                            | does not invent a password or version    |
+--------------------------------+----------------------------+------------------------------------------+
| `project-consultant-questions` | `project-consultant`       | Answers with the source and says "it is  |
|                                |                            | not documented" when appropriate         |
|                                |                            | (skipped if the agent does not exist)    |
+--------------------------------+----------------------------+------------------------------------------+
| `project-documenter-local-repo`| `project-documenter`       | Rules with `file:line`, i18n messages,   |
|                                |                            | header for the index and **does not copy |
|                                |                            | secrets**                                |
+--------------------------------+----------------------------+------------------------------------------+
```

## How to run them

```bash
python scripts/evaluate_agents.py --list                         # the cases and their checks
python scripts/evaluate_agents.py --run                          # all of them (spends tokens)
python scripts/evaluate_agents.py --run --agent manual-case-generator
python scripts/evaluate_agents.py --run --case story-analyst-signup-story --model claude-sonnet-5-5
```

`--run` does three things per case:

1. **Prepares an isolated workspace**, outside the repo (in the system temp folder, or in `--workdir`): a copy of `CLAUDE.md`, `AGENTS.md`, `.claude/`, `templates/` and `scripts/`, with empty `input/` and `output/`, the case inputs and its own `.env`. Your `input/` and your `output/` are never touched.
2. **Runs the agent** with Claude Code in headless mode, inside the workspace:
   `claude -p "<prompt>" --output-format json --permission-mode acceptEdits --allowedTools "Read,Write,Edit,Glob,Grep,Agent,…,Bash(python:*)" --max-budget-usd <cap> --strict-mcp-config --setting-sources project`.
   It can only read and write files and run the Python scripts; it does not use MCP connectors or your personal configuration, and each case has a spending cap (the case `budget_usd`, or `--budget-usd`).
3. **Verifies** what it left and builds the report.

**Cost**: each case is a full conversation with an agent (the case generators are the most expensive). Running all of them costs a few dollars with a large model; the caps of each case are the maximum, not the usual. To iterate, run a single case or a single agent.

### Without spending the script's tokens

- **Prepare and run by hand**: `--prepare` builds the workspaces and prints the command for each one; you run them (or open them in Claude Code and send the case prompt) and then `--verify --workdir <folder>`.
- **Verify something you already generated**: if you asked the agent for the case in your repo, `python scripts/evaluate_agents.py --verify-only . --case manual-cases-signup-story` checks what is in `output/`. What the agent answers in the chat (the `project-consultant`) goes in `_eval/response.txt` in that folder.

### Judge (optional)

With `--judge`, in addition to the checks, Claude scores the case **rubric** (clarity of the steps, redundancy, explained assumptions…). It is **informational**: it does not change the score, which comes only from the deterministic checks. It spends extra tokens.

## Results

They are saved in `evals/results/<date-time>/` (not versioned):

- `results.json`: each case with its score (0-100, weighted by the `weight` of each check), its status (*Passed* if it reaches the `threshold`, 80 by default), each check with the detail of why it failed, and the cost, turns and duration of the run.
- `evals-report.html`: the report (dark mode, like the other k0lmenIA reports), with the score per agent and per case and the **comparison with the previous run**: which checks stopped passing (**regressions**) and which started to pass.

Recommended flow when changing an agent: run its cases before and after the change and look at the regressions.

## How to add a case

A folder `evals/cases/<id>/` with a `case.json`:

```json
{
  "agent": "manual-case-generator",
  "description": "What traps it has and what is expected",
  "prompt": "Use the … agent to …",
  "requires": [".claude/agents/other-agent.md"],
  "inputs": [{"from": "inputs/US-901-signup.md", "to": "input/stories/US-901-signup.md"},
             {"from": "repo:input/api/auth-endpoints.md", "to": "input/api/auth-endpoints.md"}],
  "env": {"REPO_LOCAL_PATH": "{workspace}/demo-repo"},
  "budget_usd": 2,
  "threshold": 80,
  "checks": [{"id": "file", "type": "exists", "description": "…", "files": ["output/…/*.md"], "weight": 2}],
  "rubric": ["Criterion for the judge (optional)"]
}
```

- `inputs`: `from` is relative to `evals/` (or to the case folder); with `repo:` it is taken from the repo. It can be a file or a folder.
- `requires`: if anything in the list is missing, the case is skipped (*N/A*) instead of failing.
- `env`: the workspace `.env`; `{workspace}` is replaced with its path.

Check types (the `files` are globs relative to the workspace; the patterns are case-insensitive regexes):

```
+-----------------------+------------------------------------------+
| Type                  | What it checks                           |
+=======================+==========================================+
| `exists`              | That there are at least `min` files      |
+-----------------------+------------------------------------------+
| `contains`            | That all the `patterns` appear (or any   |
|                       | of them, with `"mode": "any"`)           |
+-----------------------+------------------------------------------+
| `not_contains`        | That none of them appears (something     |
|                       | invented, a secret)                      |
+-----------------------+------------------------------------------+
| `count`               | That `pattern` appears at least `min`    |
|                       | times (`distinct` to count distinct      |
|                       | values, for example MI-XX IDs)           |
+-----------------------+------------------------------------------+
| `order`               | That the `patterns` appear in that order |
|                       | (sections, fields of a template)         |
+-----------------------+------------------------------------------+
| `normalized_tables`   | That no tables are left in raw Markdown  |
|                       | (`format_tables.py` missing)             |
+-----------------------+------------------------------------------+
| `xlsx_columns`        | The columns of the test cases            |
|                       | spreadsheet                              |
+-----------------------+------------------------------------------+
| `xlsx_cases`          | Minimum number of cases, consecutive     |
|                       | `TC-XXX` IDs, priorities and statuses    |
|                       | from the scale, sorted by priority,      |
|                       | steps and result                         |
+-----------------------+------------------------------------------+
| `xlsx_types`          | Minimum number of cases per type         |
|                       | (positive, negative, boundary…), each    |
|                       | with its regex over title, description,  |
|                       | data and tags                            |
+-----------------------+------------------------------------------+
| `xlsx_missing_info`   | Cases marked `@missing-info` and the     |
|                       | *Missing information* sheet              |
+-----------------------+------------------------------------------+
| `xlsx_filter`         | The cases that cover a topic (`filter`)  |
|                       | must have `must` (for example            |
|                       | `@missing-info`) and not                 |
|                       | `must_not_result`                        |
+-----------------------+------------------------------------------+
| `gherkin`             | Valid `.feature`: Feature and scenario   |
|                       | tags, Given/When/Then, Examples,         |
|                       | `@missing-info @MI-XX` with its comment  |
+-----------------------+------------------------------------------+
```

The shared inputs are in `evals/inputs/`. Everything is fictional: the `config/production.env` in `demo-repo` has fake values on purpose, as a trap for the `project-documenter`.
