#!/usr/bin/env python3
"""
Chooses which test cases to run for a change (test-case-selector agent): matches the change against
the case inventory and builds a selection prioritized by risk, with the command to run the
automated part and the list of the manual part.

Usage (from the repo root):
    python scripts/select_cases.py [--git main..feature/payments --repo ../my-app] [--files a.ts,b.ts]
        [--stories US-003,PROJ-55] [--text "release notes"] [--text-file notes.md]
        [--changes changes.json] [--budget-min 60] [--name release-2.4] [--analysis analysis.json]
    python scripts/select_cases.py --report-only --name release-2.4
        → applies the agent's analysis.json again and regenerates the report, without recalculating.

The change can come from (they are combined):
  --git RANGE      changed files, commit messages (with their Jira keys) and names of the functions
                   touched, from the application repository (--repo; by default the current one).
  --files          list of changed files (from a PR, for example).
  --stories        affected stories or issues (US-XXX or Jira/Azure DevOps keys).
  --text           release notes, the PR description or the summary of the issues.
  --changes        JSON built by the agent after reading the PR or Jira:
                   {"title": "...", "stories": ["US-003"], "words": ["payment", "card"],
                    "files": ["src/checkout/payment.ts"], "text": "..."}
Case inventory (whatever exists): manual cases (output/test-cases/manual/cases-US-XXX.xlsx),
BDD scenarios (output/test-cases/bdd/*.feature) and k0lmena automation
(tools/k0lmena/{web,api,mobile}/features), with their latest result (npm test), the flaky ones
(output/failures) and the bugs (output/bug-reports). Optional: input/component-map.json maps
code folders to stories and words: {"paths": {"src/checkout/": ["US-003", "payment"]}}.

Each case gets a score (affected story, words matching the change —with synonyms
in English and Spanish—, priority, latest result, flaky, open bugs) and ends up in a group:
Essential · Recommended · Minimal regression (smoke and Critical priority) · Not selected.
It also flags the changes that touch no case (uncovered changes).

Leaves output/case-selection/<name>/ with selection.json, selection.csv (to run by hand) and
selection-report.html. With the same name, the previous run moves to history/ (last 5).
"""
import argparse
import csv
import datetime
import glob
import json
import math
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "management"))
import collect_results as rec  # noqa: E402
from estimation import estimate_case  # noqa: E402
import _history  # noqa: E402

GROUPS = ["Essential", "Recommended", "Minimal regression", "Not selected"]
PRIO_POINTS = {"Critical": 15, "High": 10, "Medium": 4, "Low": 0}
RE_US = re.compile(r"\bUS-\d+\b", re.I)
RE_KEY = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
RE_TC = re.compile(r"^TC(-API)?-\d+$")

# Words that say nothing about the area of the change (English and Spanish).
STOPWORDS = set("""a al algo ante antes asi como con contra cual cuando de del desde donde durante e el ella ellos en entre era es esa ese eso esta
este esto fue ha hay la las le les lo los mas me mi muy no nos o otra otro para pero poco por que se segun ser si sin sobre son su sus tambien
tiene todo tras un una uno unos y ya the and or of to in on for with from by at is are be this that it as an fix fixes fixed feat feature
chore refactor docs doc test tests spec specs style merge branch pull request pr wip update updates updated add added remove removed change
changes changed new old src app apps lib libs index main mod module modules component components page pages view views util utils helper
helpers common core shared base default js ts tsx jsx py java cs go rb php css scss html json yml yaml md vue svelte kt swift dart sql
config configs package lock dist build public assets static res resources internal pkg cmd service services controller controllers model
models repository repositories dto entity entities handler handlers route routes router api v1 v2 v3 get set put post delete patch init
caso casos cuando usuario debe deberia validar verificar ingresa hace clic click boton pantalla campo dado entonces dato datos paso pasos
case should must validate verify enters clicks button screen field data step steps expected precondition preconditions
given when then and but scenario feature background resultado esperado precondicion precondiciones prueba pruebas cp hu ca tc us ac
function func def class const let var export import return async await public private static void null true false""".split())

