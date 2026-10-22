# tools/quality — static code quality

- **`code_quality.py`** (`npm run code-quality`) — read-only **code quality** survey of a project: lines per language, cyclomatic complexity and function length (with `lizard` if installed), duplicated code (built-in), large files, TODO/FIXME/HACK markers, the project's own linters without fixing (`ruff`, and `eslint` if the project has its config and `node_modules`), and best-practice and performance patterns per language (empty catch, bare except, mutable defaults, debug output, sync I/O, `await` or queries inside a loop, `SELECT *`, `Thread.sleep`). Used by the `code-quality-analyst`; the report is built with `scripts/generate_code_quality_report.py`.

```bash
npm run code-quality -- --path C:/projects/my-app --output output/code-quality/my-app/quality.json
npm run code-quality -- --repo my-company/my-app --provider github --branch main --output output/code-quality/my-app/quality.json
```

With `--repo` it does a shallow clone into the system temp folder (`k0lmenia-repos/<name>`, or `--clone-dir`). For private repos it uses `GITHUB_TOKEN` or `GITLAB_TOKEN` (and `GITLAB_URL` for self-hosted) from the `.env`; the token only travels as an HTTP header of that git call and is never written to `.git/config` or printed.

Optional: `pip install lizard ruff`. Without them the built-in heuristics and the duplication check still run, and the JSON says what was skipped.
