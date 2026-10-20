#!/usr/bin/env python3
"""
Camera image quality: takes one screenshot per source and evaluates it with OpenCV
(black frames, blur and freeze) for the objective problems. The ones that need
judgment (blocked or dirty lens, camera moved off its framing, backlight, IR that does not switch
at night) are judged by the image-quality-analyst agent by looking at the screenshot this leaves. Optionally
compares against a reference to detect that the camera moved.

Usage (from the repo root):
    python tools/streaming/image_quality.py --source rtsp://cam.local/stream [--story US-001]
        [--reference ref.jpg] [--freeze 2] [--confirm]
    (--source accepts several, comma-separated; each can be an RTSP/HTTP stream or an image file)

What it does (read-only):
- Checks that each source is authorized in the .env (STREAMING_AUTHORIZED_SOURCES).
- Takes a screenshot (ffmpeg if it is a stream; uses the file if it is an image).
- OpenCV: mean brightness (black), variance of the Laplacian (blur) and, with --freeze N, compares two
  screenshots taken N seconds apart (freeze).
- --reference: compares against a reference image and estimates how much it changed (camera moved).
- Leaves in output/streaming/quality-<host or story>/: quality.json, quality-report.html and
  screenshots/ with each image (for the agent's vision review).

Requires ffmpeg (to capture from a stream) and opencv-python-headless (installed automatically if missing).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

BLACK_BRIGHTNESS = 15.0     # below this, the image is practically black
MIN_BLUR = 100.0     # variance of the Laplacian; below this, out of focus
FREEZE_DIFF = 1.0        # mean difference between two screenshots; below this, frozen
MOVED_DIFF = 25.0       # mean difference against the reference; above this, the camera moved/changed


def fail(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def _need(pkg, install):
    try:
        __import__(pkg)
        return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", install, "--quiet"], check=False)
    try:
        __import__(pkg)
    except ImportError:
        fail(f"\n[!] The '{install}' library is missing and could not be installed automatically.\n    Install it with:  pip install {install}\n")


def read_env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith("STREAMING_")})
    return values


def authorized(source, env):
    if Path(source).exists():
        return  # local image file: not a network source
    allowed = [u.strip().rstrip("/") for u in re.split(r"[,\s]+", env.get("STREAMING_AUTHORIZED_SOURCES", "")) if u.strip()]
    if not allowed:
        fail("There are no authorized sources. Add STREAMING_AUTHORIZED_SOURCES to the root .env "
             "(only devices or streams you own or have written authorization for).")
    f = source.rstrip("/")
    if not any(f == a or f.startswith(a) for a in allowed):
        fail(f"{source} is not in STREAMING_AUTHORIZED_SOURCES in the .env. Only authorized sources are tested.")


def is_stream(source):
    return urlparse(source).scheme.lower() in ("rtsp", "http", "https", "rtmp", "rtmps")


def capture(source, dest, timeout_s=30):
    """Leaves an image at `dest`. If the source is a file, copies it; if it is a stream, uses ffmpeg."""
    if Path(source).exists():
        shutil.copyfile(source, dest)
        return True
    if not shutil.which("ffmpeg"):
        fail("Cannot find ffmpeg (it is needed to capture from a stream). https://ffmpeg.org/download.html")
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if urlparse(source).scheme.lower() == "rtsp":
        cmd += ["-rtsp_transport", "tcp"]
    cmd += ["-i", source, "-frames:v", "1", "-q:v", "2", str(dest)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and Path(dest).exists()


def evaluate(cv2, np, img_path):
    img = cv2.imread(str(img_path))
    if img is None:
        return {"error": "Could not read the captured image."}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    brightness = float(gray.mean())
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    h, w = gray.shape[:2]
    return {"width": w, "height": h, "brightness": round(brightness, 1), "sharpness": round(blur, 1)}


def difference(cv2, np, a, b):
    """Mean brightness difference between two images (resizes the second to the first)."""
    ia, ib = cv2.imread(str(a)), cv2.imread(str(b))
    if ia is None or ib is None:
        return None
    ga = cv2.cvtColor(ia, cv2.COLOR_BGR2GRAY)
    gb = cv2.cvtColor(ib, cv2.COLOR_BGR2GRAY)
    if ga.shape != gb.shape:
        gb = cv2.resize(gb, (ga.shape[1], ga.shape[0]))
    return round(float(np.abs(ga.astype("float") - gb.astype("float")).mean()), 2)


def analyze_source(cv2, np, source, folder, freeze_s, reference):
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", urlparse(source).hostname or Path(source).stem or "cam").strip("-")
    screenshots = folder / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    img1 = screenshots / f"{slug}.jpg"

    rec = {"source": source, "screenshot": f"screenshots/{img1.name}", "findings": []}
    h = rec["findings"]
    if not capture(source, img1):
        rec["status"] = "failed"
        h.append({"severity": "Critical", "text": "Could not capture an image from the source."})
        return rec

    m = evaluate(cv2, np, img1)
    if "error" in m:
        rec["status"] = "failed"
        h.append({"severity": "Critical", "text": m["error"]})
        return rec
    rec["metrics"] = m

    if m["brightness"] < BLACK_BRIGHTNESS:
        h.append({"severity": "High", "text": f"Image practically black (brightness {m['brightness']})."})
    if m["sharpness"] < MIN_BLUR:
        h.append({"severity": "High", "text": f"Image out of focus (sharpness {m['sharpness']} < {MIN_BLUR}). It may be a dirty lens or out of focus."})

    # Freeze: second screenshot N seconds later
    if freeze_s and is_stream(source):
        time.sleep(freeze_s)
        img2 = screenshots / f"{slug}-2.jpg"
        if capture(source, img2):
            d = difference(cv2, np, img1, img2)
            rec["metrics"]["freeze_diff"] = d
            if d is not None and d < FREEZE_DIFF:
                h.append({"severity": "High", "text": f"Frozen image: almost no change in {freeze_s}s (difference {d})."})

    # Reference: did the camera move?
    if reference and Path(reference).exists():
        d = difference(cv2, np, reference, img1)
        rec["metrics"]["reference_diff"] = d
        if d is not None and d > MOVED_DIFF:
            h.append({"severity": "Medium", "text": f"The image differs considerably from the reference (difference {d}): the camera may have moved or the scene changed."})

    rec["status"] = "failed" if any(x["severity"] == "Critical" for x in h) else ("findings" if h else "ok")
    # Note for the agent's vision review
    rec["review_with_vision"] = ["blocked or dirty lens", "camera moved off its framing", "backlight", "night IR mode"]
    return rec


def main():
    ap = argparse.ArgumentParser(description="Camera image quality with OpenCV.")
    ap.add_argument("--source", required=True, help="RTSP/HTTP or image file (several, comma-separated).")
    ap.add_argument("--story", default="", help="US-XXX for traceability and the output folder.")
    ap.add_argument("--freeze", type=int, default=2, help="Seconds between two screenshots to detect a freeze (0 = off).")
    ap.add_argument("--reference", default=None, help="Reference image to detect that the camera moved.")
    ap.add_argument("--confirm", action="store_true", help="Skips the confirmation.")
    args = ap.parse_args()

    env = read_env()
    sources = [f.strip() for f in args.source.split(",") if f.strip()]
    for f in sources:
        authorized(f, env)
    _need("cv2", "opencv-python-headless")
    _need("numpy", "numpy")
    import cv2
    import numpy as np

    if not args.confirm:
        print("You are about to capture and evaluate an image from these sources (read-only):")
        for f in sources:
            print(f"  - {f}")
        if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
            fail("Cancelled.", 1)

    host = urlparse(sources[0]).hostname or "cameras"
    folder = ROOT / "output" / "streaming" / f"quality-{args.story or host}"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, ["quality.json", "quality-report.html"], "quality.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)

    results = []
    for f in sources:
        print(f"[quality] {f} …", file=sys.stderr)
        results.append(analyze_source(cv2, np, f, folder, args.freeze, args.reference))

    data = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "story": args.story or None,
        "sources": results,
        "summary": {"total": len(results),
                    "ok": sum(1 for r in results if r["status"] == "ok"),
                    "with_findings": sum(1 for r in results if r["status"] == "findings"),
                    "failed": sum(1 for r in results if r["status"] == "failed")},
    }
    (folder / "quality.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import generate_quality_report
        generate_quality_report.generate(folder / "quality.json", folder / "quality-report.html")
        print(f"[quality] Report: {folder / 'quality-report.html'}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)

    r = data["summary"]
    print(f"[quality] Done: {r['total']} · {r['ok']} ok · {r['with_findings']} with findings · {r['failed']} failed.")
    print(f"[quality] Data: {folder / 'quality.json'}")


if __name__ == "__main__":
    main()
