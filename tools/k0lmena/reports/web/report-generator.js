"use strict";

// multiple-cucumber-html-reporter v4 is ESM only: it is loaded with a dynamic import().
const loadReporter = () => import("multiple-cucumber-html-reporter");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { reportOptions, themeInHtml, waitForHtml, safeUrl } = require("../dark-theme");

/**
 * This script lives inside reports/web. With REPORT_DIR (the same one as cucumber.js) it builds the report
 * in that folder instead of reports/web.
 */
const REPORT_DIR = (process.env.REPORT_DIR || "").trim()
  ? path.resolve(__dirname, "../..", process.env.REPORT_DIR.trim())
  : path.resolve(__dirname);

(async function main() {
  // 1) Generate the report
  // The feature pages carry a per-run id: the old ones are deleted so they do not pile up.
  fs.rmSync(path.join(REPORT_DIR, "features"), { recursive: true, force: true });
  const report = await loadReporter();
  await report.generate({
    ...reportOptions("Web"),
    jsonDir: REPORT_DIR,
    reportPath: REPORT_DIR,
    metadata: {
      browser: { name: process.env.BROWSER || "chromium", version: "Playwright" },
      device: os.hostname(),
      platform: { name: os.platform(), version: os.release() },
    },
    customData: {
      Project: "k0lmena · Web",
      "Run at": new Date().toLocaleString("en-US"),
      "Base URL": safeUrl(process.env.BASEURL || process.env.APP_URL),
    },
  });

  // 2) Wait for index.html (front-report.html, Cucumber's own, is already in the folder)
  if (!(await waitForHtml(REPORT_DIR))) console.error("[k0lmena] Note: the reporter did not finish writing index.html in time; the theme was applied to what was there.");

  // 3) Apply patches to ALL the generated HTML files
  patchAllHtmlReports(REPORT_DIR);

  console.log(
    "[k0lmena] Web report generated with the k0lmenIA dark theme (trace links fixed)."
  );
})().catch((e) => {
  console.error("[k0lmena] Report generation/patch failed:", e);
  process.exitCode = 1;
});

/* ----------------------------- Patcher ----------------------------- */

function patchAllHtmlReports(rootDir) {
  const htmlFiles = collectFilesRecursive(rootDir, (p) =>
    p.toLowerCase().endsWith(".html")
  );

  for (const file of htmlFiles) {
    patchSingleHtml(file, rootDir);
  }
}

function patchSingleHtml(filePath, rootDir) {
  let html;
  try {
    html = fs.readFileSync(filePath, "utf8");
  } catch {
    return;
  }

  // Avoid double injection
  if (html.includes('id="k0lmena-theme"')) return;

  // ✅ FIX 1: Zip download (traces) - fixes relative paths in pages inside /features/
  html = fixRelativeTraceLinks(html, filePath, rootDir);

  // ✅ FIX 2: Labels (without touching styles)
  // They must end up like this:
  // + Show Error
  // + Show Info
  // + Download Zip
  // + Screenshot
  html = fixInfoAndZipLabels(html);

  // ✅ FIX 3: locked dark mode with the common k0lmenIA theme (reports/dark-theme.js)
  html = themeInHtml(html);

  try {
    fs.writeFileSync(filePath, html, "utf8");
  } catch {
    // noop
  }
}

/**
 * ✅ Fixes links like href="traces/file.zip" so they point correctly from subfolders (features/, etc.)
 */
