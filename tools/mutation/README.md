# Mutation testing

**Read-only** reading of a mutation testing report (standard **Stryker** / mutation-testing-report-schema format). Used by the `mutation-analyst` agent.

- **`mutation.py`** (`npm run mutation`) — parses the Stryker JSON (StrykerJS, Stryker.NET and those that export to that schema), computes the global and per-file **mutation score**, lists the **surviving mutants** (the ones your tests did not detect) and the code **without coverage**, and flags the files below a threshold.

```bash
npm run mutation -- --report reports/mutation/mutation.json --threshold 70
```

It does not run the mutation: the `mutation-analyst` does that with the project's tool (**Stryker** for JS/TS/C#, **mutmut/cosmic-ray** for Python, **PITest** for JVM, **Infection** for PHP); this tool only reads the report. No dependencies (stdlib).
