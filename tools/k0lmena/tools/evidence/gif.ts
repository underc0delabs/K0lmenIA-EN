// tools/evidence/gif.ts
//
// Evidence for passing scenarios (web and mobile).
//   EVIDENCE=screenshot -> final screenshot (default)
//   EVIDENCE=both       -> final screenshot + GIF of the walkthrough (one screenshot per step)
//   EVIDENCE=off        -> nothing
// If EVIDENCE is not set, `npm test` asks for it at startup (see run-tests.js).

// gifenc and pngjs are plain JavaScript (no binaries); they are loaded with require because they ship no types.
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { GIFEncoder, quantize, applyPalette } = require('gifenc');
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { PNG } = require('pngjs');

export type EvidenceMode = 'off' | 'screenshot' | 'both';

export function evidenceMode(): EvidenceMode {
  const raw = (process.env.EVIDENCE ?? 'screenshot').trim().toLowerCase();
  if (['off', '0', 'false', 'no'].includes(raw)) return 'off';
  if (['both', 'gif', 'screenshot+gif'].includes(raw)) return 'both';
  return 'screenshot'; // screenshot | on | 1 | true | empty
}

/** Shrinks a decoded PNG to `width` px (nearest neighbor: fast and good enough for a GIF). */
function shrink(png: { width: number; height: number; data: Buffer }, width: number) {
  if (png.width <= width) return png;
  const height = Math.round((png.height * width) / png.width);
  const data = Buffer.alloc(width * height * 4);
  for (let y = 0; y < height; y++) {
    const sy = Math.floor((y * png.height) / height);
    for (let x = 0; x < width; x++) {
      const sx = Math.floor((x * png.width) / width);
      png.data.copy(data, (y * width + x) * 4, (sy * png.width + sx) * 4, (sy * png.width + sx) * 4 + 4);
    }
  }
  return { width, height, data };
}

/**
 * Builds an animated GIF from the screenshots (PNG) of each step.
 * Frames are shrunk to `width` px; the last one stays on screen twice as long.
 */
export function createGif(screenshots: Buffer[], options: { width?: number; msPerStep?: number } = {}): Buffer | null {
  const { width = 800, msPerStep = 1000 } = options;
  if (screenshots.length === 0) return null;
  const gif = GIFEncoder();
  let base: { width: number; height: number } | null = null;
  screenshots.forEach((screenshot, i) => {
    const frame = shrink(PNG.sync.read(screenshot), width);
    // A frame with a different size (e.g. the screen rotated) doesn't fit in the same GIF: it is discarded.
    if (base && (frame.width !== base.width || frame.height !== base.height)) return;
    base = base ?? { width: frame.width, height: frame.height };
    const palette = quantize(frame.data, 256);
    gif.writeFrame(applyPalette(frame.data, palette), frame.width, frame.height, {
      palette,
      delay: i === screenshots.length - 1 ? msPerStep * 2 : msPerStep,
    });
  });
  gif.finish();
  return Buffer.from(gif.bytes());
}

/** HTML attachment that shows the GIF in the report (the report doesn't render image/gif as an image). */
export function htmlGif(src: string, title: string): string {
  return `<p><strong>${title}</strong></p><img src="${src}" style="max-width:100%" alt="${title}">` +
    `<p><a href="${src}" download>Download GIF</a></p>`;
}
