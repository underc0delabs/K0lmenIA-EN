# Content / typos

**Read-only** review of the content and typos of a text or file. Used by the `content-reviewer` agent.

- **`content.py`** (`npm run content`) — uses heuristics (no dictionary, no dependencies) to detect the most common objective errors: leftover placeholders, Lorem ipsum, duplicated words, visible i18n keys, TODO markers, spaces before punctuation and multiple spaces. With `--lt` it runs **LanguageTool** (real spelling/grammar) if it is installed.

```bash
npm run content -- --file page.txt --language en-US
npm run content -- --text "the the text to review"
```

It does not judge style or tone, only objective errors. No dependencies for the heuristics; LanguageTool is optional (`pip install language-tool-python`).
