---
name: secure-code
description: How to do static security analysis of code (SAST) and secret scanning — the bug classes you see in the source code (SQL/NoSQL/command injection, XSS, insecure deserialization, path traversal, SSRF, XXE, weak or hardcoded crypto, authentication and access control, open redirects, insecure use of randomness, race conditions), the mapping to OWASP Top 10 and CWE, how to run and read semgrep (rules, auto config, severity), triaging false positives and prioritizing by exploitability and reachability, detecting secrets and credentials in the code (cloud keys, tokens, private keys, passwords in config) and what to do with them (rotate, remove from git history, use a vault), the difference between SAST (code) and DAST (running app) and what each one doesn't see, tools (semgrep, gitleaks/trufflehog, CodeQL) and questions for the owner. Used by the secure-code-analyst; complements security-analyst and web-pentester (dynamic analysis) and dependency-analysis (SCA).
---

# Static security analysis of code (SAST) and secrets

SAST looks for **security bugs in the source code** without running it, and secret scanning finds **credentials that shouldn't be in the repo**. It is static and read-only; what happens with the running app is seen by the `security-analyst` and the `web-pentester` (DAST). It runs over the application repository (`REPO_LOCAL_PATH`).

## 1. What SAST finds (bug classes)

Mapped to the **OWASP Top 10** and to **CWE**:

- **Injection** (SQL, NoSQL, OS commands, LDAP): user data concatenated into a query or command. The most serious and common.
- **XSS**: unescaped output in HTML/JS.
- **Insecure deserialization**, **XXE** (XML with external entities), **path traversal** (`../`), **SSRF** (user-controlled URL that the server fetches).
- **Cryptography**: weak algorithms (MD5/SHA1 for passwords, DES), hardcoded keys/IVs, non-cryptographic randomness (`Math.random` for tokens).
- **Authentication and access control** in the code: missing checks, non-constant-time password comparison.
- **Open redirect**, **log injection**, **race conditions** (TOCTOU).

## 2. Secrets in the code

- Cloud keys (AWS `AKIA…`, Google `AIza…`), tokens (GitHub `ghp_…`, Slack `xox…`), private keys (`BEGIN PRIVATE KEY`), payment keys (`sk_live_…`), JWT, and assignments like `password=…`, `api_key=…` in config.
- **A secret in the repo is considered compromised**: you have to **rotate it**, not just delete it — and remove it from the **git history** (it is in old commits). Store them in a **vault**/environment variables, not in the code.
- The `npm run sast` tool (`tools/security/sast.py`) comes with a built-in secret scanner (it always runs) and **redacts** the value in the output; never put the full secret in the report.

## 3. Triage and prioritization

- SAST produces **false positives**: each finding is confirmed by reading the code (does the data really arrive unsanitized? is it dead, test or example code?). Discard FPs **with a reason**.
- Prioritize by **exploitability** (input controllable by the user, reachable from the network) and severity, not just by what the rule says.

## 4. Tools

- **semgrep** (`semgrep --config auto --json`): rules by language and framework; severity ERROR/WARNING/INFO. It is what `npm run sast` uses if it is installed.
- **gitleaks** / **trufflehog**: secrets (including the git history).
- **CodeQL**: deep SAST (GitHub), for more exhaustive analysis.

## 5. SAST vs. DAST (what each one does NOT see)

- **SAST** sees the code but not the runtime: it doesn't know about server configuration, headers, TLS, or real call chains.
- **DAST** (ZAP, pentest) sees the running app but not the code. They complement each other: a SAST finding is **confirmed** with DAST or with a manual test (`web-pentester`).

## 6. Typical questions for the owner

When it isn't written down, they are `MI-XX`:

- What is the repository and the branch? What languages/frameworks?
- What severity blocks a release? Is there an SLA for exposed secrets?
- Are there parts of the code out of scope (generated, vendored, legacy)?
- Do they already use semgrep/CodeQL in CI with some custom config?
- Where should the secrets live (vault, environment variables, secret manager)?
