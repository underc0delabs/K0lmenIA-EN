#!/usr/bin/env python3
"""Normalizes ALL the Markdown tables in a .md file into aligned ASCII tables.

Usage:
    python scripts/format_tables.py <file.md> [max_column_width]

What it does:
- Finds every Markdown table (rows with `|` and their separator row `|---|---|`) and
  replaces it with an ASCII table (grid style) inside a code block, so it looks
  aligned in any editor, no matter how much text it has.
- Long cells are wrapped to `max_column_width` characters (default 40).
  It respects line breaks written as `<br>` or real ones.
- It does NOT touch what is already inside code blocks (```), so it is safe to
  run it several times on the same file (it is idempotent).

Meant for any agent to run once after writing a `.md`, so that all of its
tables end up with the same format.
"""
import sys
import re
import textwrap
import subprocess

DELIM_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _need(pkg, install=None):
    """Makes sure the library is available. If it is missing, tries to install it; if it
    can't, it says so with a clear message and stops."""
    install = install or pkg
    try:
        __import__(pkg)
        return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", install, "--quiet"], check=False)
    try:
        __import__(pkg)
    except ImportError:
        sys.exit(
            f"\n[!] The '{install}' library is missing and could not be installed automatically.\n"
            f"    Install the dependencies with:  pip install -r requirements.txt\n"
            f"    (or directly:  pip install {install})\n")


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _wrap_cell(text, width):
    text = re.sub(r"<br\s*/?>", "\n", str(text))
    out = []
    for seg in text.split("\n"):
        seg = seg.strip()
        if seg:
            out.extend(textwrap.wrap(seg, width=width))
        else:
            out.append("")
    return "\n".join(out)


def _is_row(line):
    return "|" in line and line.strip() != ""


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/format_tables.py <file.md> [max_column_width]", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 40

    _need("tabulate")
    from tabulate import tabulate

    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")

    out = []
    i = 0
    in_fence = False
    n = len(lines)
    converted = 0

    while i < n:
        line = lines[i]

        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue

        # Does a table start here? A row with '|' followed by a separator row.
        if (not in_fence and _is_row(line) and i + 1 < n and DELIM_RE.match(lines[i + 1])
                and "-" in lines[i + 1]):
            headers = _cells(line)
            ncols = len(headers)
            j = i + 2
            data = []
            while j < n and _is_row(lines[j]) and not lines[j].lstrip().startswith("```"):
                row = _cells(lines[j])
                row = (row + [""] * ncols)[:ncols]   # pad to the number of columns
                data.append(row)
                j += 1

            H = [_wrap_cell(h, width) for h in headers]
            R = [[_wrap_cell(c, width) for c in row] for row in data]
            table = tabulate(R, headers=H, tablefmt="grid")
            out.append("```")
            out.append(table)
            out.append("```")
            converted += 1
            i = j
            continue

        out.append(line)
        i += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"OK: {converted} table(s) formatted in {path}")


if __name__ == "__main__":
    main()
