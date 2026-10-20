// Shared visual comparison (used by pixel-perfect and cross-browser).
//
//   stabilize(page, { hide })        → turns off animations, transitions and the text cursor, hides
//                                     the dynamic areas and waits for fonts and images: two screenshots
//                                     of the same page must come out identical.
//   measureElements(page)            → box (position and size on the page) of every visible element
//                                     that matters: headings, links, buttons, fields, images, etc.
//   compareElements(ref, act)     → which elements shifted, changed size, are missing or are
//                                     new (groups the ones that moved together into a "block").
//   comparePng(a, b)               → different pixels, percent, regions with changes and the
//                                     diff image (the changes in red over the actual one).
//   crop(png, box)                  → a piece of the image (to show each region up close).
//
// Only uses pngjs (no native dependencies).
// pngjs is loaded only when comparing images (the element comparison does not need it).
const png = () => require('pngjs').PNG;

// ------------------------------------------------------------------ stabilize the page
const CSS_STABLE = `*,*::before,*::after{animation-duration:0s!important;animation-delay:0s!important;
  animation-iteration-count:1!important;transition:none!important;caret-color:transparent!important;scroll-behavior:auto!important}
  [data-k0-hidden]{visibility:hidden!important}`;

// No scrollbars: Firefox (and WebKit on some systems) draws them taking up width and headless
// Chromium does not; with a scrollbar the page is narrower, text wraps differently and everything looks shifted.
// Used by cross-browser when comparing engines (pixel-perfect compares the same browser).
const CSS_NO_SCROLLBAR = `html{scrollbar-width:none!important}html::-webkit-scrollbar,body::-webkit-scrollbar{display:none!important}`;

async function stabilize(page, { hide = [], waitMs = 400 } = {}) {
  await page.addStyleTag({ content: CSS_STABLE }).catch(() => {});
  await page.evaluate(async (sels) => {
    for (const s of sels) {
      try { document.querySelectorAll(s).forEach((el) => el.setAttribute('data-k0-hidden', '')); } catch { /* invalid selector */ }
    }
    // Videos and animated GIFs: first frame.
    document.querySelectorAll('video').forEach((v) => { try { v.pause(); v.currentTime = 0; } catch { /* no video */ } });
    const limit = (p, ms) => Promise.race([p, new Promise((r) => setTimeout(r, ms))]);
    if (document.fonts && document.fonts.ready) await limit(document.fonts.ready, 5000);
    const pending = [...document.images].filter((i) => !i.complete)
      .map((i) => new Promise((r) => { i.addEventListener('load', r, { once: true }); i.addEventListener('error', r, { once: true }); }));
    await limit(Promise.all(pending), 5000);
  }, hide).catch(() => {});
  await page.waitForTimeout(waitMs);
}