# Synonyms (English and Spanish) → one concept. That way "payment" in a file finds cases about "pago".
CONCEPTS = {
    "login": "login signin sign-in logon ingreso ingresar iniciar sesion autenticacion auth authentication credencial credenciales credential credentials",
    "logout": "logout signout salir cerrar desconectar",
    "signup": "signup sign-up register registration registro registrar alta create-account onboarding",
    "cart": "cart carrito basket bolsa",
    "payment": "payment payments pay pago pagos pagar paga checkout cobro billing mercadopago stripe",
    "card": "card cards tarjeta tarjetas",
    "order": "order orders pedido pedidos orden ordenes compra compras purchase purchases",
    "profile": "profile perfil account accounts cuenta cuentas settings ajustes preferencias preferences",
    "password": "password passwords contrasena clave pass passwd reset recuperar recuperacion recovery",
    "search": "search busqueda buscar buscador filter filtro filtros finder",
    "product": "product products producto productos item items articulo articulos catalog catalogo sku",
    "invoice": "invoice invoices factura facturas facturacion receipt receipts comprobante",
    "email": "email mail correo emails mails smtp",
    "notification": "notification notifications notificacion notificaciones alert alerts alerta alertas push",
    "home": "home inicio landing portada dashboard tablero",
    "admin": "admin administracion administration backoffice",
    "report": "report reports reporte reportes informe informes export exportar",
    "discount": "discount discounts descuento descuentos coupon coupons cupon cupones promo promocion promociones promotion promotions voucher",
    "shipping": "shipping envio envios delivery deliveries entrega entregas despacho",
    "stock": "stock inventory inventario existencias",
    "price": "price prices precio precios tarifa tarifas rate rates cotizacion quote",
    "contact": "contact contacto contactos soporte support",
    "navigation": "menu nav navbar navigation navegacion header encabezado footer sidebar",
    "user": "user users usuario usuarios cliente clientes customer customers",
    "permission": "permission permissions permiso permisos rol roles role acl",
    "file": "upload uploads archivo archivos adjunto adjuntos attachment attachments file files subir",
}
SYNONYM = {}
for _c, _ws in CONCEPTS.items():
    for _w in _ws.split():
        SYNONYM[_w] = _c


def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _root(t):
    if t in SYNONYM:
        return SYNONYM[t]
    for suf in ("es", "s"):
        if len(t) > 4 and t.endswith(suf) and t[: -len(suf)] in SYNONYM:
            return SYNONYM[t[: -len(suf)]]
    if len(t) > 5 and t.endswith("es"):
        t = t[:-2]
    elif len(t) > 4 and t.endswith("s"):
        t = t[:-1]
    return SYNONYM.get(t, t)


def tokens(text):
    """Text (or file path, or nameInCamelCase) → normalized concepts."""
    text = RE_KEY.sub(" ", str(text or ""))  # keys (PROJ-55) count as stories, not as words
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = _strip_accents(text.lower())
    output = []
    for t in re.split(r"[^a-z0-9ñ]+", text):
        if len(t) < 3 or t.isdigit() or t in STOPWORDS:
            continue
        r = _root(t)
        if r not in STOPWORDS and len(r) >= 3:
            output.append(r)
    return output


# ------------------------------------------------------------------ the change
def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def git_ranges(rng):
    """(range for git diff, range for git log). `A..B` or `A...B`: the diff goes from the merge base
    (`A...B`, so the changes A added afterwards are not included) and the log is the commits of B that are not
    in A (`A..B`). A single commit or ref is left as is."""
    m = re.fullmatch(r"(.*?)\.{2,3}(.*)", rng.strip())
    if not m:
        return rng, rng
    base, tip = m.group(1) or "HEAD", m.group(2) or "HEAD"
    return f"{base}...{tip}", f"{base}..{tip}"


