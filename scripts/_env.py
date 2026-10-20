#!/usr/bin/env python3
"""
Reads the .env at the k0lmenIA root, with the same rules as k0lmena (dotenv) and
scripts/mcp/read-env.js:

- `KEY=value`, with an optional leading `export`; surrounding spaces are ignored.
- Value in single or double quotes: taken literally (a `#` inside is not a comment).
- Unquoted value: a trailing ` # comment` is discarded.
- Empty lines and comments (`#`) are ignored. Tolerates a BOM (files saved on Windows).
- K0LMENA_ENV_FILE points to another file (for example, in CI).

Variables already defined in the environment take precedence over the file.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def env_file():
    return Path(os.environ.get("K0LMENA_ENV_FILE") or ROOT / ".env")


def read_env(file=None):
    """Returns {key: value} from the file (without touching os.environ)."""
    file = Path(file) if file else env_file()
    values = {}
    if not file.exists():
        return values
    for line in file.read_text(encoding="utf-8-sig").splitlines():
        m = _LINE.match(line)
        if not m or line.lstrip().startswith("#"):
            continue
        value = m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*$", "", value)
        values[m.group(1)] = value
    return values


def load_env(file=None):
    """Loads the .env into os.environ without overriding what's already defined in the environment."""
    for key, value in read_env(file).items():
        os.environ.setdefault(key, value)
