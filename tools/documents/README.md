# Documents

**Read-only** survey of generated documents (PDF, Excel/CSV) to validate them in QA. Used by the `document-tester` agent.

- **`documents.py`** (`npm run documents`) — extracts text and metadata from a **PDF** (pypdf), sheets and cells from an **Excel** file (openpyxl) or rows from a **CSV**, and detects **unreplaced placeholders** (template variables, Lorem ipsum, TODO) — the most common bug in a generated document.

```bash
npm run documents -- --file output/.../invoice.pdf
npm run documents -- --file report.xlsx
```

It does not modify the document. The `document-tester` verifies that the data/calculations and the layout are correct using this input and the expected data. Requires `pypdf` (PDF) and `openpyxl` (Excel), lazily imported.