def read_change(a):
    change = {"title": "", "files": [], "stories": set(), "keys": set(), "commits": [], "functions": [], "text": "", "words": [],
              "sources": []}
    if a.git:
        repo = Path(a.repo or ".").resolve()
        r_diff, r_log = git_ranges(a.git)
        change["files"] += [l.strip() for l in _git(repo, "diff", "--name-only", r_diff).splitlines() if l.strip()]
        msgs = _git(repo, "log", "--format=%h%x09%s%x09%b%x1e", r_log)
        for block in msgs.split("\x1e"):
            parts = block.strip().split("\t")
            if len(parts) >= 2:
                change["commits"].append({"hash": parts[0], "message": parts[1], "body": parts[2].strip() if len(parts) > 2 else ""})
        # Functions and classes touched (hunk headers: "@@ -10,3 +10,4 @@ function validateCard(").
        diff = _git(repo, "diff", "--unified=0", r_diff)
        change["functions"] = sorted({m.strip() for m in re.findall(r"^@@[^@]*@@\s*(.+)$", diff, re.M)})[:80]
        change["sources"].append(f"git {a.git} ({repo.name})")
    if a.files:
        change["files"] += [x.strip() for x in a.files.split(",") if x.strip()]
        change["sources"].append("file list")
    if a.stories:
        for h in a.stories.split(","):
            h = h.strip().upper()
            (change["stories"] if RE_US.fullmatch(h) else change["keys"]).add(h)
        change["sources"].append("stories in the request")
    texts = []
    if a.text:
        texts.append(a.text)
    if a.text_file:
        texts.append(Path(a.text_file).read_text(encoding="utf-8"))
        change["sources"].append(Path(a.text_file).name)
    if a.changes:
        c = json.loads(Path(a.changes).read_text(encoding="utf-8"))
        change["title"] = c.get("title") or change["title"]
        change["files"] += c.get("files") or []
        for h in c.get("stories") or []:
            (change["stories"] if RE_US.fullmatch(h.upper()) else change["keys"]).add(h.upper())
        change["words"] += c.get("words") or []
        if c.get("text"):
            texts.append(c["text"])
        change["sources"].append(Path(a.changes).name)
    if a.text:
        change["sources"].append("request text")
    change["text"] = "\n".join(texts)
    for c in change["commits"]:
        for m in RE_KEY.findall(f'{c["message"]} {c["body"]}'):
            (change["stories"] if RE_US.fullmatch(m) else change["keys"]).add(m.upper())
    for m in RE_KEY.findall(change["text"]):
        (change["stories"] if RE_US.fullmatch(m) else change["keys"]).add(m.upper())
    change["files"] = list(dict.fromkeys(change["files"]))
    return change


def keys_to_stories(keys):
    """Jira/Azure keys → local US items, from the management traceability and the context sheets."""
    mapping = {}
    for file in glob.glob(str(ROOT / "output" / "management" / "US-*.json")):
        try:
            t = json.loads(Path(file).read_text(encoding="utf-8"))
        except ValueError:
            continue
        us = Path(file).name.split("-")[0] + "-" + Path(file).name.split("-")[1]
        for k in [t.get("story_key"), t.get("issue"), t.get("story")] + [v.get("story") for v in (t.get("cases") or {}).values() if isinstance(v, dict)]:
            if k:
                mapping[str(k).upper()] = us.upper()
    for file in glob.glob(str(ROOT / "output" / "context" / "context-US-*.md")):
        us = re.search(r"(US-\d+)", file).group(1).upper()
        for k in RE_KEY.findall(Path(file).read_text(encoding="utf-8")[:4000]):
            if not RE_US.fullmatch(k):
                mapping.setdefault(k.upper(), us)
    return {mapping[k] for k in keys if k in mapping}


def component_map():
    file = ROOT / "input" / "component-map.json"
    if not file.exists():
        return {}
    try:
        return json.loads(file.read_text(encoding="utf-8")).get("paths") or {}
    except ValueError:
        print(f"[!] {file.name} is not valid JSON: ignoring it.", file=sys.stderr)
        return {}


# ------------------------------------------------------------------ the inventory
def _feature_title(path):
    m = re.search(r"^\s*Feature:\s*(.+)$", Path(path).read_text(encoding="utf-8-sig"), re.M)
    return m.group(1).strip() if m else ""


