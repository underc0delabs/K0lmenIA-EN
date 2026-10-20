#!/usr/bin/env python3
"""
Converts Bruno and Insomnia collections to Postman Collection v2.1 (what Newman runs).

Usage (from the repo root; on Mac/Linux, python3):
    python scripts/convert_collection.py <source> [--output <folder>] [--environment <name>]

<source> can be:
  - a **Bruno** collection: the folder that has `bruno.json` (with its `.bru` files, subfolders and
    `environments/*.bru`);
  - an **Insomnia v4** export (`.json` with `"_type": "export"`): requests, folders and environments;
  - an **Insomnia v5** export (`.yaml`, `type: collection.insomnia.rest/5.0`, Insomnia 11+). It needs
    PyYAML (`pip install pyyaml`); if it is not installed, it says so.
  - a **Postman** collection: it is returned as is (it does not need to be converted).

Writes to --output (by default, the source folder) `<name>.postman_collection.json` and, if the
collection has an environment, `<name>.postman_environment.json`. --environment picks which one (Bruno: the
name of the environments/ file without `.bru`; Insomnia: the name of the sub-environment). If there is
only one, that one is used.

What it converts:
  - Requests (method, URL, headers, query and path params, bearer, basic and API key authentication) and
    folders, in the order of the collection.
  - JSON, text, XML, form-urlencoded, multipart (without files) and **GraphQL** bodies (query + variables,
    Postman's graphql mode, which Newman runs the same way).
  - Variables: `{{ _.var }}` (Insomnia) and `{{var}}` (Bruno) end up as Postman `{{var}}`.
  - Bruno: `assert` → `pm.test` (eq, neq, gt, gte, lt, lte, in, notIn, contains, notContains, length,
    matches, notMatches, startsWith, endsWith, between, isEmpty, isNotEmpty, isNull, isUndefined,
    isDefined, isTruthy, isFalsy, isJson, isNumber, isString, isBoolean, isArray); `vars:pre-request`
    and `vars:post-response`; `script:pre-request`, `script:post-response` and `tests` with an adapter
    (`res`, `req`, `bru`, `test`, `expect` on top of `pm`).
  - Insomnia: `preRequestScript` and `afterResponseScript` (its `insomnia.*` API is the same as `pm.*`).

What cannot be converted (Insomnia `{% ... %}` template tags, files in multipart, OAuth2/AWS/Digest
auth, `bru.runRequest`, Insomnia unit tests, …) **is not lost silently**: it goes into the
list of warnings that the script prints and that `convert()` returns.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
METHODS = ("get", "post", "put", "patch", "delete", "options", "head", "connect", "trace")
# Blocks of a .bru file whose content is free text (not key: value).
TEXT_BLOCKS = {"body:json", "body:text", "body:xml", "body:graphql", "body:graphql:vars", "body:sparql",
                 "script:pre-request", "script:post-response", "tests", "docs"}


class Conversion:
    def __init__(self, format, collection, environment=None, warnings=None):
        self.format = format
        self.collection = collection
        self.environment = environment
        self.warnings = warnings or []


# --------------------------------------------------------------------------- common

def detect_format(path):
    """'bruno' | 'insomnia4' | 'insomnia5' | 'postman' | None."""
    path = Path(path)
    if path.is_dir():
        return "bruno" if (path / "bruno.json").exists() else None
    if path.name == "bruno.json":
        return "bruno"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix.lower() in (".yaml", ".yml"):
        return "insomnia5" if re.search(r"^type:\s*['\"]?collection\.insomnia\.rest/5", text, re.M) else None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if isinstance(data, dict):
        if data.get("_type") == "export" and isinstance(data.get("resources"), list):
            return "insomnia4"
        if "item" in data and "info" in data:
            return "postman"
    return None


def variables(text, warnings=None, where=""):
    """Normalizes the variables to the Postman format: {{ _.x }} / {{ x }} / {{process.env.X}} → {{x}}."""
    if not isinstance(text, str):
        return text
    if warnings is not None and "{%" in text:
        warnings.append(f"{where}: it has Insomnia template tags ({{% ... %}}) that Postman does not understand; they were "
                        "left as is. Replace them with a variable or a script.")
    if warnings is not None and re.search(r"\{\{\s*process\.env\.", text):
        warnings.append(f"{where}: it uses {{{{process.env.X}}}}; it became {{{{X}}}}. Define it in the environment or with --env-var.")
    text = re.sub(r"\{\{\s*_\[\s*['\"]([^'\"]+)['\"]\s*\]\s*\}\}", r"{{\1}}", text)
    text = re.sub(r"\{\{\s*_\.([\w.\-]+)\s*\}\}", r"{{\1}}", text)
    text = re.sub(r"\{\{\s*process\.env\.([\w.\-]+)\s*\}\}", r"{{\1}}", text)
    return re.sub(r"\{\{\s*([$\w.\-]+)\s*\}\}", r"{{\1}}", text)


def _header(name, value, active=True):
    h = {"key": name, "value": value}
    if not active:
        h["disabled"] = True
    return h


def _auth_bearer(token):
    return {"type": "bearer", "bearer": [{"key": "token", "value": token, "type": "string"}]}


def _auth_basic(username, password):
    return {"type": "basic", "basic": [{"key": "username", "value": username, "type": "string"},
                                       {"key": "password", "value": password, "type": "string"}]}


def _auth_apikey(key, value, where="header"):
    return {"type": "apikey", "apikey": [{"key": "key", "value": key, "type": "string"},
                                         {"key": "value", "value": value, "type": "string"},
                                         {"key": "in", "value": "query" if where in ("query", "queryparams") else "header",
                                          "type": "string"}]}


def _event(kind, lines):
    return {"listen": kind, "script": {"type": "text/javascript", "exec": lines}}


def _with_query(url, params):
    """Adds the active query params to the URL if it does not have them yet."""
    active = [(k, v) for k, v, enabled in params if enabled]
    if not active or "?" in url:
        return url
    return url + "?" + "&".join(f"{k}={v}" for k, v in active)


def _environment(name, values):
    return {"name": name, "values": [{"key": k, "value": v, "enabled": True} for k, v in values.items()],
            "_postman_variable_scope": "environment"}


def _flatten(data, prefix=""):
    """{"a": {"b": 1}} → {"a.b": "1"} (Insomnia environments allow nested objects)."""
    flat = {}
    for k, v in (data or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            flat.update(_flatten(v, key + "."))
        else:
            flat[key] = v if isinstance(v, str) else json.dumps(v) if isinstance(v, (list, bool)) or v is None else str(v)
    return flat


def _collection(name, items, source, auth=None, collection_variables=None):
    col = {"info": {"name": name, "schema": SCHEMA,
                    "description": f"Converted from {source} with scripts/convert_collection.py."},
           "item": items}
    if auth:
        col["auth"] = auth
    if collection_variables:
        col["variable"] = [{"key": k, "value": v} for k, v in collection_variables.items()]
    return col


# --------------------------------------------------------------------------- Bruno

def parse_bru(text):
    """Reads a .bru file → {block: dict | list | str}. The dicts are {key: (value, active)}."""
    blocks = {}
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z][\w:\-]*)\s*([{\[])\s*$", lines[i])
        if not m:
            i += 1
            continue
        name, opener = m.group(1), m.group(2)
        closer = "}" if opener == "{" else "]"
        body = []
        i += 1
        while i < len(lines) and lines[i].rstrip() != closer:
            body.append(lines[i])
            i += 1
        i += 1
        if opener == "[":
            blocks[name] = [x.strip().rstrip(",") for x in body if x.strip()]
        elif name in TEXT_BLOCKS:
            blocks[name] = "\n".join(x[2:] if x.startswith("  ") else x for x in body).strip("\n")
        else:
            blocks[name] = _bru_pairs(body)
    return blocks


def _bru_pairs(lines):
    pairs = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        m = re.match(r"^(~?)(\"[^\"]*\"|'[^']*'|[^:]+?)\s*:\s?(.*)$", line)
        if not m:
            continue
        active, key, value = not m.group(1), m.group(2).strip().strip("\"'"), m.group(3)
        if value.strip() == "'''":  # multiline value
            parts = []
            while i < len(lines) and lines[i].strip() != "'''":
                parts.append(lines[i].strip())
                i += 1
            i += 1
            value = "\n".join(parts)
        pairs[key] = (value.strip(), active)
    return pairs


BRU_ADAPTER = [
    "// Adapted from Bruno by scripts/convert_collection.py: res, req, bru, test and expect on top of pm.",
    "const bru = { setVar: (k, v) => pm.collectionVariables.set(k, v), getVar: (k) => pm.variables.get(k),",
    "  setEnvVar: (k, v) => pm.environment.set(k, v), getEnvVar: (k) => pm.environment.get(k),",
    "  getProcessEnv: (k) => pm.variables.get(k), interpolate: (s) => pm.variables.replaceIn(s),",
    "  setNextRequest: (n) => postman.setNextRequest(n) };",
    "const req = { getUrl: () => pm.request.url.toString(), setUrl: (u) => pm.request.url.update(u),",
    "  getMethod: () => pm.request.method, getHeader: (n) => pm.request.headers.get(n),",
    "  setHeader: (n, v) => pm.request.headers.upsert({ key: n, value: v }),",
    "  getBody: () => { try { return JSON.parse(pm.request.body.raw); } catch (e) { return pm.request.body && pm.request.body.raw; } },",
    "  setBody: (b) => pm.request.body.update(typeof b === 'string' ? b : JSON.stringify(b)) };",
    "const test = (name, fn) => pm.test(name, fn);",
    "const expect = pm.expect;",
]
RES_ADAPTER = [
    "const __body = (() => { try { return pm.response.json(); } catch (e) { return pm.response.text(); } })();",
    "const __headers = Object.fromEntries(pm.response.headers.all().map((h) => [h.key.toLowerCase(), h.value]));",
    "const res = { status: pm.response.code, statusText: pm.response.status, body: __body, headers: __headers,",
    "  responseTime: pm.response.responseTime, getStatus: () => pm.response.code, getBody: () => __body,",
    "  getHeader: (n) => __headers[String(n).toLowerCase()], getHeaders: () => __headers,",
    "  getResponseTime: () => pm.response.responseTime };",
]


def _js_value(text):
    """The value of a Bruno assert as a JavaScript literal."""
    t = text.strip()
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return t
    if t in ("true", "false", "null", "undefined"):
        return t
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'`":
        t = t[1:-1]
    if "{{" in t:
        return f"pm.variables.replaceIn({json.dumps(t)})"
    return json.dumps(t)


def _bru_assert(lhs, rule, warnings, where):
    """A Bruno assert line ('res.status', 'eq 200') → pm.test, or None if it is not recognized."""
    m = re.match(r"^(\w+)\s*(.*)$", rule.strip())
    if not m:
        warnings.append(f"{where}: could not understand the assert '{lhs}: {rule}'; it was not converted.")
        return None
    op, arg = m.group(1), m.group(2)
    v = _js_value(arg) if arg else None
    as_list = lambda: "[" + ", ".join(_js_value(x) for x in arg.split(",") if x.strip()) + "]"  # noqa: E731
    ops = {
        "eq": f"expect({lhs}).to.eql({v})", "neq": f"expect({lhs}).to.not.eql({v})",
        "gt": f"expect({lhs}).to.be.above({v})", "gte": f"expect({lhs}).to.be.at.least({v})",
        "lt": f"expect({lhs}).to.be.below({v})", "lte": f"expect({lhs}).to.be.at.most({v})",
        "in": f"expect({lhs}).to.be.oneOf({as_list()})", "notIn": f"expect({lhs}).to.not.be.oneOf({as_list()})",
        "contains": f"expect({lhs}).to.include({v})", "notContains": f"expect({lhs}).to.not.include({v})",
        "length": f"expect({lhs}).to.have.lengthOf({v})",
        "matches": f"expect(String({lhs})).to.match(new RegExp({v}))",
        "notMatches": f"expect(String({lhs})).to.not.match(new RegExp({v}))",
        "startsWith": f"expect(String({lhs}).startsWith({v})).to.be.true",
        "endsWith": f"expect(String({lhs}).endsWith({v})).to.be.true",
        "between": f"expect({lhs}).to.be.within({as_list()[1:-1] or 'undefined'})",
        "isEmpty": f"expect({lhs}).to.be.empty", "isNotEmpty": f"expect({lhs}).to.not.be.empty",
        "isNull": f"expect({lhs}).to.be.null", "isUndefined": f"expect({lhs}).to.be.undefined",
        "isDefined": f"expect({lhs}).to.not.be.undefined", "isTruthy": f"expect({lhs}).to.be.ok",
        "isFalsy": f"expect({lhs}).to.not.be.ok", "isJson": f"expect({lhs}).to.be.an('object')",
        "isNumber": f"expect({lhs}).to.be.a('number')", "isString": f"expect({lhs}).to.be.a('string')",
        "isBoolean": f"expect({lhs}).to.be.a('boolean')", "isArray": f"expect({lhs}).to.be.an('array')",
    }
    if op not in ops:
        warnings.append(f"{where}: the operator '{op}' of the assert '{lhs}' has no equivalent; it was not converted.")
        return None
    return f"pm.test({json.dumps(f'{lhs}: {rule.strip()}')}, function () {{ {ops[op]}; }});"


def _review_script(script, warnings, where):
    if re.search(r"bru\.(runRequest|sendRequest|runner|setNextRequest\(null)|require\(|\bawait\b", script):
        warnings.append(f"{where}: the script uses require, await or bru.runRequest/sendRequest, which may not "
                        "work in Postman/Newman; review it.")


def _bru_request(file, blocks, warnings, inherited):
    meta = {k: v for k, (v, _) in blocks.get("meta", {}).items()}
    name = meta.get("name") or file.stem
    where = f"{file.name} ({name})"
    method = next((m for m in METHODS if m in blocks), None)
    if not method:
        warnings.append(f"{where}: it has no HTTP method (is it a gRPC or WebSocket request?); it was not converted.")
        return None
    data = {k: v for k, (v, _) in blocks[method].items()}
    url = variables(data.get("url", ""), warnings, where)
    for k, (v, active) in blocks.get("params:path", {}).items():
        if active:
            url = re.sub(rf":{re.escape(k)}(?=/|\?|$)", variables(v), url)
    url = _with_query(url, [(k, variables(v), a) for k, (v, a) in blocks.get("params:query", {}).items()])

    headers = [_header(k, variables(v, warnings, where), a) for k, (v, a) in inherited["headers"].items()
               if k not in blocks.get("headers", {})]
    headers += [_header(k, variables(v, warnings, where), a) for k, (v, a) in blocks.get("headers", {}).items()]
    req = {"method": method.upper(), "header": headers, "url": url}

    auth_type = data.get("auth", "inherit")
    auth = _bru_auth(auth_type, blocks, warnings, where)
    if auth:
        req["auth"] = auth

    body_type = data.get("body", "none")
    body = _bru_body(body_type, blocks, warnings, where, meta.get("type") == "graphql")
    if body:
        req["body"] = body

    before, after = [], []
    for k, (v, active) in blocks.get("vars:pre-request", {}).items():
        if active:
            before.append(f"pm.variables.set({json.dumps(k)}, pm.variables.replaceIn({json.dumps(variables(v))}));")
    if blocks.get("script:pre-request"):
        _review_script(blocks["script:pre-request"], warnings, where)
        before += blocks["script:pre-request"].split("\n")
    for k, (v, active) in blocks.get("vars:post-response", {}).items():
        if active:
            after.append(f"pm.collectionVariables.set({json.dumps(k)}, {v});")
    for lhs, (rule, active) in blocks.get("assert", {}).items():
        if active:
            line = _bru_assert(lhs, rule, warnings, where)
            if line:
                after.append(line)
    for block in ("script:post-response", "tests"):
        if blocks.get(block):
            _review_script(blocks[block], warnings, where)
            after += blocks[block].split("\n")
    item = {"name": name, "request": req}
    events = []
    if before:
        events.append(_event("prerequest", BRU_ADAPTER + before))
    if after:
        events.append(_event("test", BRU_ADAPTER + RES_ADAPTER + after))
    if events:
        item["event"] = events
    if blocks.get("docs"):
        item["request"]["description"] = blocks["docs"]
    return item


def _bru_auth(kind, blocks, warnings, where):
    if kind in ("inherit", ""):
        return None
    if kind == "none":
        return {"type": "noauth"}
    data = {k: variables(v) for k, (v, _) in blocks.get(f"auth:{kind}", {}).items()}
    if kind == "bearer":
        return _auth_bearer(data.get("token", ""))
    if kind == "basic":
        return _auth_basic(data.get("username", ""), data.get("password", ""))
    if kind == "apikey":
        return _auth_apikey(data.get("key", ""), data.get("value", ""), data.get("placement", "header"))
    warnings.append(f"{where}: the '{kind}' authentication is not converted; configure it in Postman or with a header.")
    return None


def _bru_body(kind, blocks, warnings, where, is_graphql):
    if kind == "graphql" or (is_graphql and "body:graphql" in blocks):
        return {"mode": "graphql", "graphql": {"query": blocks.get("body:graphql", ""),
                                               "variables": variables(blocks.get("body:graphql:vars", "")) or ""}}
    if kind in ("json", "text", "xml", "sparql"):
        text = variables(blocks.get(f"body:{kind}", ""), warnings, where)
        language = {"json": "json", "xml": "xml"}.get(kind, "text")
        return {"mode": "raw", "raw": text, "options": {"raw": {"language": language}}}
    if kind in ("formUrlEncoded", "form-urlencoded"):
        pairs = blocks.get("body:form-urlencoded", {})
        return {"mode": "urlencoded", "urlencoded": [dict(_header(k, variables(v), a)) for k, (v, a) in pairs.items()]}
    if kind in ("multipartForm", "multipart-form"):
        fields = []
        for k, (v, a) in blocks.get("body:multipart-form", {}).items():
            if v.startswith("@file("):
                warnings.append(f"{where}: the field '{k}' uploads a file; Newman needs the real path (src). Review it.")
                path = v[len("@file("):].rstrip(")")
                fields.append({"key": k, "type": "file", "src": path, **({} if a else {"disabled": True})})
            else:
                fields.append({"key": k, "value": variables(v), "type": "text", **({} if a else {"disabled": True})})
        return {"mode": "formdata", "formdata": fields}
    if kind not in ("none", ""):
        warnings.append(f"{where}: the body of type '{kind}' is not converted.")
    return None


def _bru_order(path):
    """Sort key of a request or folder: the seq of its meta, then the name."""
    file = path / "folder.bru" if path.is_dir() else path
    seq = 10 ** 6
    if file.exists():
        meta = parse_bru(file.read_text(encoding="utf-8-sig")).get("meta", {})
        try:
            seq = float(meta.get("seq", ("",))[0])
        except ValueError:
            pass
    return (seq, path.name.lower())


def _bru_folder(folder, warnings, inherited):
    items = []
    children = [p for p in folder.iterdir()
                if (p.is_dir() and p.name not in ("environments", "node_modules", ".git"))
                or (p.suffix == ".bru" and p.name not in ("collection.bru", "folder.bru"))]
    for p in sorted(children, key=_bru_order):
        if p.is_dir():
            own = dict(inherited["headers"])
            folder_bru = p / "folder.bru"
            name = p.name
            if folder_bru.exists():
                fb = parse_bru(folder_bru.read_text(encoding="utf-8-sig"))
                own.update(fb.get("headers", {}))
                name = fb.get("meta", {}).get("name", (p.name,))[0] or p.name
                if any(k.startswith(("script:", "vars:")) or k == "tests" for k in fb):
                    warnings.append(f"{p.name}/folder.bru: folder scripts and variables are not converted.")
            sub = _bru_folder(p, warnings, {"headers": own})
            if sub:
                items.append({"name": name, "item": sub})
        else:
            blocks = parse_bru(p.read_text(encoding="utf-8-sig"))
            item = _bru_request(p, blocks, warnings, inherited)
            if item:
                items.append(item)
    return items


def convert_bruno(folder, environment=None):
    folder = Path(folder)
    if folder.name == "bruno.json":
        folder = folder.parent
    warnings = []
    config = json.loads((folder / "bruno.json").read_text(encoding="utf-8-sig"))
    name = config.get("name") or folder.name
    inherited = {"headers": {}}
    auth = None
    col_bru = folder / "collection.bru"
    if col_bru.exists():
        cb = parse_bru(col_bru.read_text(encoding="utf-8-sig"))
        inherited["headers"] = cb.get("headers", {})
        kind = {k: v for k, (v, _) in cb.get("auth", {}).items()}.get("mode")
        if kind:
            auth = _bru_auth(kind, cb, warnings, "collection.bru")
        if any(k.startswith(("script:", "vars:")) or k == "tests" for k in cb):
            warnings.append("collection.bru: collection scripts and variables are not converted; move them to each request.")
    items = _bru_folder(folder, warnings, inherited)

    env = None
    envs = sorted((folder / "environments").glob("*.bru")) if (folder / "environments").exists() else []
    if environment and Path(environment).suffix == ".bru" and Path(environment).exists():
        chosen = Path(environment)
    elif environment:
        chosen = next((e for e in envs if e.stem.lower() == str(environment).lower()), None)
        if not chosen:
            warnings.append(f"The environment '{environment}' does not exist. Available: {', '.join(e.stem for e in envs) or 'none'}.")
    else:
        chosen = envs[0] if len(envs) == 1 else None
        if len(envs) > 1:
            warnings.append(f"There are several environments ({', '.join(e.stem for e in envs)}): pick one with --environment.")
    if chosen:
        eb = parse_bru(chosen.read_text(encoding="utf-8-sig"))
        values = {k: variables(v) for k, (v, active) in eb.get("vars", {}).items() if active}
        secrets = eb.get("vars:secret", [])
        for s in secrets:
            values.setdefault(s.lstrip("~"), "")
        if secrets:
            warnings.append(f"Environment {chosen.stem}: the secret variables ({', '.join(secrets)}) are left empty; "
                            "pass them with --env-var (the token, with API_TOKEN from the .env: run_newman.py does it on its own).")
        env = _environment(chosen.stem, values)
    return Conversion("bruno", _collection(name, items, "Bruno", auth), env, warnings)


# --------------------------------------------------------------------------- Insomnia

INSOMNIA_ADAPTER = ["// Adapted from Insomnia by scripts/convert_collection.py: its insomnia.* API is the pm.* one.",
                      "const insomnia = pm;"]


def _insomnia_request(r, warnings):
    """An Insomnia request (v4 or v5) → Postman item."""
    name = r.get("name") or "Request"
    where = f"Insomnia ({name})"
    url = variables(r.get("url", ""), warnings, where)
    params = [(p.get("name", ""), variables(p.get("value", ""), warnings, where), not p.get("disabled"))
              for p in r.get("parameters") or []]
    url = _with_query(url, params)
    headers = [_header(h.get("name", ""), variables(h.get("value", ""), warnings, where), not h.get("disabled"))
               for h in r.get("headers") or [] if h.get("name")]
    req = {"method": (r.get("method") or "GET").upper(), "header": headers, "url": url}

    auth = r.get("authentication") or {}
    if auth and not auth.get("disabled"):
        kind = auth.get("type")
        if kind == "bearer":
            prefix = auth.get("prefix")
            if prefix and prefix.lower() != "bearer":
                req["header"].append(_header("Authorization", f"{prefix} {variables(auth.get('token', ''))}"))
            else:
                req["auth"] = _auth_bearer(variables(auth.get("token", "")))
        elif kind == "basic":
            req["auth"] = _auth_basic(variables(auth.get("username", "")), variables(auth.get("password", "")))
        elif kind == "apikey":
            req["auth"] = _auth_apikey(variables(auth.get("key", "")), variables(auth.get("value", "")),
                                       str(auth.get("addTo", "header")).lower())
        elif kind == "none":
            req["auth"] = {"type": "noauth"}
        elif kind:
            warnings.append(f"{where}: the '{kind}' authentication is not converted; configure it in Postman or with a header.")

    body = r.get("body") or {}
    mime = (body.get("mimeType") or "").lower()
    if mime == "application/graphql":
        try:
            gql = json.loads(body.get("text") or "{}")
        except ValueError:
            gql = {"query": body.get("text", "")}
        vars_gql = gql.get("variables")
        req["body"] = {"mode": "graphql", "graphql": {
            "query": gql.get("query", ""),
            "variables": variables(json.dumps(vars_gql, ensure_ascii=False, indent=2)) if vars_gql else ""}}
    elif mime == "application/x-www-form-urlencoded":
        req["body"] = {"mode": "urlencoded", "urlencoded": [
            _header(p.get("name", ""), variables(p.get("value", "")), not p.get("disabled")) for p in body.get("params") or []]}
    elif mime == "multipart/form-data":
        fields = []
        for p in body.get("params") or []:
            if p.get("type") == "file":
                warnings.append(f"{where}: the field '{p.get('name')}' uploads a file ({p.get('fileName', '')}); review the path.")
                fields.append({"key": p.get("name", ""), "type": "file", "src": p.get("fileName", "")})
            else:
                fields.append({"key": p.get("name", ""), "value": variables(p.get("value", "")), "type": "text"})
        req["body"] = {"mode": "formdata", "formdata": fields}
    elif body.get("text") is not None or mime:
        language = "json" if "json" in mime else "xml" if "xml" in mime else "text"
        req["body"] = {"mode": "raw", "raw": variables(body.get("text", ""), warnings, where),
                       "options": {"raw": {"language": language}}}
    if body.get("fileName"):
        warnings.append(f"{where}: the body is a file ({body['fileName']}); it is not converted.")

    item = {"name": name, "request": req}
    scripts = r.get("scripts") or {}
    before = r.get("preRequestScript") or scripts.get("preRequest") or ""
    after = r.get("afterResponseScript") or scripts.get("afterResponse") or ""
    events = []
    if before.strip():
        events.append(_event("prerequest", INSOMNIA_ADAPTER + before.split("\n")))
    if after.strip():
        events.append(_event("test", INSOMNIA_ADAPTER + after.split("\n")))
    if events:
        item["event"] = events
    if r.get("description"):
        req["description"] = r["description"]
    return item


def _pick_insomnia_env(base, subs, environment, warnings):
    """Merges the base environment with the chosen sub-environment (by name, or the only one there is)."""
    values = _flatten(base.get("data") or {})
    name = base.get("name") or "Base Environment"
    chosen = None
    if environment:
        chosen = next((s for s in subs if (s.get("name") or "").lower() == str(environment).lower()), None)
        if not chosen:
            warnings.append(f"The environment '{environment}' does not exist. Available: {', '.join(s.get('name', '') for s in subs) or 'none'}.")
    elif len(subs) == 1:
        chosen = subs[0]
    elif len(subs) > 1:
        warnings.append(f"There are several environments ({', '.join(s.get('name', '') for s in subs)}): pick one with --environment.")
    if chosen:
        values.update(_flatten(chosen.get("data") or {}))
        name = chosen.get("name") or name
    values = {k: variables(v) for k, v in values.items()}
    return _environment(name, values) if values else None


def convert_insomnia4(file, environment=None):
    data = json.loads(Path(file).read_text(encoding="utf-8-sig"))
    warnings = []
    resources = data.get("resources") or []
    workspace = next((r for r in resources if r.get("_type") == "workspace"), {})
    children = {}
    for r in resources:
        children.setdefault(r.get("parentId"), []).append(r)
    order = lambda r: (r.get("metaSortKey", 0) if isinstance(r.get("metaSortKey"), (int, float)) else 0, r.get("name", ""))  # noqa: E731

    folder_variables = {}

    def build(parent):
        items = []
        for r in sorted(children.get(parent, []), key=order):
            if r.get("_type") == "request_group":
                if r.get("environment"):
                    folder_variables.update(_flatten(r["environment"]))
                    warnings.append(f"Folder '{r.get('name')}': its environment becomes collection variables (in "
                                    "Postman there are no folder variables).")
                items.append({"name": r.get("name") or "Folder", "item": build(r["_id"])})
            elif r.get("_type") == "request":
                items.append(_insomnia_request(r, warnings))
            elif r.get("_type") in ("grpc_request", "websocket_request"):
                warnings.append(f"'{r.get('name')}': {r['_type']} requests are not converted.")
        return items

    items = build(workspace.get("_id"))
    types = {r.get("_type") for r in resources}
    if types & {"unit_test_suite", "unit_test"}:
        warnings.append("Insomnia unit tests are not converted: move their validations to the afterResponseScript of each request.")
    base = next((r for r in resources if r.get("_type") == "environment" and r.get("parentId") == workspace.get("_id")), {})
    subs = [r for r in resources if r.get("_type") == "environment" and base and r.get("parentId") == base.get("_id")]
    env = _pick_insomnia_env(base, subs, environment, warnings) if base else None
    name = workspace.get("name") or Path(file).stem
    return Conversion("insomnia4", _collection(name, items, "Insomnia (v4)", None,
                                               {k: variables(v) for k, v in folder_variables.items()}), env, warnings)


def convert_insomnia5(file, environment=None):
    try:
        import yaml
    except ImportError:
        sys.exit("Reading Insomnia v5 exports (.yaml) requires PyYAML: pip install pyyaml")
    data = yaml.safe_load(Path(file).read_text(encoding="utf-8-sig")) or {}
    warnings = []

    def order(r):
        key = (r.get("meta") or {}).get("sortKey", 0)
        return (key if isinstance(key, (int, float)) else 0, r.get("name", ""))

    def build(entries):
        items = []
        for r in sorted(entries or [], key=order):
            if "children" in r:
                items.append({"name": r.get("name") or "Folder", "item": build(r.get("children"))})
                if r.get("environment"):
                    warnings.append(f"Folder '{r.get('name')}': its environment is not converted (in Postman there are no "
                                    "folder variables).")
            elif "url" in r or "method" in r:
                items.append(_insomnia_request(r, warnings))
        return items

    items = build(data.get("collection"))
    envs = data.get("environments") or {}
    env = _pick_insomnia_env(envs, envs.get("subEnvironments") or [], environment, warnings) if envs else None
    name = data.get("name") or Path(file).stem
    return Conversion("insomnia5", _collection(name, items, "Insomnia (v5)"), env, warnings)


# --------------------------------------------------------------------------- entry point

def convert(source, environment=None):
    """Converts the source collection. Returns a Conversion (collection, environment, warnings)."""
    fmt = detect_format(source)
    if fmt == "bruno":
        return convert_bruno(source, environment)
    if fmt == "insomnia4":
        return convert_insomnia4(source, environment)
    if fmt == "insomnia5":
        return convert_insomnia5(source, environment)
    if fmt == "postman":
        return Conversion("postman", json.loads(Path(source).read_text(encoding="utf-8-sig")))
    raise ValueError(f"Unrecognized format for {source}: it must be a Bruno folder (with bruno.json), "
                     "an Insomnia export (v4 .json or v5 .yaml) or a Postman collection.")


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "collection"


def save(conv, folder, name=None):
    """Writes the collection (and the environment) to the folder. Returns (collection_path, environment_path)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = name or _slug(conv.collection["info"]["name"])
    col_path = folder / f"{name}.postman_collection.json"
    col_path.write_text(json.dumps(conv.collection, ensure_ascii=False, indent=2), encoding="utf-8")
    env_path = None
    if conv.environment:
        env_path = folder / f"{name}.postman_environment.json"
        env_path.write_text(json.dumps(conv.environment, ensure_ascii=False, indent=2), encoding="utf-8")
    return col_path, env_path


def count_requests(items):
    return sum(count_requests(i["item"]) if "item" in i else 1 for i in items)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Converts Bruno and Insomnia collections to Postman v2.1")
    ap.add_argument("source", help="Bruno folder, Insomnia export (.json v4 / .yaml v5) or Postman collection")
    ap.add_argument("--output", help="folder where the converted collection is saved (by default, next to the source)")
    ap.add_argument("--environment", help="environment to use (Bruno: name of the .bru; Insomnia: sub-environment)")
    a = ap.parse_args(argv)
    source = Path(a.source)
    try:
        conv = convert(source, a.environment)
    except (ValueError, OSError) as e:
        sys.exit(str(e))
    if conv.format == "postman":
        print(f"{source} is already a Postman collection: it does not need to be converted.")
        return 0
    output = Path(a.output) if a.output else (source if source.is_dir() else source.parent)
    col_path, env_path = save(conv, output)
    print(f"{conv.format}: {count_requests(conv.collection['item'])} request(s) → {col_path}")
    if env_path:
        print(f"Environment '{conv.environment['name']}' → {env_path}")
    for warning in conv.warnings:
        print(f"  ! {warning}")
    if not conv.warnings:
        print("No warnings: everything was converted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