// ------------------------------------------------------------------ element boxes
// Each element carries a key that is stable across runs (and across browsers): id or data-testid if
// it has one; otherwise tag + text + occurrence number of that combination.
function _measureInPage() {
  const SEL = 'h1,h2,h3,h4,h5,h6,a[href],button,input:not([type=hidden]),select,textarea,label,img,svg,video,iframe,' +
    'nav,header,footer,main,aside,form,table,li,p,[role=button],[role=link],[role=tab],[role=dialog],[role=alert],[data-testid]';
  const CONTAINERS = new Set(['nav', 'header', 'footer', 'main', 'aside', 'form', 'table', 'svg', 'video', 'iframe']);
  const sx = window.scrollX;
  const sy = window.scrollY;
  const seen = new Map();
  const output = [];
  const textOf = (el) => (el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('placeholder') ||
    (el.tagName === 'INPUT' ? el.value : '') || el.innerText || el.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  // Besides SEL: div, span and section with their own text (a banner or a notice without a semantic tag).
  const withText = [...document.querySelectorAll('div,span,section,strong,em,small')].filter((el) =>
    [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 2));
  const list = [...new Set([...document.querySelectorAll(SEL), ...withText])];
  // The computed color comes in each engine's format (rgb(), oklch(), color(srgb …)): it is painted
  // on a canvas and the pixel is read back, so it ends up in sRGB the same in every browser.
  const canvas = document.createElement('canvas').getContext('2d', { willReadFrequently: true });
  const colors = new Map();
  const hex = (c) => {
    if (colors.has(c)) return colors.get(c);
    let result = 'transparent';
    if (canvas) {
      canvas.clearRect(0, 0, 1, 1);
      canvas.fillStyle = '#000';
      canvas.fillStyle = c;
      canvas.fillRect(0, 0, 1, 1);
      const [r, g, b, a] = canvas.getImageData(0, 0, 1, 1).data;
      if (a > 0) result = '#' + [r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('');
    } else {
      const m = c.match(/\d+(\.\d+)?/g);
      if (m && !(m.length === 4 && Number(m[3]) === 0)) result = '#' + m.slice(0, 3).map((x) => Math.round(Number(x)).toString(16).padStart(2, '0')).join('');
    }
    colors.set(c, result);
    return result;
  };
  for (const el of list) {
    if (output.length >= 800) break;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) continue;
    if (el.closest('[data-k0-hidden]')) continue;
    const tag = el.tagName.toLowerCase();
    const text = textOf(el).slice(0, 60);
    // A paragraph or li without its own text adds nothing (and large containers are measured anyway).
    if ((tag === 'p' || tag === 'li') && !text) continue;
    const testid = el.getAttribute('data-testid');
    let key;
    if (el.id && !/^\d|[:\s]/.test(el.id)) key = `#${el.id}`;
    else if (testid) key = `[data-testid=${testid}]`;
    else {
      // Containers are identified by their order (their text is everything inside and changes
      // with anything); the rest, by their text.
      const base = CONTAINERS.has(tag) ? `${tag}|` : `${tag}|${text.slice(0, 40)}`;
      const n = (seen.get(base) || 0) + 1;
      seen.set(base, n);
      key = `${base}|${n}`;
    }
    let desc = tag;
    if (el.id) desc += `#${el.id}`;
    const classes = (typeof el.className === 'string' ? el.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
    if (classes.length) desc += `.${classes.join('.')}`;
    output.push({ key, tag, text, desc, x: Math.round(r.left + sx), y: Math.round(r.top + sy),
      w: Math.round(r.width), h: Math.round(r.height),
      style: { background: hex(cs.backgroundColor), color: hex(cs.color), font_size: cs.fontSize, font_weight: cs.fontWeight } });
  }
  return { elements: output, width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight };
}

async function measureElements(page) {
  return page.evaluate(_measureInPage);
}

// Elements that matter more if they are missing or move (they are used).
const INTERACTIVE = new Set(['a', 'button', 'input', 'select', 'textarea', 'label']);

function movementSeverity(dist, tag) {
  const inter = INTERACTIVE.has(tag);
  if (dist >= 40) return inter ? 'High' : 'Medium';
  if (dist >= 12) return inter ? 'Medium' : 'Low';
  return 'Low';
}

// ref and act: lists of measureElements().elements. tolerance in px.
function compareElements(ref, act, { tolerance = 3, minBlock = 4 } = {}) {
  const actMap = new Map(act.map((e) => [e.key, e]));
  const refMap = new Map(ref.map((e) => [e.key, e]));
  const moved = [];
  const resized = [];
  const missing = [];
  for (const r of ref) {
    const a = actMap.get(r.key);
    if (!a) { missing.push(r); continue; }
    const dx = a.x - r.x;
    const dy = a.y - r.y;
    const dw = a.w - r.w;
    const dh = a.h - r.h;
    if (Math.abs(dx) > tolerance || Math.abs(dy) > tolerance) moved.push({ ...r, dx, dy, dw, dh, actual: a });
    else if (Math.abs(dw) > tolerance || Math.abs(dh) > tolerance) resized.push({ ...r, dx, dy, dw, dh, actual: a });
  }
  // Styles: the same change (from → to) in several elements is just one (all the buttons changed color).
  const PROP_NAME = { background: 'background color', color: 'text color', font_size: 'font size', font_weight: 'font weight' };
  const styles = new Map();
  for (const r of ref) {
    const a = actMap.get(r.key);
    if (!a || !r.style || !a.style) continue;
    for (const prop of Object.keys(PROP_NAME)) {
      if (r.style[prop] === a.style[prop]) continue;
      const k = `${prop}|${r.style[prop]}|${a.style[prop]}`;
      if (!styles.has(k)) styles.set(k, { prop, name: PROP_NAME[prop], from: r.style[prop], to: a.style[prop], elements: [] });
      styles.get(k).elements.push({ ...r, actual: a });
    }
  }
  let added = act.filter((a) => !refMap.has(a.key));
  // A missing one and a new one with the same tag in the same place: it is the same element with another
  // text (a button that was renamed), not one that disappeared.
  // Possible offsets: none, or the most common one among those that moved (if everything went down 40 px,
  // the element with another text also went down 40 px).
  const freq = new Map();
  for (const m of moved) { const k = `${m.dx}|${m.dy}`; freq.set(k, (freq.get(k) || 0) + 1); }
  const offs = [[0, 0], ...[...freq.entries()].sort((p, q) => q[1] - p[1]).slice(0, 3).map(([k]) => k.split('|').map(Number))];
  const near = (n, f) => offs.some(([ox, oy]) => Math.abs(n.x - f.x - ox) <= 30 && Math.abs(n.y - f.y - oy) <= 30);
  const changed = [];
  for (const f of [...missing]) {
    const pair = added.find((n) => n.tag === f.tag && near(n, f)
      && Math.abs(n.w - f.w) <= Math.max(40, f.w * 0.5) && Math.abs(n.h - f.h) <= Math.max(12, f.h * 0.5));
    if (!pair) continue;
    changed.push({ ...f, actual: pair });
    missing.splice(missing.indexOf(f), 1);
    added = added.filter((n) => n !== pair);
  }

  // Blocks: many elements with the same offset have a single cause (something above grew
  // or shifted and pushed everything below). The block is reported, not each element.
  const groups = new Map();
  for (const m of moved) {
    const k = `${Math.round(m.dx / 2) * 2}|${Math.round(m.dy / 2) * 2}`;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(m);
  }
  const blocks = [];
  const loose = [];
  for (const list of groups.values()) {
    if (list.length >= minBlock) {
      list.sort((a, b) => a.y - b.y || a.x - b.x);
      const x = Math.min(...list.map((e) => e.x));
      const y = Math.min(...list.map((e) => e.y));
      blocks.push({ dx: list[0].dx, dy: list[0].dy, elements: list.length,
        from: list.find((e) => !['main', 'nav', 'header', 'footer', 'aside', 'form', 'table', 'section', 'div'].includes(e.tag)) || list[0],
        box: { x, y, w: Math.max(...list.map((e) => e.x + e.w)) - x, h: Math.max(...list.map((e) => e.y + e.h)) - y },
        examples: list.slice(0, 6).map((e) => ({ desc: e.desc, text: e.text })) });
    } else loose.push(...list);
  }
  blocks.sort((a, b) => b.elements - a.elements);
  loose.sort((a, b) => Math.hypot(b.dx, b.dy) - Math.hypot(a.dx, a.dy));
  for (const m of loose) m.severity = movementSeverity(Math.hypot(m.dx, m.dy), m.tag);
  return { moved: loose, blocks, resized, missing, added, changed,
    styles: [...styles.values()].sort((p, q) => q.elements.length - p.elements.length), total_ref: ref.length, total_act: act.length };
}

// ------------------------------------------------------------------ pixel differences
// Color distance in YIQ (the same idea as pixelmatch): weighs it the way the eye perceives it.
const MAX_DELTA = 35215;
function _delta(a, i, b, j) {
  const ra = a[i]; const ga = a[i + 1]; const ba = a[i + 2];
  const rb = b[j]; const gb = b[j + 1]; const bb = b[j + 2];
  const y = (ra - rb) * 0.29889531 + (ga - gb) * 0.58662247 + (ba - bb) * 0.11448223;
  const iq = (ra - rb) * 0.59597799 - (ga - gb) * 0.2741761 - (ba - bb) * 0.32180189;
  const q = (ra - rb) * 0.21147017 - (ga - gb) * 0.52261711 + (ba - bb) * 0.31114694;
  return 0.5053 * y * y + 0.299 * iq * iq + 0.1957 * q * q;
}

function readPng(buf) {
  return png().sync.read(Buffer.isBuffer(buf) ? buf : require('fs').readFileSync(buf));
}

// Compares two PNGs (Buffer or path). threshold: 0..1, per-pixel sensitivity (0.1 = noticeable changes).
// If the images have different sizes, it compares the common part and counts the rest as changed.
function comparePng(bufA, bufB, { threshold = 0.1, cell = 16, minCellPixels = 6 } = {}) {
  const a = readPng(bufA);
  const b = readPng(bufB);
  const W = Math.max(a.width, b.width);
  const H = Math.max(a.height, b.height);
  const w = Math.min(a.width, b.width);
  const h = Math.min(a.height, b.height);
  const limit = MAX_DELTA * threshold * threshold;
  const output = new (png())({ width: W, height: H });
  const cols = Math.ceil(W / cell);
  const rows = Math.ceil(H / cell);
  const cells = new Uint32Array(cols * rows);
  let different = 0;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const o = (y * W + x) * 4;
      const inside = x < w && y < h;
      let change;
      let gray = 255;
      if (inside) {
        const ia = (y * a.width + x) * 4;
        const ib = (y * b.width + x) * 4;
        change = _delta(a.data, ia, b.data, ib) > limit;
        gray = 0.299 * b.data[ib] + 0.587 * b.data[ib + 1] + 0.114 * b.data[ib + 2];
      } else change = true;
      if (change) {
        different++;
        cells[Math.floor(y / cell) * cols + Math.floor(x / cell)]++;
        output.data[o] = 255; output.data[o + 1] = 32; output.data[o + 2] = 48; output.data[o + 3] = 255;
      } else {
        // The actual image, dimmed, in the background: the red changes are seen in context.
        const v = Math.round(255 - (255 - gray) * 0.22);
        output.data[o] = v; output.data[o + 1] = v; output.data[o + 2] = v; output.data[o + 3] = 255;
      }
    }
  }
  const regions = _regions(cells, cols, rows, cell, minCellPixels, W, H);
  return { width_a: a.width, height_a: a.height, width_b: b.width, height_b: b.height, different,
    pct: Math.round((different / (W * H)) * 10000) / 100, regions, diff: png().sync.write(output) };
}