def inventory():
    from readers import read_feature, read_xlsx
    cases = {}

    def case(us, cid):
        k = f"{us}:{cid}"
        return cases.setdefault(k, {"key": k, "story": us, "id": cid, "title": "", "priority": "", "tags": set(), "text": [],
                                    "story_title": "", "sources": [], "automated": [], "steps": 0, "result": None,
                                    "duration_s": None, "flaky": False, "bugs": [], "manual_minutes": None})

    for x in sorted(glob.glob(str(ROOT / "output" / "test-cases" / "manual" / "cases-US-*.xlsx"))):
        us = re.search(r"(US-\d+)", x).group(1).upper()
        try:
            for c in read_xlsx(x):
                k = case(us, c["id"])
                k["title"] = k["title"] or c["title"]
                k["priority"] = k["priority"] or c["priority"]
                k["tags"].update(c.get("tags") or [])
                k["text"] += [c["title"], c["title"], c.get("description", ""), c.get("preconditions", "")] + \
                    [f'{p.get("action", "")} {p.get("result", "")}' for p in c.get("steps") or []]
                k["steps"] = max(k["steps"], len(c.get("steps") or []))
                k["manual_minutes"] = estimate_case(c)["minutes"]
                if "Manual" not in k["sources"]:
                    k["sources"].append("Manual")
        except Exception as ex:  # a spreadsheet with another format does not stop the selection
            print(f"[!] I could not read {Path(x).name}: {ex}", file=sys.stderr)

    def from_features(pattern, source, suite=None):
        for x in sorted(glob.glob(str(ROOT / pattern), recursive=True)):
            try:
                scenarios = read_feature(x)
            except Exception:
                continue
            tit = _feature_title(x)
            for c in scenarios:
                tags = [t.upper() for t in c["tags"]]
                us = next((t for t in tags if RE_US.fullmatch(t)), None)
                m = re.search(r"(US-\d+)", Path(x).name, re.I)
                us = us or (m.group(1).upper() if m else "NO-US")
                k = case(us, c["id"])
                k["title"] = k["title"] or c["title"]
                k["story_title"] = k["story_title"] or tit
                if c.get("priority") and not k["priority"]:
                    # The .feature priority is only trusted if it comes from an explicit tag
                    # (@critical/@high/@medium/@low or @smoke); otherwise the manual case's one wins.
                    has_tag = any(t.lower() in ("critical", "high", "medium", "low", "smoke") for t in c["tags"])
                    k["priority"] = c["priority"] if has_tag else ""
                k["tags"].update(c["tags"])
                k["text"] += [c["title"], c["title"], c.get("gherkin", ""), tit]
                k["steps"] = max(k["steps"], len([l for l in c.get("gherkin", "").splitlines() if re.match(r"\s*(Given|When|Then|And|But|\*)\b", l)]))
                if not k["manual_minutes"]:
                    k["manual_minutes"] = estimate_case(c)["minutes"]
                if suite:
                    k["automated"].append({"suite": suite, "file": Path(x).relative_to(ROOT).as_posix(),
                                           "blocked": any(t.lower() == "blocked" for t in c["tags"])})
                if source not in k["sources"]:
                    k["sources"].append(source)

    from_features("output/test-cases/bdd/*.feature", "BDD")
    for suite in ("web", "api", "mobile"):
        from_features(f"tools/k0lmena/{suite}/features/**/*.feature", "Automated", suite)

    # Latest result and duration (npm test) and live runs.
    for r in sorted(rec.from_runs(None) + rec.from_cucumber(None), key=lambda r: r.get("moment") or 0):
        if not r.get("id") or not RE_TC.match(str(r["id"])):
            continue
        for k in cases.values():
            if k["id"] == r["id"] and (not r.get("title") or r["title"] == k["title"] or len([x for x in cases.values() if x["id"] == r["id"]]) == 1):
                k["result"] = {"status": r["status"], "source": r["source"]}
    for suite in ("web", "api", "mobile"):
        rep = rec.K0 / suite / "cucumber-report.json"
        try:
            features = json.loads(rep.read_text(encoding="utf-8") or "[]") if rep.exists() else []
        except ValueError:
            features = []
        for f in features:
            for sc in f.get("elements") or []:
                tags = [t["name"].lstrip("@").upper() for t in (f.get("tags") or []) + (sc.get("tags") or [])]
                us = next((t for t in tags if RE_US.fullmatch(t)), None)
                tc = next((t for t in tags if RE_TC.match(t)), None)
                k = cases.get(f"{us}:{tc}")
                if k:
                    k["duration_s"] = round(sum((p.get("result") or {}).get("duration") or 0 for p in sc.get("steps") or []) / 1e9, 1)
    for file in glob.glob(str(ROOT / "output" / "failures" / "*" / "failures.json")):
        try:
            d = json.loads(Path(file).read_text(encoding="utf-8"))
        except ValueError:
            continue
        for f in d.get("failures") or []:
            k = cases.get(f'{(f.get("story") or "").upper()}:{f.get("case")}')
            if k and f.get("category") == "Flaky":
                k["flaky"] = True
    for b in rec.from_bugs(None):
        if b["status"].lower() not in rec.OPEN:
            continue
        for k in cases.values():
            if k["story"] in (b.get("story") or ""):
                k["bugs"].append(b["id"])
    return list(cases.values())


