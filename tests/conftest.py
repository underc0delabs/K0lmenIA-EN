"""Common setup for the k0lmenIA tests: the scripts are imported from scripts/ and scripts/management/."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "scripts", ROOT / "scripts" / "management"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# The reports built by the tests (also in subprocesses) do not touch the output/index.html portal.
import os  # noqa: E402

os.environ["K0LMENIA_PORTAL"] = "0"