function fixRelativeTraceLinks(html, filePath, rootDir) {
  try {
    const tracesDir = path.join(rootDir, "traces");
    let rel = path.relative(path.dirname(filePath), tracesDir);
    rel = rel.split(path.sep).join("/"); // web slashes
    if (!rel || rel.trim() === "") rel = "traces";
    rel = rel.replace(/\/+$/, "");

    // Rewrites ONLY when it starts with "traces/", "videos/" or "evidence/" (does not touch ../ that are already correct)
    const prefix = rel.replace(/traces$/, "");
    // Also inside escaped HTML attachments (data-attachment-content uses &#34; / &quot;).
    html = html.replace(
      /(href|src)=(["']|&#34;|&quot;)(traces|videos|evidence)\//gi,
      (_m, attr, q, dir) => `${attr}=${q}${prefix}${dir}/`
    );

    return html;
  } catch {
    return html;
  }
}

/**
 * ✅ DEFINITIVE FIX:
 * Patches ONLY inside <ul class="panel_toolbox">...</ul>.
 *
 * Rules:
 * 1) If an <a> is clearly a ZIP one (attributes with .zip / traces / downloadZip / trace), it is labeled "+ Download Zip".
 * 2) If the toolbox has the pattern Error -> Info -> Info -> Screenshot, the 3rd one is forced to "+ Download Zip".
 * 3) Any "Descargar Zip" / "download zip" is normalized to "Download Zip".
 * 4) CSS/structure is not touched, only text.
 */
function fixInfoAndZipLabels(html) {
  return html.replace(
    /<ul\b[^>]*class=(["'])[^"']*panel_toolbox[^"']*\1[^>]*>[\s\S]*?<\/ul>/gi,
    (ul) => patchPanelToolboxUl(ul)
  );
}

function patchPanelToolboxUl(ulHtml) {
  const anchorRe = /<a\b[^>]*>[\s\S]*?<\/a>/gi;

  const anchors = [];
  let m;
  while ((m = anchorRe.exec(ulHtml)) !== null) {
    anchors.push({
      start: m.index,
      end: anchorRe.lastIndex,
      html: m[0],
    });
  }

  if (anchors.length === 0) return ulHtml;

  // Utility: type by visible label
  const getPlain = (aHtml) =>
    aHtml
      .replace(/<[^>]*>/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();

  const getType = (aHtml) => {
    const p = getPlain(aHtml);
    if (p.includes("+ show error")) return "error";
    if (p.includes("+ screenshot")) return "screenshot";
    if (p.includes("+ download zip") || p.includes("+ descargar zip") || p.includes("+ downloadzip"))
      return "zip";
    if (p.includes("+ show info")) return "info";
    return "other";
  };

  const isZipCandidateByAttrs = (aHtml) => {
    const open = (aHtml.match(/^<a\b[^>]*>/i) || [""])[0].toLowerCase();
    return (
      open.includes(".zip") ||
      open.includes("traces/") ||
      open.includes("trace") || // key: many reports do not put .zip in href but do put "trace"/"downloadTrace"
      open.includes("downloadzip") ||
      open.includes("download-zip") ||
      open.includes("zip")
    );
  };

  // 1) First pass: normalizes ZIP by attributes, and normalizes "Descargar Zip" -> "Download Zip"
  let updated = ulHtml;
  for (let i = anchors.length - 1; i >= 0; i--) {
    const a = anchors[i].html;
    const type = getType(a);

    let newA = a;

    // Normalizes any "Descargar Zip" or "download zip" text to "Download Zip"
    if (/(\+\s*)(descargar\s*zip|download\s*zip|downloadzip)/i.test(newA)) {
      newA = replacePlusLabel(newA, "+ Download Zip");
    }

    // If by its attributes it looks like ZIP, force "Download Zip"
    if (isZipCandidateByAttrs(newA)) {
      // Even if it currently says Show Info
      if (/(\+\s*)(show\s*info|descargar\s*zip|download\s*zip|downloadzip)/i.test(getPlain(newA))) {
        newA = replacePlusLabel(newA, "+ Download Zip");
      }
    } else {
      // If it does NOT look like ZIP but ended up as "Download Zip", turn it back into Show Info (avoids false positives)
      if (type === "zip" && !isZipCandidateByAttrs(newA)) {
        newA = replacePlusLabel(newA, "+ Show Info");
      }
    }

    if (newA !== a) {
      updated = updated.slice(0, anchors[i].start) + newA + updated.slice(anchors[i].end);
    }
  }

  // Re-extracts anchors from the already updated HTML (because lengths changed)
  const anchors2 = [];
  anchorRe.lastIndex = 0;
  while ((m = anchorRe.exec(updated)) !== null) {
    anchors2.push({
      start: m.index,
      end: anchorRe.lastIndex,
      html: m[0],
      type: getType(m[0]),
    });
  }

  // 2) Definitive fallback by visual pattern:
  // Error -> Info -> Info -> Screenshot  => the 3rd one is ZIP
  if (anchors2.length >= 4) {
    for (let i = 0; i <= anchors2.length - 4; i++) {
      const a0 = anchors2[i];
      const a1 = anchors2[i + 1];
      const a2 = anchors2[i + 2];
      const a3 = anchors2[i + 3];

      const isPattern =
        a0.type === "error" &&
        a1.type === "info" &&
        a2.type === "info" &&
        a3.type === "screenshot";

      if (isPattern) {
        const target = anchors2[i + 2].html;
        const patched = replacePlusLabel(target, "+ Download Zip");

        if (patched !== target) {
          updated =
            updated.slice(0, anchors2[i + 2].start) +
            patched +
            updated.slice(anchors2[i + 2].end);
        }
        break; // one per toolbox is enough
      }
    }
  }

  return updated;
}

/**
 * Replaces ONLY the text of the "+ ..." label, keeping any inner HTML.
 */
function replacePlusLabel(aTagOrInner, desiredLabel) {
  const desiredNoPlus = desiredLabel.replace(/^\+\s*/i, "");

  // Replaces the label if it exists (Show Info / Download Zip / Descargar Zip)
  const re = /(\+\s*)(Show\s*Info|Descargar\s*Zip|Download\s*Zip|download\s*zip|downloadzip)/i;

  if (re.test(aTagOrInner)) {
    return aTagOrInner.replace(re, `$1${desiredNoPlus}`);
  }

  // If the label was not found but there is HTML: append at the end without breaking anything

  if (/<[^>]+>/.test(aTagOrInner)) {
    return `${aTagOrInner} ${desiredLabel}`;
  }

  return desiredLabel;
}

function collectFilesRecursive(dir, predicate) {
  const out = [];
  let entries = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }

  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);

    if (entry.isDirectory()) {
      out.push(...collectFilesRecursive(fullPath, predicate));
    } else if (entry.isFile()) {
      if (!predicate || predicate(fullPath)) out.push(fullPath);
    }
  }

  return out;
}