# ------------------------------------------------------------------ score and groups
def select(change, cases, budget=None, min_per_step=1.5):
    paths = component_map()
    affected = set(change["stories"]) | keys_to_stories(change["keys"])
    # Words of the change with their weight (files and functions weigh more than free text).
    weights = Counter()
    origin = {}

    def add(text, weight, src):
        for t in tokens(text):
            weights[t] += weight
            origin.setdefault(t, set()).add(src)

    for f in change["files"]:
        add(f, 1.0, f)
        for path, values in paths.items():
            if f.replace("\\", "/").startswith(path.rstrip("*")):
                for v in values:
                    if RE_US.fullmatch(str(v).upper()):
                        affected.add(str(v).upper())
                    else:
                        add(v, 1.5, f"map: {path}")
    for fn in change["functions"]:
        add(fn, 0.6, "function touched")
    for c in change["commits"]:
        add(c["message"], 0.8, f'commit {c["hash"]}')
    for p in change["words"]:
        add(p, 1.5, "keyword")
    add(change["title"], 1.0, "title")
    add(change["text"], 0.5, "text")

    # IDF over the inventory: a word that is in every case distinguishes nothing.
    docs = []
    for c in cases:
        toks = Counter(tokens(" ".join(c["text"] + [c["title"], c.get("story_title", ""), " ".join(c["tags"])])))
        docs.append(toks)
    n = len(docs) or 1
    df = Counter(t for d in docs for t in d)
    idf = {t: math.log((n + 1) / (df[t] + 0.5)) for t in df}

    used = Counter()
    for c, toks in zip(cases, docs):
        reasons = []
        p = 0
        if c["story"] in affected:
            p += 60
            reasons.append(f'Story {c["story"]} is in the change')
        matches = sorted({t for t in weights if t in toks}, key=lambda t: -idf.get(t, 0) * weights[t])
        raw = sum(idf.get(t, 0) * min(2, toks[t]) * weights[t] for t in matches)
        kw = round(45 * (1 - math.exp(-raw / 6))) if raw else 0
        if kw:
            p += kw
            used.update(matches)
            ex = sorted({o for t in matches[:3] for o in origin.get(t, [])})[:2]
            reasons.append(f'Matches the change in: {", ".join(matches[:5])}' + (f' ({"; ".join(ex)})' if ex else ""))
        prio = c["priority"] or "Medium"
        if PRIO_POINTS.get(prio):
            p += PRIO_POINTS[prio]
            if prio in ("Critical", "High"):
                reasons.append(f"Priority {prio}")
        if c["result"] and c["result"]["status"] == "Failed":
            p += 10
            reasons.append(f'Failed in the latest run ({c["result"]["source"]})')
        if c["flaky"]:
            p += 6
            reasons.append("It is flaky")
        if c["bugs"]:
            p += 5
            reasons.append(f'There are open bugs in the story: {", ".join(c["bugs"][:3])}')
        c["score"] = min(100, p)
        c["matches"] = matches[:8]
        c["reasons"] = reasons
        smoke = any(t.lower() == "smoke" for t in c["tags"]) or prio == "Critical"
        if c["story"] in affected or c["score"] >= 60:
            c["group"] = "Essential"
        elif c["score"] >= 35 and (kw or c["story"] in affected):
            c["group"] = "Recommended"
        elif smoke:
            c["group"] = "Minimal regression"
            c["reasons"].append("It is smoke or Critical priority: it always runs")
        else:
            c["group"] = "Not selected"
        active = [x for x in c["automated"] if not x["blocked"]]
        c["type"] = "Automated" if active else "Manual"
        c["suite"] = active[0]["suite"] if active else None
        # Automated: what it took in the latest run. Manual: the formula of scripts/estimation.py.
        c["minutes"] = max(0.1, round((c["duration_s"] or 30) / 60, 1)) if active else (
            c.get("manual_minutes") or round(max(2, (c["steps"] or 3) * min_per_step), 1))

    # Time budget: the essential ones are kept and the rest are filled in by score.
    if budget:
        spent = sum(c["minutes"] for c in cases if c["group"] == "Essential")
        for c in sorted([c for c in cases if c["group"] in ("Recommended", "Minimal regression")], key=lambda c: -c["score"]):
            if spent + c["minutes"] <= budget:
                spent += c["minutes"]
            else:
                c["group"] = "Not selected"
                c["reasons"].append(f"Left out by the budget of {budget} min")

    # Uncovered changes: files whose content (words) does not appear in any case.
    no_coverage = []
    for f in change["files"]:
        ts = [t for t in set(tokens(f)) if not used.get(t)]
        if ts and not any(used.get(t) for t in set(tokens(f))):
            no_coverage.append({"file": f, "words": sorted(ts)[:6]})
    return affected, no_coverage, weights


