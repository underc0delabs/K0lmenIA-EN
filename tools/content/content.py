#!/usr/bin/env python3
"""
Read-only, dependency-free content/typo review of a text or file: uses heuristics to detect the most
common objective errors (leftover placeholders, Lorem ipsum, duplicated words, visible i18n keys,
TODO markers, spaces before punctuation, capitalization/punctuation). For real spelling/grammar it
uses LanguageTool if it is installed (optional).

Usage (from the repo root):
    python tools/content/content.py --file page.txt [--language en-US] [--output ...]
    python tools/content/content.py --text "the the text to review"

The content-reviewer agent usually extracts the visible text of the website with Playwright (snapshot)
and passes it through here; this does not judge style or tone, only objective errors.
"""
import argparse
import json
import re
import sys
from pathlib import Path

HEURISTICS = [
    ("Unreplaced placeholder", re.compile(r"\{\{\s*[\w.]+\s*\}\}|\$\{[\w.]+\}|%\(?[\w]+\)?[sd]")),
    ("Lorem ipsum", re.compile(r"(?i)lorem ipsum")),
    ("Pending marker", re.compile(r"\b(TODO|FIXME|XXX|TBD|PENDING|PLACEHOLDER)\b")),
    ("Visible i18n key", re.compile(r"\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}\b")),
    ("Duplicated word", re.compile(r"(?i)\b(\w{2,})\s+\1\b")),
    ("Filler text", re.compile(r"(?i)\b(asdf+|qwerty|aaaa+|xxxx+|test test|dummy)\b")),
    ("Space before punctuation", re.compile(r"\s+[,.;:!?]")),
    ("Multiple spaces", re.compile(r"\S {2,}\S")),
]


def check(text):
    """[(type, line, fragment)] of the objective problems in the text. Pure and testable."""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for kind, rx in HEURISTICS:
            m = rx.search(line)
            if m:
                frag = re.sub(r"\s+", " ", m.group(0)).strip()[:50]
                out.append((kind, i, frag))
    return out


def languagetool(text, language):
    """Spelling/grammar with LanguageTool if it is installed; otherwise returns None (optional)."""
    try:
        import language_tool_python  # noqa
    except ImportError:
        return None
    try:
        tool = language_tool_python.LanguageToolPublicAPI(language)
        matches = tool.check(text)
        return [{"message": m.message, "context": m.context, "rule": m.ruleId,
                 "suggestions": m.replacements[:3]} for m in matches[:200]]
    except Exception:
        return None


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Content/typo review (heuristics + optional LanguageTool).")
    ap.add_argument("--file", default="")
    ap.add_argument("--text", default="")
    ap.add_argument("--language", default="en-US", help="language for LanguageTool (en-US, es, pt…)")
    ap.add_argument("--lt", action="store_true", help="also run LanguageTool if it is installed")
    ap.add_argument("--output", default="")
    args = ap.parse_args(argv)
    if args.file:
        if not Path(args.file).exists():
            print(f"[content] Not found: {args.file}", file=sys.stderr)
            return 2
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    else:
        text = args.text
    if not text.strip():
        print("[content] Pass --file or --text.", file=sys.stderr)
        return 2
    heur = check(text)
    data = {"heuristics": [{"type": t, "line": ln, "fragment": f} for t, ln, f in heur],
            "summary": {"heuristics": len(heur)}}
    if args.lt:
        lt = languagetool(text, args.language)
        data["languagetool"] = lt if lt is not None else "not installed (pip install language-tool-python)"
        if isinstance(lt, list):
            data["summary"]["languagetool"] = len(lt)
    text_out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text_out, encoding="utf-8")
        print(f"[content] Data in {p}", file=sys.stderr)
    print(text_out)
    print(f"[content] {len(heur)} heuristic problem(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
