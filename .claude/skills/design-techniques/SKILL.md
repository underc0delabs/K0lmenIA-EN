---
name: design-techniques
description: Applies formal black-box test design techniques —equivalence classes, boundary values, decision tables, state transitions and pairwise— to derive complete, non-redundant cases. Use it when generating or reviewing test cases (manual, BDD or API) whenever the story, business rule or endpoint has ranges, conditions, states or parameter combinations.
---

# Test case design techniques

These techniques help you **cover more with fewer cases**: they derive the relevant cases systematically, without throwing random values or repeating the same thing. Apply them when designing cases from a story, a business rule or an endpoint.

## How to use them (flow)

1. **Identify the inputs and their rules.** For each field or condition: type, range, format, whether it is required, valid and invalid values, possible states.
2. **Choose the technique by input type** (guide below). Several are almost always combined.
3. **Derive the cases** with the technique.
4. **Always add negative and edge cases**, not just the happy path.
5. **Remove redundancy**: if two cases test exactly the same thing, keep one.
6. **What is not defined is not invented**: record it as **Missing information** (`MI-XX`, skill `context-research`) with its question for the PO; if you use an assumption to write the case, state it tied to that `MI-XX`.

## Which technique to use

- **Numeric or length range** (e.g. amount 1–9999, password 8–16) → **boundary values** + **equivalence classes**.
- **Inputs with categories or valid/invalid** (e.g. document type, marital status) → **equivalence classes**.
- **Several conditions that combine and change the result** (e.g. discount by customer type + payment method) → **decision table**.
- **Flow with states** (e.g. order: created → paid → shipped; or account lockout after N attempts) → **state transition**.
- **Many independent parameters** (e.g. browser × OS × language) → **pairwise** (reduced combinatorics).

## The techniques in one line

- **Equivalence classes:** group the inputs the system treats the same way and test **one representative per group** (valid and invalid).
- **Boundary values:** errors hide at the edges; test **the boundary and its neighbors** (min−1, min, min+1 … max−1, max, max+1).
- **Decision table:** list conditions and actions, and build one column per **relevant combination** of conditions.
- **State transition:** map states and events, and test the **valid and the invalid transitions** (events not allowed in each state).
- **Pairwise:** instead of all combinations, cover **all pairs** of values; it greatly reduces the number of cases while keeping good coverage.

The detail of each technique, with worked examples and common mistakes, is in [`references/techniques.md`](references/techniques.md).

## Output

The cases you derive go in the format of the agent that generates them (`.xlsx` spreadsheet + `.md`, `.feature`, API cases…), each with its **priority** (most critical first). In the coverage report **always** state the technique and the derived values per criterion (e.g.: "Boundary values, 8–16: 7, 8, 16, 17 → TC-004 to TC-007"), so the reason for each case can be verified.