// Cells with changes → regions (connected components, merged if they touch or overlap).
function _regions(cells, cols, rows, cell, minPix, W, H) {
  const mark = new Uint8Array(cols * rows);
  const boxes = [];
  for (let i = 0; i < cells.length; i++) {
    if (mark[i] || cells[i] < minPix) continue;
    const stack = [i];
    mark[i] = 1;
    let x0 = cols; let y0 = rows; let x1 = 0; let y1 = 0; let pix = 0;
    while (stack.length) {
      const k = stack.pop();
      const cx = k % cols;
      const cy = Math.floor(k / cols);
      pix += cells[k];
      x0 = Math.min(x0, cx); y0 = Math.min(y0, cy); x1 = Math.max(x1, cx); y1 = Math.max(y1, cy);
      // Neighbors within 2 cells: merges nearby changes (a text that shifted is one region, not ten).
      for (let dy = -2; dy <= 2; dy++) {
        for (let dx = -2; dx <= 2; dx++) {
          const nx = cx + dx;
          const ny = cy + dy;
          if (nx < 0 || ny < 0 || nx >= cols || ny >= rows) continue;
          const n = ny * cols + nx;
          if (!mark[n] && cells[n] >= minPix) { mark[n] = 1; stack.push(n); }
        }
      }
    }
    boxes.push({ x: x0 * cell, y: y0 * cell, w: Math.min(W, (x1 + 1) * cell) - x0 * cell, h: Math.min(H, (y1 + 1) * cell) - y0 * cell, pixels: pix });
  }
  boxes.sort((p, q) => q.pixels - p.pixels);
  return boxes;
}

