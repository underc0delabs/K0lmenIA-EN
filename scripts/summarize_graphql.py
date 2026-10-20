#!/usr/bin/env python3
"""
Summarizes a GraphQL schema in a few lines: queries, mutations and subscriptions with their arguments and
types, and the input types, enums and objects they use (api-mapper and api-case-generator agents).

Usage (from the repo root; on Mac/Linux, python3):
    python scripts/summarize_graphql.py <source> [--token] [--header "X-Tenant: demo"] [--output summary.md]

<source> can be:
  - the URL of the GraphQL endpoint: it sends it the introspection query by POST (read-only). With
    --token it adds `Authorization: Bearer <API_TOKEN from the .env>` (the token is not printed);
  - an SDL schema file (`.graphql` / `.graphqls` / `.gql`);
  - a JSON with the result of an introspection (`{"data": {"__schema": ...}}` or `{"__schema": ...}`).

It keeps you from dumping the whole schema into the conversation: the summary says which operations exist, which
arguments are required (`!`), which values the enums accept and what each one returns. If the server has
introspection disabled (common in production), it says so: ask for the SDL file.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

def introspection_query(levels=3):
    """Introspection query; `levels` of ofType (3 is enough for [Type!]!). Fewer levels for
    servers with a depth limit."""
    ref = "kind name"
    for _ in range(levels):
        ref = f"kind name ofType {{ {ref} }}"
    return ("query Introspection { __schema { queryType { name } mutationType { name } subscriptionType { name } "
            "types { kind name description fields(includeDeprecated: true) { name description isDeprecated "
            "args { name type { ...Ref } defaultValue } type { ...Ref } } inputFields { name type { ...Ref } defaultValue } "
            "enumValues(includeDeprecated: true) { name isDeprecated } } } } "
            f"fragment Ref on __Type {{ {ref} }}")


def _type(ref):
    """Introspection type → GraphQL notation ('[String!]!')."""
    if not ref:
        return "?"
    if ref["kind"] in ("NON_NULL", "LIST") and not ref.get("ofType"):
        return "…"  # the server limited the introspection depth
    if ref["kind"] == "NON_NULL":
        return _type(ref.get("ofType")) + "!"
    if ref["kind"] == "LIST":
        return "[" + _type(ref.get("ofType")) + "]"
    return ref.get("name") or "?"


def _base_name(kind):
    return re.sub(r"[\[\]!]", "", kind)


def from_introspection(data):
    """Introspection result → model {'roots': {...}, 'types': {...}}."""
    schema = (data.get("data") or data).get("__schema")
    if not schema:
        raise ValueError("The JSON has no __schema (did the introspection return errors?).")
    roots = {"query": (schema.get("queryType") or {}).get("name"),
             "mutation": (schema.get("mutationType") or {}).get("name"),
             "subscription": (schema.get("subscriptionType") or {}).get("name")}
    types = {}
    for t in schema.get("types") or []:
        if t["name"].startswith("__"):
            continue
        types[t["name"]] = {
            "kind": t["kind"],
            "fields": [{"name": f["name"], "type": _type(f["type"]), "deprecated": f.get("isDeprecated", False),
                        "args": [{"name": a["name"], "type": _type(a["type"]), "default": a.get("defaultValue")}
                                 for a in f.get("args") or []]} for f in t.get("fields") or []]
                      + [{"name": f["name"], "type": _type(f["type"]), "args": [], "default": f.get("defaultValue")}
                         for f in t.get("inputFields") or []],
            "values": [e["name"] for e in t.get("enumValues") or []],
        }
    return {"roots": roots, "types": types}


_SCALARS = {"String", "Int", "Float", "Boolean", "ID"}


def from_sdl(text):
    """SDL schema → the same model as from_introspection (simple reading, no directives)."""
    text = re.sub(r'"""[\s\S]*?"""', "", text)           # block descriptions
    text = re.sub(r'(?m)^\s*"[^"\n]*"\s*$', "", text)    # one-line descriptions
    text = re.sub(r"#.*", "", text)
    text = re.sub(r"=\s*\{[^{}]*\}", "= «object»", text)  # object defaults: do not confuse them with the closing brace
    roots = {"query": "Query", "mutation": "Mutation", "subscription": "Subscription"}
    m = re.search(r"\bschema\s*\{([^}]*)\}", text)
    if m:
        for op, name in re.findall(r"(query|mutation|subscription)\s*:\s*(\w+)", m.group(1)):
            roots[op] = name
    types = {}
    pattern = re.compile(r"\b(extend\s+)?(type|input|interface|enum)\s+(\w+)[^{]*\{([^}]*)\}")
    for _, kind_word, name, body in pattern.findall(text):
        kind = {"type": "OBJECT", "input": "INPUT_OBJECT", "interface": "INTERFACE", "enum": "ENUM"}[kind_word]
        t = types.setdefault(name, {"kind": kind, "fields": [], "values": []})
        if kind_word == "enum":
            t["values"] += re.findall(r"\b([A-Za-z_]\w*)\b(?:\s*@\w+(?:\([^)]*\))?)*", body)
            continue
        body = re.sub(r"\s+", " ", body)
        for field in re.finditer(r"(\w+)\s*(\(([^)]*)\))?\s*:\s*([\w\[\]!]+)(\s*=\s*[^\s@]+)?", body):
            args = [{"name": a, "type": ti, "default": (d or "").lstrip("= ").strip() or None}
                    for a, ti, d in re.findall(r"(\w+)\s*:\s*([\w\[\]!]+)(\s*=\s*[^,)\s]+)?", field.group(3) or "")]
            t["fields"].append({"name": field.group(1), "type": field.group(4), "args": args,
                                "deprecated": False})
    for scalar in re.findall(r"\bscalar\s+(\w+)", text):
        types.setdefault(scalar, {"kind": "SCALAR", "fields": [], "values": []})
    roots = {op: (n if n in types else None) for op, n in roots.items()}
    return {"roots": roots, "types": types}


def summarize(model):
    """Model → short Markdown text."""
    types = model["types"]
    lines, used = [], set()
    for op in ("query", "mutation", "subscription"):
        root = model["roots"].get(op)
        if not root or root not in types:
            continue
        fields = types[root]["fields"]
        lines += [f"## {op.capitalize()} ({len(fields)})", ""]
        for c in fields:
            args = ", ".join(f"{a['name']}: {a['type']}" + (f" = {a['default']}" if a.get("default") else "")
                             for a in c["args"])
            depr = " (deprecated)" if c.get("deprecated") else ""
            lines.append(f"- `{c['name']}({args})` → `{c['type']}`{depr}" if args else f"- `{c['name']}` → `{c['type']}`{depr}")
            used.add(_base_name(c["type"]))
            used.update(_base_name(a["type"]) for a in c["args"])
        lines.append("")
    # types reachable from the operations (one more level for return objects)
    pending, seen = list(used), set()
    while pending:
        n = pending.pop()
        if n in seen or n not in types:
            continue
        seen.add(n)
        if types[n]["kind"] in ("INPUT_OBJECT", "OBJECT", "INTERFACE"):
            pending += [_base_name(c["type"]) for c in types[n]["fields"]]
    sections = [("INPUT_OBJECT", "Input types"), ("ENUM", "Enums"), ("OBJECT", "Objects"), ("INTERFACE", "Interfaces")]
    for kind, title in sections:
        group = sorted(n for n in seen if types[n]["kind"] == kind and n not in model["roots"].values())
        if not group:
            continue
        lines += [f"## {title} ({len(group)})", ""]
        for n in group:
            t = types[n]
            if kind == "ENUM":
                lines.append(f"- `{n}`: {', '.join(t['values'])}")
            else:
                lines.append(f"- `{n}` {{ " + ", ".join(f"{c['name']}: {c['type']}" for c in t["fields"]) + " }")
        lines.append("")
    scalars = sorted(n for n in types if types[n]["kind"] == "SCALAR" and n not in _SCALARS)
    if scalars:
        lines += [f"Custom scalars: {', '.join(scalars)}", ""]
    return "\n".join(lines)


def introspect(url, headers):
    try:
        import requests
    except ImportError:
        sys.exit("The requests library is missing: pip install -r requirements.txt")
    messages = ""
    for levels in (3, 2, 1, 0):  # if the server limits the depth, it retries with a shorter one
        r = requests.post(url, json={"query": introspection_query(levels), "operationName": "Introspection"},
                          headers={"Content-Type": "application/json", **headers}, timeout=60)
        try:
            data = r.json()
        except ValueError:
            sys.exit(f"The endpoint answered {r.status_code} without JSON: is it the GraphQL URL?")
        if (data.get("data") or {}).get("__schema"):
            return data
        messages = "; ".join(str(e.get("message")) for e in data.get("errors") or [])
        if "depth" not in messages.lower() and "complex" not in messages.lower():
            break
    sys.exit(f"The introspection returned errors ({messages}). If it is disabled, ask for the SDL schema (.graphql).")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Summarizes a GraphQL schema (introspection, SDL or JSON)")
    ap.add_argument("source", help="GraphQL endpoint URL, .graphql (SDL) file or introspection JSON")
    ap.add_argument("--token", action="store_true", help="sends Authorization: Bearer with API_TOKEN from the .env")
    ap.add_argument("--header", action="append", default=[], help='extra header, "Name: value" (repeatable)')
    ap.add_argument("--output", help="saves the summary to this .md file (in addition to showing it)")
    a = ap.parse_args(argv)
    if re.match(r"^https?://", a.source):
        headers = dict(h.split(":", 1) for h in a.header)
        headers = {k.strip(): v.strip() for k, v in headers.items()}
        if a.token:
            from _env import read_env
            token = read_env().get("API_TOKEN")
            if not token:
                sys.exit("You asked for --token but API_TOKEN is missing from the root .env.")
            headers["Authorization"] = f"Bearer {token}"
        model = from_introspection(introspect(a.source, headers))
        source = a.source
    else:
        path = Path(a.source)
        if not path.exists():
            sys.exit(f"{path} does not exist.")
        text = path.read_text(encoding="utf-8-sig")
        model = from_introspection(json.loads(text)) if path.suffix.lower() == ".json" else from_sdl(text)
        source = path.as_posix()
    summary = f"# GraphQL schema\n\nSource: {source}\n\n" + summarize(model)
    if "…" in summary:
        summary += ("\n> The server limits the introspection depth: some types were left as `[…]`. "
                    "For the full detail, ask for the SDL schema (.graphql).\n")
    print(summary)
    if a.output:
        Path(a.output).write_text(summary, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
