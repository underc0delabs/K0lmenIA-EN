#!/usr/bin/env python3
"""
Read-only survey of the control tree of a Windows desktop app (pywinauto).

Usage (from the repo root, on Windows, with the app open):
    python tools/desktop/controls.py --title "Invoicer.*"   [--output output/desktop/tree.json]
    python tools/desktop/controls.py --process 1234 --backend uia --depth 6

What it does (read-only):
- Connects to an already open app by title (regex) or PID, with the UI Automation backend (`uia`, the
  recommended one for modern WPF/UWP/WinForms) or `win32` (classic Win32).
- Walks the control tree of the main window (type, name, automation id, class) down to a given
  depth: it is the app's "DOM", input for the mapper and the agent to locate the controls.
- Computes a summary (number of controls, by type, how many lack an accessible name).

It does not click or change anything. For Electron apps, automate them as web (Playwright); this is for
native Windows apps. Requirements: Windows, `pip install pywinauto`.
"""
import argparse
import json
import sys
from pathlib import Path


def _connect(title=None, process=None, backend="uia"):
    try:
        from pywinauto import Application
    except ImportError:
        raise RuntimeError("pywinauto is missing (Windows only): install it with `pip install pywinauto`.")
    app = Application(backend=backend)
    try:
        if process:
            app.connect(process=int(process), timeout=10)
        elif title:
            app.connect(title_re=title, timeout=10)
        else:
            raise RuntimeError("Specify which app to connect to with --title \"<regex>\" or --process <PID>.")
    except RuntimeError:
        raise
    except Exception as ex:
        raise RuntimeError(f"Could not connect to the app: {ex}. Is it open? Try --process <PID> or the other --backend.")
    return app


def _node(ctrl, depth, max_depth):
    info = ctrl.element_info
    def g(attr):
        try:
            return getattr(info, attr)
        except Exception:
            return None
    node = {"type": g("control_type") or g("class_name"), "name": g("name"),
            "automation_id": g("automation_id"), "class": g("class_name")}
    children = []
    if depth < max_depth:
        try:
            for ch in ctrl.children():
                children.append(_node(ch, depth + 1, max_depth))
        except Exception:
            pass
    node["children"] = children
    return node


def tree(title=None, process=None, backend="uia", max_depth=6):
    app = _connect(title, process, backend)
    window = app.top_window()
    window.wait("exists", timeout=10)
    return _node(window.wrapper_object(), 0, max_depth)


def tree_summary(node):
    """Testable tree summary: total controls, by type and how many lack an accessible name."""
    total, by_type, no_name = 0, {}, 0
    stack = [node] if node else []
    while stack:
        n = stack.pop()
        total += 1
        t = n.get("type") or "?"
        by_type[t] = by_type.get(t, 0) + 1
        if not (n.get("name") or "").strip():
            no_name += 1
        stack.extend(n.get("children") or [])
    return {"controls": total, "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1])), "no_name": no_name}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Read-only survey of the control tree of a desktop app.")
    ap.add_argument("--title", default="", help="regex of the window title")
    ap.add_argument("--process", default="", help="process PID")
    ap.add_argument("--backend", default="uia", choices=["uia", "win32"])
    ap.add_argument("--depth", type=int, default=6, help="maximum tree depth")
    ap.add_argument("--output", default="", help="path where to save the JSON (optional)")
    args = ap.parse_args(argv)
    try:
        a = tree(args.title or None, args.process or None, args.backend, args.depth)
    except RuntimeError as ex:
        print(f"[desktop] {ex}", file=sys.stderr)
        return 2
    data = {"tree": a, "summary": tree_summary(a)}
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[desktop] Tree in {p}", file=sys.stderr)
    print(text)
    r = data["summary"]
    print(f"[desktop] {r['controls']} control(s), {r['no_name']} without an accessible name.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
