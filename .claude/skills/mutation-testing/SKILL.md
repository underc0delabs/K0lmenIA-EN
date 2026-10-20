---
name: mutation-testing
description: How to do mutation testing — measuring the real quality of a test suite by introducing changes (mutants) into the code and seeing whether the tests detect them ("kill" them). Concepts — mutants and mutators (change an operator, a boundary, a return, a boolean, delete a line), mutant statuses (killed, survived, no coverage, timeout, compile error, ignored), mutation score (killed+timeout over the valid total) and why it's a better signal than line coverage (coverage says what gets executed; mutation, what really gets verified), surviving mutants as missing tests or weak assertions, equivalent mutants (they don't change observable behavior, they are false positives to ignore), how to limit the cost (incremental mutation on the diff, per critical module, with limits), tools per language (Stryker for JS/TS/C#/Scala, mutmut or cosmic-ray for Python, PITest for JVM, Infection for PHP, go-mutesting for Go), the flow (the suite has to be green and fast first), thresholds per file/project, interpreting the survivors and questions for the team. Used by the mutation-analyst; complements the coverage-analyst (coverage) and the test case generators.
---

# Mutation testing (test suite quality)

Coverage tells you **which code gets executed** by the tests; it doesn't tell you whether it's actually **verified**. Mutation testing measures that: it introduces small changes (**mutants**) into the code and, if the tests stay green, that mutant **survived** → there's a missing test or a weak assertion. It's "testing that your tests are worth something". It complements `coverage-analyst`.

## 1. Mutants and mutators

- A **mutator** changes something minimal: an operator (`+`→`-`, `>`→`>=`), a boolean (`true`→`false`), a boundary, a `return`, a condition, or **deletes a line**.
- Each change creates a **mutant**. The suite is run against each one.

## 2. Statuses and mutation score

- **Killed**: some test failed → the mutant was detected (good).
- **Survived**: all tests passed anyway → **not detected** (there's a gap).
- **No coverage**: the mutant is in code that no test executes.
- **Timeout**: the mutant hung (counts as detected); **Compile error** / **Ignored**: excluded from the calculation.
- **Mutation score** = (killed + timeout) / (killed + timeout + survived + no coverage) × 100. It's a **better signal than line coverage**.

## 3. Survivors and equivalents

- A **surviving mutant** points to a missing test or a loose assertion: that's the actionable part. For each one, which test case or assertion would kill it?
- An **equivalent mutant** doesn't change observable behavior (e.g. a change that still gives the same result): it's a **false positive** that gets marked as ignored, not "fixed". Telling them apart is the key human judgment.

## 4. Cost: how to limit it

- Mutation is **expensive** (it runs the suite N times). To make it viable:
  - **Incremental**: mutate only the **diff** (what changed in the PR/branch), not the whole repo.
  - **Per critical module**: focus on business/money logic, not trivial code.
  - Concurrency and timeout limits; exclude generated/vendored code.
- **Requirement**: the suite has to be **green and fast** before mutating (a flaky test ruins the measurement).

## 5. Tools per language

- **JS/TS/C#/Scala**: Stryker (emits the **standard JSON report** that `npm run mutation` reads).
- **Python**: mutmut or cosmic-ray. **JVM**: PITest. **PHP**: Infection. **Go**: go-mutesting.

## 6. Flow

1. Confirm the suite is **green and fast**.
2. Run the mutation tool (on the diff or a module), generate the report.
3. Read the report with `npm run mutation` (`tools/mutation/mutation.py`): global and per-file mutation score, survivors and files under the threshold.
4. **Triage the survivors**: separate equivalents (ignore, with a reason) from real ones (missing test/assertion); prioritize by file criticality.
5. Recommend the concrete tests/assertions that would kill the real survivors.

## 7. Thresholds

- Set a **minimum score** per project/module (e.g. 70-80% in critical logic); don't demand 100% (equivalents make it impossible). Useful as a PR gate on the diff.

## 8. Typical bugs/smells it reveals

- Tests that execute the code but **assert** nothing (high coverage, low score).
- Weak assertions (they check that it "doesn't blow up" but not the result).
- Branches/boundary conditions without a test (the `>`→`>=` mutant survives).
- Error handling without a test (deleting the `throw` survives).

## 9. Typical questions for the team

When it isn't written down, they are `MI-XX`:

- Which language/test stack, and which mutation tool applies?
- Is the suite green and fast? Are there flaky tests to exclude?
- Do we mutate everything, the diff or a critical module? What threshold is expected?
- Which parts of the code are critical (money, security, calculations)?