// Crop (with margin) of a PNG; if the box goes outside the image, it fills with gray.
function crop(buf, { x, y, w, h }, margin = 24) {
  const img = readPng(buf);
  const X = Math.max(0, x - margin);
  const Y = Math.max(0, y - margin);
  const width = Math.max(1, Math.min(w + margin * 2, 1600));
  const height = Math.max(1, Math.min(h + margin * 2, 1200));
  const out = new (png())({ width, height });
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      const o = (j * width + i) * 4;
      const sx = X + i;
      const sy = Y + j;
      if (sx < img.width && sy < img.height) {
        const s = (sy * img.width + sx) * 4;
        out.data[o] = img.data[s]; out.data[o + 1] = img.data[s + 1]; out.data[o + 2] = img.data[s + 2]; out.data[o + 3] = 255;
      } else {
        out.data[o] = 40; out.data[o + 1] = 42; out.data[o + 2] = 48; out.data[o + 3] = 255;
      }
    }
  }
  return png().sync.write(out);
}

// Crop of the window `win` with the rectangle `box` (image coordinates) marked.
function markedCrop(buf, win, box, color = [255, 45, 45]) {
  const img = readPng(buf);
  const X = Math.max(0, Math.round(win.x));
  const Y = Math.max(0, Math.round(win.y));
  const width = Math.max(1, Math.min(Math.round(win.w), 1600));
  const height = Math.max(1, Math.min(Math.round(win.h), 1200));
  const out = new (png())({ width, height });
  const border = 3;
  for (let j = 0; j < height; j++) {
    for (let i = 0; i < width; i++) {
      const o = (j * width + i) * 4;
      const sx = X + i;
      const sy = Y + j;
      let r = 40; let g = 42; let b = 48;
      if (sx < img.width && sy < img.height) {
        const s = (sy * img.width + sx) * 4;
        r = img.data[s]; g = img.data[s + 1]; b = img.data[s + 2];
      }
      if (box) {
        const inX = sx >= box.x - border && sx < box.x + box.w + border;
        const inY = sy >= box.y - border && sy < box.y + box.h + border;
        const inside = sx >= box.x && sx < box.x + box.w && sy >= box.y && sy < box.y + box.h;
        if (inX && inY && !inside) { [r, g, b] = color; }
      }
      out.data[o] = r; out.data[o + 1] = g; out.data[o + 2] = b; out.data[o + 3] = 255;
    }
  }
  return png().sync.write(out);
}

// Window that contains the given boxes, with margin, of the minimum requested size.
function windowOf(boxes, margin = 60, minWidth = 320, minHeight = 160) {
  const x0 = Math.min(...boxes.map((c) => c.x)) - margin;
  const y0 = Math.min(...boxes.map((c) => c.y)) - margin;
  const x1 = Math.max(...boxes.map((c) => c.x + c.w)) + margin;
  const y1 = Math.max(...boxes.map((c) => c.y + c.h)) + margin;
  const w = Math.max(minWidth, x1 - x0);
  const h = Math.max(minHeight, y1 - y0);
  return { x: Math.max(0, Math.round((x0 + x1) / 2 - w / 2)), y: Math.max(0, Math.round((y0 + y1) / 2 - h / 2)), w, h };
}

// Size of a PNG without decoding it entirely.
function pngSize(buf) {
  const b = Buffer.isBuffer(buf) ? buf : require('fs').readFileSync(buf);
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
}

module.exports = { stabilize, measureElements, compareElements, comparePng, crop, markedCrop, windowOf, pngSize, movementSeverity,
  CSS_STABLE, CSS_NO_SCROLLBAR, _regions };