def apply_adjustments(cases, analysis):
    for key, adj in (analysis.get("adjustments") or {}).items():
        for c in cases:
            if c["key"].upper() == key.upper() and adj.get("group") in GROUPS:
                c["original_group"] = c.get("original_group") or c["group"]
                c["group"] = adj["group"]
                c["reasons"] = [r for r in c["reasons"] if not r.startswith("Analysis adjustment")] + [f'Analysis adjustment: {adj.get("reason", "")}'.strip()]


def commands(cases):
    sel = [c for c in cases if c["group"] != "Not selected" and c["type"] == "Automated"]
    output = []
    for suite in ("web", "api", "mobile"):
        by_us = {}
        for c in sel:
            if c["suite"] == suite:
                by_us.setdefault(c["story"], []).append(c["id"])
        if not by_us:
            continue
        parts = []
        for us, tcs in sorted(by_us.items()):
            tcs = sorted(set(tcs))
            inner = " or ".join(f"@{x}" for x in tcs)
            parts.append(f"(@{us} and ({inner}))" if len(tcs) > 1 else f"(@{us} and @{tcs[0]})")
        tags = " or ".join(parts)
        output.append({"suite": suite, "tags": tags, "cases": sum(len(set(v)) for v in by_us.values()),
                       "bash": f'TAGS="{tags}" npm test -- {suite}', "powershell": f'$env:TAGS="{tags}"; npm test -- {suite}'})
    return output


def summarize(cases, no_coverage):
    sel = [c for c in cases if c["group"] != "Not selected"]
    total_min = sum(c["minutes"] for c in cases)
    sel_min = sum(c["minutes"] for c in sel)
    return {"cases": len(cases), "selected": len(sel), "by_group": {g: sum(1 for c in cases if c["group"] == g) for g in GROUPS},
            "automated": sum(1 for c in sel if c["type"] == "Automated"), "manual": sum(1 for c in sel if c["type"] == "Manual"),
            "selection_minutes": round(sel_min, 1), "total_minutes": round(total_min, 1),
            "savings_pct": round((1 - sel_min / total_min) * 100) if total_min else 0,
            "stories": len({c["story"] for c in cases}), "selected_stories": len({c["story"] for c in sel}),
            "no_coverage": len(no_coverage)}


