"use strict";
// HTML report of the API suite (npm run report:api), with the k0lmenIA dark theme.
// multiple-cucumber-html-reporter v4 is ESM only: it is loaded with a dynamic import().
const os = require("os");
const path = require("path");
const { reportOptions, applyTheme, waitForHtml, safeUrl } = require("../dark-theme");

const DIR = path.resolve(__dirname);

(async () => {
  const reporter = await import("multiple-cucumber-html-reporter");
  await reporter.generate({
    ...reportOptions("API"),
    jsonDir: DIR, // Directory where the cucumber-report.json file is
    reportPath: DIR, // Folder where the HTML report will be generated
    metadata: {
      browser: { name: "API (axios)", version: "-" },
      device: os.hostname(),
      platform: { name: os.platform(), version: os.release() },
    },
    customData: {
      Project: "k0lmena · API",
      "Run at": new Date().toLocaleString("en-US"),
      "Base URL": safeUrl(process.env.API_BASEURL),
    },
  });
  if (!(await waitForHtml(DIR))) console.error('[k0lmena] Note: the reporter did not finish writing index.html in time; the theme was applied to what was there.');
  console.log(`[k0lmena] API report with dark theme (${applyTheme(DIR)} pages).`);
})().catch((e) => {
  console.error("[k0lmena] Could not generate the API report:", e);

  process.exitCode = 1;
});
