---
name: code-quality
description: How to do static code quality analysis — maintainability metrics and their usual thresholds (cyclomatic complexity, function and file length, duplication, number of parameters, TODO/FIXME debt), code smells per language (JavaScript/TypeScript, Python, Java/Kotlin, C#, Go, PHP), best practices (error handling, empty catch, bare except, mutable defaults, debug output, any/ts-ignore, wildcard imports), static performance patterns (N+1 queries and remote calls inside loops, await in a loop, synchronous I/O in Node, SELECT *, blocking sleeps, unbounded queries, string building in loops), how to get the code (local path or a shallow read-only clone from GitHub/GitLab with the token from the .env), the project's own linters (eslint, ruff) without fixing, how to triage false positives and prioritize by impact and hotspots, what static analysis doesn't see (real performance, runtime) and questions for the team. Used by the code-quality-analyst; complements secure-code (SAST), dependency-analysis (SCA) and the performance agents.
---

# Static code quality analysis

Looks at **how the code is written**: whether it's maintainable, follows the language's best practices and has patterns that will be slow under load. It's static and read-only. It runs on the application repository: a local copy (`REPO_LOCAL_PATH`) or a shallow clone from GitHub/GitLab (`npm run code-quality -- --repo …`).

## 1. Maintainability metrics (usual thresholds)

- **Cyclomatic complexity** per function: ≤ 10 is fine, 11–15 deserves attention, > 15 is hard to test (the tool flags > 15; > 30 is high). A complex function needs at least as many tests as its complexity.
- **Function length**: > 80 lines usually does several things. **Parameters**: > 5 suggests a missing object.
- **File size**: > 500 lines of code usually mixes responsibilities.
- **Duplication**: < 5% is healthy, 5–10% worth watching, > 10% is debt (a bug fixed in one copy stays in the others).
- **TODO/FIXME/HACK markers**: debt written down; count them and look at the oldest/critical ones.

Metrics alone don't make a finding: a 200-line generated parser is not the same as a 200-line controller.

## 2. Best practices and reliability (smells per language)

- **All**: empty catch / swallowed errors, generic catch of everything, magic numbers, dead code, commented-out code, very long lines.
- **JavaScript/TypeScript**: `console.log`/`debugger` left in, `forEach(async …)` (doesn't wait), unhandled promises, `any` and `@ts-ignore`, `==` instead of `===`, `eslint-disable` for the whole file.
- **Python**: bare `except:`, `except …: pass`, mutable default arguments (`def f(x=[])`), `import *`, `print` instead of `logging`.
- **Java/Kotlin/C#**: `printStackTrace` / `System.out`, catching `Exception` and ignoring it, `Thread.sleep` as a wait, resources not closed (try-with-resources / `using`).

## 3. Performance patterns visible in the code

- **N+1**: a query or remote call **inside a loop** (one per item) instead of a batch/join/`IN`. The most expensive and the most common.
- **`await` in a loop** when the calls are independent → `Promise.all` / batch.
- **Synchronous I/O in Node** (`readFileSync`, `execSync`) in a request path blocks every user; in build scripts it's fine.
- **`SELECT *`**, queries without `LIMIT`/pagination, missing indexes for the filters used (confirm with the schema).
- **Blocking sleeps** (`Thread.sleep`) instead of events or retries with backoff; string building in loops; loading whole files or tables into memory.

Static analysis gives **candidates**; the real impact is measured under load with `performance-mapper` (k6/JMeter) or the page with `web-performance-auditor`.

## 4. Linters

Use the ones **the project already has configured** (its rules are the team's standard): `eslint` with its own config (needs `npm ci` in the project) and `ruff` for Python. **Never with `--fix`**. Report **by rule** (the 10 most frequent), not thousands of loose lines.

## 5. Triage and prioritization

- Confirm each candidate **by reading the code**; discard with a reason (test code, build scripts, generated or vendored code, intentional and commented).
- Severity by impact: a performance or reliability problem in a hot path (High) > maintainability of core code (Medium) > style (Low).
- **Hotspots**: files with high complexity + many findings + many changes — refactoring there gives the most return. Recommend with file, line and an example of the fix.

## 6. What it does NOT cover

Security bugs and secrets → `secure-code` (secure-code-analyst). Vulnerable packages → `dependency-analysis` (dependency-analyst). Real behavior and performance → runtime testing and the performance agents. Test quality → mutation-testing.

## 7. Typical questions for the team

When it isn't written down, they are `MI-XX`:

- Which repository, branch and folders? Are there parts out of scope (generated, vendored, legacy)?
- Is there a style guide or agreed limits (complexity, duplication, file size)? Do they use SonarQube/CodeClimate in CI with a quality gate?
- Which paths are hot (most traffic) so performance findings can be prioritized?
- Is the linter config in the repo the one CI uses?
