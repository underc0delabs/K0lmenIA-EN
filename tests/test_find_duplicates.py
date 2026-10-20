"""Search for duplicate and related bugs (bug-triager agent)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import find_duplicates as fd  # noqa: E402

BUG_MD = """**ID:** `BUG-008`

**Title:** `[Checkout]` Card payment rejects valid cards

**Story:** `PROJ-12`

**Status:** Open

**Description:**
When paying with a valid Visa card, the checkout shows "Invalid card" and does not let you continue.

**Steps to reproduce:**
1. Add a product to the cart
2. Go to the checkout and pay with a card

**Actual Result:**
Shows "Invalid card".

**Expected Result:**
The payment is processed.
"""


def test_reads_template_report():
    bug = fd.read_bug_md(BUG_MD)
    assert bug["id"] == "BUG-008"
    assert bug["title"] == "[Checkout] Card payment rejects valid cards"
    assert bug["story"] == "PROJ-12" and bug["status"] == "Open"
    assert "Invalid card" in bug["actual_result"]


def test_loose_note_takes_first_line_as_title():
    bug = fd.read_bug_md("# The login does not respond\nWhen pressing Sign in nothing happens.", "login-observation")
    assert bug["id"] == "login-observation" and bug["title"] == "The login does not respond"


def test_classifies_duplicate_related_and_distinct_with_spanish_synonyms():
    bug = fd.read_bug_md(BUG_MD)
    candidates = [
        {"id": "PROJ-120", "title": "[Checkout] El pago con tarjeta válida es rechazado", "description": "Al pagar con una tarjeta Visa válida muestra \"Invalid card\"",
         "status": "Abierto", "source": "jira", "story": "PROJ-12"},
        {"id": "PROJ-121", "title": "The cart does not update the total when paying", "description": "checkout with coupon and card", "status": "Open", "source": "jira"},
        {"id": "PROJ-122", "title": "Logo cut off in the page footer", "description": "footer on mobile", "status": "Open", "source": "jira"},
    ]
    res = {c["id"]: c for c in fd.compare(bug, candidates)}
    assert res["PROJ-120"]["classification"] == fd.DUPLICATE
    assert any("same message" in m for m in res["PROJ-120"]["reasons"])
    assert res["PROJ-121"]["classification"] == fd.RELATED
    assert res["PROJ-122"]["classification"] == fd.DIFFERENT
    assert list(res)[0] == "PROJ-120"  # sorted by score


def test_closed_duplicate_is_possible_regression_and_not_compared_with_itself():
    bug = fd.read_bug_md(BUG_MD)
    closed = dict(fd.read_bug_md(BUG_MD), id="BUG-002", status="Resolved")
    res = fd.compare(bug, [closed, dict(bug)])
    assert [r["id"] for r in res] == ["BUG-002"]
    assert res[0]["possible_regression"]
    assert fd.verdict(res) == "Possible regression of a closed bug"
    assert fd.verdict([]) == "New"


def test_main_writes_json_and_md(tmp_path, capsys):
    bug = tmp_path / "BUG-008.md"
    bug.write_text(BUG_MD, encoding="utf-8")
    cand = tmp_path / "candidates.json"
    cand.write_text(json.dumps([{"id": "PROJ-120", "title": "[Checkout] Card payment rejects cards", "source": "jira",
                                 "description": "Shows \"Invalid card\" with a valid card"}]), encoding="utf-8")
    output = tmp_path / "out"
    assert fd.main(["--bug", str(bug), "--candidates", str(cand), "--no-local", "--output", str(output)]) == 0
    data = json.loads((output / "triage.json").read_text(encoding="utf-8"))
    assert data["bugs"][0]["verdict"] == "Probable duplicate"
    md = (output / "triage.md").read_text(encoding="utf-8")
    assert "PROJ-120" in md and "+====" in md
    assert "BUG-008: Probable duplicate" in capsys.readouterr().out


def test_batch_compares_bugs_with_each_other(tmp_path):
    (tmp_path / "BUG-001.md").write_text(BUG_MD.replace("BUG-008", "BUG-001"), encoding="utf-8")
    (tmp_path / "BUG-002.md").write_text(BUG_MD.replace("BUG-008", "BUG-002"), encoding="utf-8")
    output = tmp_path / "out"
    fd.main(["--batch", str(tmp_path), "--no-local", "--output", str(output), "--name", "batch"])
    data = json.loads((output / "triage.json").read_text(encoding="utf-8"))
    assert [b["matches"][0]["id"] for b in data["bugs"]] == ["BUG-002", "BUG-001"]
