---
name: image-quality
description: The "how" of evaluating a camera's image quality — what OpenCV measures (brightness for black frames, Laplacian variance for blur, difference between captures for freezing, difference against a reference for a moved camera), with which thresholds, and what to judge with vision (dirty or obstructed lens, shifted framing, backlight, night IR). Used by the image-quality-analyst agent.
---

# Camera image quality

A guide for evaluating **how a camera looks**, combining OpenCV metrics (the objective part) with your judgment looking at the capture (the judgment part). The `tools/streaming/image_quality.py` tool leaves the capture in `screenshots/` and the metrics in `quality.json`.

## The objective part (OpenCV, already computed)

- **Mean brightness** of the grayscale image. Below ~15 the image is practically **black** (camera covered, no signal, no IR at night).
- **Sharpness** = Laplacian variance. Below ~100 it is **blurry** (dirty lens, out of focus, or fog). It's relative to the scene: a plain wall gives low variance without being blurry, which is why you confirm it by eye.
- **Freezing**: mean difference between two captures taken N seconds apart (`--freeze`). Almost zero = **frozen image** (the stream doesn't advance even though it "plays").
- **Moved camera**: mean difference against a **reference** (`--reference`). High = the framing changed (someone moved it) or the scene changed a lot. It fits the idea of `pixel-perfect`: compare against a reference and report how much changed.

Thresholds in the runner: `BLACK_BRIGHTNESS=15`, `MIN_BLUR=100`, `FREEZE_DIFF=1.0`, `MOVED_DIFF=25`. They are a starting point; if the person defines others for the type of scene, those win.

## The judgment part (you, with vision)

Look at the capture and evaluate what a metric doesn't distinguish well:

- **Obstructed or dirty lens**: smudges, drops, cobwebs, something covering part of the frame.
- **Camera moved from the reference framing**: it points somewhere else, it shifted or rotated.
- **Backlight**: a window or a light washes out part of the image and the important part can't be seen.
- **Night IR mode**: at night it should look black and white with IR; if it's dark or in noisy color, the IR didn't switch. **Careful**: a "dark" night image with correct IR is **not** a defect — don't flag it just for low brightness.

## How to decide

- An automatic finding (black, blur, freezing) is a **candidate**: confirm it with the capture. Discard what's expected (plain scene, night with IR).
- Without a **reference** or without knowing how it should look (day/night, framing), whatever you can't assert goes in as `Missing info`, not as a defect.

## Severity

- **Critical**: no image could be captured from the camera.
- **High**: black, blurry or frozen image (confirmed).
- **Medium**: camera moved relative to the reference; backlight that prevents seeing the important part.
- **Low**: IR that doesn't switch (if some noise is expected), slight dirt.