def write(folder, data):
    data["summary"] = summarize(data["cases"], data["no_coverage"])
    data["commands"] = commands(data["cases"])
    (folder / "selection.json").write_text(json.dumps(data, ensure_ascii=False, indent=2, default=list), encoding="utf-8")
    with open(folder / "selection.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Group", "Story", "ID", "Title", "Type", "Suite", "Priority", "Score", "Minutes", "Latest result", "Why"])
        order = {g: i for i, g in enumerate(GROUPS)}
        for c in sorted(data["cases"], key=lambda c: (order[c["group"]], -c["score"])):
            if c["group"] == "Not selected":
                continue
            w.writerow([c["group"], c["story"], c["id"], c["title"], c["type"], c["suite"] or "", c["priority"] or "Medium", c["score"],
                        c["minutes"], (c["result"] or {}).get("status", ""), " · ".join(c["reasons"])])


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Test case selection for a change")
    ap.add_argument("--git", help="commit range (main..branch, v2.3..v2.4, HEAD~3..HEAD)")
    ap.add_argument("--repo", help="application repository (by default, the current one)")
    ap.add_argument("--files", help="changed files, separated by commas")
    ap.add_argument("--stories", help="affected stories or keys, separated by commas")
    ap.add_argument("--text", help="release notes or description of the change")
    ap.add_argument("--text-file", help="file with the notes or the description")
    ap.add_argument("--changes", help="changes.json built by the agent")
    ap.add_argument("--budget-min", type=float, help="maximum time of the selection, in minutes")
    ap.add_argument("--min-per-step", type=float, default=1.5, help="minutes per step of a manual case (estimate)")
    ap.add_argument("--name", help="name of the selection (output folder)")
    ap.add_argument("--analysis", help="the agent's analysis.json (by default, the one in the folder if it exists)")
    ap.add_argument("--report-only", action="store_true", help="applies the analysis and regenerates the report without recalculating")
    ap.add_argument("--output", help="folder (by default output/case-selection/<name>)")
    a = ap.parse_args()

    name = a.name or (re.sub(r"[^\w.-]+", "_", a.git).strip("_") if a.git else f'change-{datetime.date.today().isoformat()}')
    folder = Path(a.output) if a.output else ROOT / "output" / "case-selection" / name
    analysis_file = Path(a.analysis) if a.analysis else folder / "analysis.json"
    if a.report_only:
        data = json.loads((folder / "selection.json").read_text(encoding="utf-8"))
    else:
        if not any([a.git, a.files, a.stories, a.text, a.text_file, a.changes]):
            sys.exit("Tell me what changed: --git, --files, --stories, --text, --text-file or --changes.")
        change = read_change(a)
        cases = inventory()
        if not cases:
            sys.exit("I found no test cases (neither manual, nor BDD, nor automated in k0lmena): generate them first.")
        affected, no_coverage, weights = select(change, cases, a.budget_min, a.min_per_step)
        for c in cases:
            c["tags"] = sorted(c["tags"])
            c.pop("text", None)
        # The previous selection with the same name moves to history/<date>/ (the last 5 are kept).
        _history.archive(folder, ["selection.json", "selection.csv", "selection-report.html", "analysis.json", "changes.json"], "selection.json")
        folder.mkdir(parents=True, exist_ok=True)
        order = {g: i for i, g in enumerate(GROUPS)}
        cases.sort(key=lambda c: (order[c["group"]], -c["score"], c["story"], c["id"]))
        data = {"name": name, "date": datetime.datetime.now().isoformat(timespec="seconds"), "budget_min": a.budget_min,
                "change": {"title": change["title"], "sources": change["sources"], "files": change["files"], "commits": change["commits"],
                           "functions": change["functions"][:30], "stories": sorted(change["stories"]), "keys": sorted(change["keys"]),
                           "text": change["text"][:3000], "words": [{"word": t, "weight": round(p, 2)} for t, p in weights.most_common(25)]},
                "affected_stories": sorted(affected), "no_coverage": no_coverage, "cases": cases}
    analysis = json.loads(analysis_file.read_text(encoding="utf-8")) if analysis_file.exists() else {}
    if analysis:
        apply_adjustments(data["cases"], analysis)
    write(folder, data)
    r = data["summary"]
    where = folder.resolve()
    where = where.relative_to(ROOT).as_posix() if where.is_relative_to(ROOT) else str(where)
    print(f'Cases: {r["cases"]} · selected: {r["selected"]} ({r["automated"]} automated, {r["manual"]} manual) · '
          f'{r["selection_minutes"]} of {r["total_minutes"]} min (savings {r["savings_pct"]} %)')
    for g in GROUPS:
        print(f'  {g}: {r["by_group"][g]}')
    if data["no_coverage"]:
        print(f'Changes without cases: {len(data["no_coverage"])}')
    for c in data["commands"]:
        print(f'  {c["suite"]}: {c["bash"]}')
    args = [sys.executable, str(ROOT / "scripts" / "generate_selection_report.py"), str(folder / "selection.json"), str(folder / "selection-report.html")]
    if analysis_file.exists():
        args += ["--analysis", str(analysis_file)]
    res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    print(res.stdout.strip() or res.stderr.strip())
    print(f"Data: {where}/selection.json · spreadsheet: {where}/selection.csv")


if __name__ == "__main__":
    main()
