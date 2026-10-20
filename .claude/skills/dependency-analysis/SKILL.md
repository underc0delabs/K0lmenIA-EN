---
name: dependency-analysis
description: How to analyze the security of a project's dependencies (SCA, Software Composition Analysis) — ecosystems and their manifests/lockfiles (npm/yarn/pnpm, pip/poetry, Maven/Gradle, Go, Ruby, PHP), known vulnerabilities (CVE, GHSA) and how to read CVSS and severity, direct vs. transitive dependencies, upgrade paths (fix available, major with breaking changes), reachability (whether the vulnerable code is actually used) to prioritize and discard noise, licenses and copyleft risk (GPL/AGPL), SBOM (CycloneDX/SPDX), supply chain attacks (dependency confusion, typosquatting, compromised packages), the difference between outdated and vulnerable, false positives and accepted risk (documented, with a review date), tools (npm audit, pip-audit, osv-scanner, Dependabot/Renovate) and how to prioritize the fixes, and questions for the owner. Used by the dependency-analyst; complements security-analyst and web-pentester (which do the dynamic analysis).
---

# Dependency analysis (SCA)

Most of a project's code is **third-party**. SCA looks for **known vulnerabilities (CVE)** and **license** issues in those dependencies. It is **static and read-only**: it doesn't run the app or attack it (that is DAST: `security-analyst`, `web-pentester`). It runs on the application repository (`REPO_LOCAL_PATH`).

## 1. Ecosystems and lockfiles

- Each ecosystem has its manifest and its **lockfile** (the source of truth for which version is installed): npm/yarn/pnpm (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`), Python (`requirements.txt`, `poetry.lock`), Maven/Gradle, Go (`go.sum`), Ruby (`Gemfile.lock`), PHP (`composer.lock`).
- The analysis is done against the **lockfile**, not just the manifest: that's where the real versions are, including the transitive ones.

## 2. Direct vs. transitive

- A **direct** dependency is one you chose; a **transitive** one was pulled in by another. Most CVEs are in transitive dependencies.
- If the vulnerable one is transitive, the fix may be upgrading the **direct** one that brings it in, or an `override`/`resolution` to force the patched version.

## 3. Severity and prioritization

- Severity comes from **CVSS** (Critical/High/Medium/Low). But not everything "critical" is exploitable in your context: prioritize by **reachability** (is the vulnerable code used?), whether it is reachable from the network, and whether there is a public exploit.
- **Outdated ≠ vulnerable**: an old package without a CVE is not a bug; upgrading it is a separate risk (regression). Report vulnerable packages, not just old ones.
- **Fix available**: whatever is solved by moving to a patched version is a priority (low cost).

## 4. Supply chain

- **Dependency confusion**: an internal package with the same name as a public one can be impersonated.
- **Typosquatting**: names similar to popular packages.
- **Compromised packages** (a hacked maintainer, a malicious postinstall): review maintainer changes and install scripts in new dependencies.

## 5. Licenses

- **Copyleft** licenses (GPL, AGPL, LGPL) may force you to release your code depending on how you use them; permissive ones (MIT, Apache-2.0, BSD) don't. Flag the ones that need legal review; don't decide on them yourself.

## 6. SBOM

- An **SBOM** (CycloneDX or SPDX) is the inventory of everything that makes up the software; useful for auditing and for responding quickly to a new CVE (does it affect us?).

## 7. Tools

- `npm audit --json` (Node), `pip-audit` (Python), **`osv-scanner`** (multi-ecosystem, OSV database). The `npm run dependencies` tool (`tools/security/dependencies.py`) runs whichever are available and aggregates by severity.
- Automate follow-up with **Dependabot** or **Renovate** (upgrade PRs).

## 8. False positives and accepted risk

- A CVE may not apply (you don't use the vulnerable function, it's dev/test only). Document the **accepted risk** with the reason and a **review date** (as the repo's own `SECURITY.md` does); don't just delete it and move on.

## 9. Typical questions for the owner

When it is not written down, they are `MI-XX`:

- Which repository and branch should be analyzed? Is there a lockfile?
- Which minimum severity blocks a release? Is there an SLA for patching critical ones?
- Are copyleft licenses allowed? Is there a list of approved licenses?
- Are dev/test dependencies in scope, or only production ones?
- Is there already an accepted-risk policy or an SBOM?
