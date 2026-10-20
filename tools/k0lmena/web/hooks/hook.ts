"use strict";
import { config } from "dotenv";
config();
import {
  chromium,
  firefox,
  webkit,
  Browser,
  Page,
  BrowserContext,
} from "playwright";
import {
  BeforeAll,
  Before,
  After,
  AfterAll,
  AfterStep,
  Status,
  ITestCaseHookParameter,
  setDefaultTimeout,
} from "@cucumber/cucumber";
import * as fs from "fs";
import * as path from "path";
import { consumeHealingEvents, flushHealingHistory } from "../utils/autoHealing";
import { createGif, htmlGif, evidenceMode } from "../../tools/evidence/gif";
const { activeSession } = require("../../tools/login/session");

setDefaultTimeout(60 * 1000);

const nodeLogs: string[] = [];
const originalConsoleLog = console.log;
console.log = function (...args: any[]) {
  nodeLogs.push(args.map(String).join(" "));
  originalConsoleLog.apply(console, args);
};

let browsers: Browser[] = [];
let pages: Page[] = [];
let contexts: BrowserContext[] = [];

const pageLogs = new Map<Page, string[]>();
// Screenshots per step for the walkthrough GIF (only with EVIDENCE=both).
const pageFrames = new Map<Page, Buffer[]>();
const traceState = new Map<
  BrowserContext,
  { started: boolean; stopped: boolean }
>();

function sanitizeFilePart(value: string): string {
  return value
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 120);
}

function toPosix(p: string): string {
  return p.split(path.sep).join("/");
}

function boolFromEnv(name: string, defaultValue: boolean): boolean {
  const raw = (process.env[name] ?? String(defaultValue)).toLowerCase().trim();
  return !["0", "false", "no", "off"].includes(raw);
}

function intFromEnv(name: string, defaultValue: number): number {
  const raw = (process.env[name] ?? "").trim();
  // Empty or unset → the default value (Number("") is 0: without this, the viewport ended up at 0x0).
  if (!raw) return defaultValue;
  const n = Number(raw);
  return Number.isFinite(n) ? n : defaultValue;
}

function traceMode(): "off" | "on" | "on-failure" {
  const raw = (process.env.TRACE ?? "off").toLowerCase().trim();
  if (raw === "on") return "on";
  if (raw === "on-failure" || raw === "onfailure") return "on-failure";
  return "off";
}

// VIDEO env var: on-failure (default) -> keeps the video only if the scenario fails
//                on -> always keeps it | off -> does not record
function videoMode(): "off" | "on" | "on-failure" {
  const raw = (process.env.VIDEO ?? "on-failure").toLowerCase().trim();
  if (raw === "on") return "on";
  if (raw === "off") return "off";
  return "on-failure";
}

function getReportRootAbs(): string {
  const raw = (process.env.REPORT_DIR ?? "reports/web").trim();
  return path.isAbsolute(raw) ? raw : path.join(process.cwd(), raw);
}

async function ensureDirAbs(dirAbs: string): Promise<string> {
  if (!fs.existsSync(dirAbs)) fs.mkdirSync(dirAbs, { recursive: true });
  return dirAbs;
}

function getBrowserLabel(browser: Browser): string {
  const type = (browser as any)?._type?.name?.();
  if (typeof type === "string" && type.length > 0) return type;
  const name = (browser as any)?.browserType?.()?.name?.();
  if (typeof name === "string" && name.length > 0) return name;
  return "browser";
}

function resolveBrowserTypes(): any[] {
  const browserChoice = (process.env.BROWSER ?? "").toLowerCase().trim();
  const map: Record<string, any> = { chromium, firefox, webkit };
  if (browserChoice && map[browserChoice]) return [map[browserChoice]];
  return [chromium, firefox, webkit];
}

function scenarioNameFromWorld(world: any): string {
  return world?.pickle?.name || world?.scenario?.name || "scenario";
}

function attachPageListeners(page: Page) {
  const logs: string[] = [];
  pageLogs.set(page, logs);

  page.on("console", (msg) => {
    logs.push(`[browser console:${msg.type()}] ${msg.text()}`);
  });

  page.on("pageerror", (err) => {
    logs.push(`[pageerror] ${String(err)}`);
  });

  page.on("requestfailed", (req) => {
    const failure = req.failure();
    logs.push(
      `[requestfailed] ${req.method()} ${req.url()}${
        failure?.errorText ? ` -> ${failure.errorText}` : ""
      }`
    );
  });

  page.on("response", (res) => {
    if (res.status() >= 400) {
      logs.push(`[http ${res.status()}] ${res.request().method()} ${res.url()}`);
    }
  });

  page.on("crash", () => {
    logs.push("[crash] The page crashed.");
  });
}

async function startTracingIfEnabled(context: BrowserContext) {
  const mode = traceMode();
  if (mode === "off") return;
  await context.tracing.start({
    screenshots: true,
    snapshots: true,
    sources: true,
  });
  traceState.set(context, { started: true, stopped: false });
}

async function stopTracing(context: BrowserContext, savePath?: string) {
  const state = traceState.get(context);
  if (!state?.started || state.stopped) return;
  if (savePath) {
    await context.tracing.stop({ path: savePath }).catch(() => undefined);
  } else {
    await context.tracing.stop().catch(() => undefined);
  }
  state.stopped = true;
  traceState.set(context, state);
}

BeforeAll(async function () {
  const browserTypes = resolveBrowserTypes();
  const headless = boolFromEnv("HEADLESS", true);
  const slowMo = intFromEnv("SLOWMO", 0);

  for (const browserType of browserTypes) {
    const b = await browserType.launch({ headless, slowMo });
    browsers.push(b);
  }
});

// Session saved with npm run login (SESSION in the .env). It is resolved once per process, so the
// "file does not exist" warning is not repeated in every scenario.
let resolvedSession: string | null | undefined;
function activeSessionFile(): string | null {
  if (resolvedSession === undefined) {
    resolvedSession = activeSession(process.env.SESSION, (msg: string) => originalConsoleLog(`[session] ${msg}`));
  }
  return resolvedSession ?? null;
}

Before(async function (scenario: ITestCaseHookParameter) {
  nodeLogs.length = 0;

  for (const ctx of contexts) {
    await ctx.close().catch(() => undefined);
  }

  contexts.length = 0;
  pages.length = 0;
  pageLogs.clear();
  pageFrames.clear();
  traceState.clear();

  const viewport = {
    width: intFromEnv("VIEWPORT_WIDTH", 1366),
    height: intFromEnv("VIEWPORT_HEIGHT", 768),
  };

  const locale = (process.env.LOCALE ?? "en-US").trim();
  const timezoneId = (process.env.TIMEZONE ?? "America/New_York").trim();

  // @no-session scenarios (for example, the ones that test the login itself) start without a session.
  const noSession = (scenario?.pickle?.tags ?? []).some((t) => t.name === "@no-session");
  const storageState = noSession ? undefined : activeSessionFile() ?? undefined;

  for (const browser of browsers) {
    const recordVideo =
      videoMode() === "off"
        ? undefined
        : { dir: path.join(getReportRootAbs(), "videos", ".tmp"), size: viewport };
    const context = await browser.newContext({ viewport, locale, timezoneId, recordVideo, storageState });
    contexts.push(context);

    await startTracingIfEnabled(context);

    const page = await context.newPage();
    page.setDefaultTimeout(60 * 1000);
    page.setDefaultNavigationTimeout(60 * 1000);

    attachPageListeners(page);
    pages.push(page);
  }
});

AfterStep(async function ({ result, pickle }) {
  const healEvents = consumeHealingEvents();
  if (healEvents.length > 0) {
    const lines = healEvents
      .map((e) => {
        const note = e.note ? `\nNote: ${e.note}` : "";
        return `AUTO-HEALING\n- At: ${e.at}\n- Action: ${e.action}\n- Original: ${e.original}\n- Healed with: ${e.healedWith}${note}`;
      })
      .join("\n\n");
    await this.attach(lines, "text/plain");
  }

  if (evidenceMode() === "both" && result?.status === Status.PASSED) {
    for (const page of pages) {
      const frame = await page.screenshot().catch(() => undefined);
      if (frame) pageFrames.set(page, [...(pageFrames.get(page) ?? []), frame]);
    }
  }

  if (!result || result.status !== Status.FAILED) return;

  const reportRoot = getReportRootAbs();
  const screenshotsDir = await ensureDirAbs(path.join(reportRoot, "screenshots"));
  const tracesDir = await ensureDirAbs(path.join(reportRoot, "traces"));

  const scenarioName = sanitizeFilePart(pickle?.name || scenarioNameFromWorld(this as any));
  const timestamp = Date.now();

  for (let i = 0; i < pages.length; i++) {
    const page = pages[i];
    const browserLabel = getBrowserLabel(browsers[i] ?? (browsers[0] as any));

    const screenshot = await page
      .screenshot({ fullPage: true })
      .catch(() => undefined);

    if (screenshot) {
      const fileName = `screenshot-${scenarioName}-${browserLabel}-${timestamp}.png`;
      fs.writeFileSync(path.join(screenshotsDir, fileName), screenshot);
      await this.attach(screenshot, "image/png");
    }

    const url = page.url();
    const title = await page.title().catch(() => "");
    await this.attach(
      `PAGE ON FAILURE (${browserLabel})\n- URL: ${url}\n- Title: ${title}`,
      "text/plain"
    );

    // DOM at the moment of the failure: the automation-repairer looks there for the element the
    // locator didn't find (and proposes a new one) without running the scenario again.
    const html = await page.content().catch(() => undefined);
    if (html) {
      const domDir = await ensureDirAbs(path.join(reportRoot, "dom"));
      const domAbs = path.join(domDir, `dom-${scenarioName}-${browserLabel}-${timestamp}.html`);
      fs.writeFileSync(domAbs, html);
      await this.attach(`DOM: ${toPosix(path.relative(reportRoot, domAbs))}\n- URL: ${url}`, "text/plain");
    }

    const browserSideLogs = pageLogs.get(page) ?? [];
    if (browserSideLogs.length > 0) {
      await this.attach(
        `BROWSER LOGS (${browserLabel}): console, JS errors, failed requests and HTTP responses >= 400\n${browserSideLogs.join("\n")}`,
        "text/plain"
      );
    }
  }

  const mode = traceMode();
  if (mode === "on" || mode === "on-failure") {
    for (let i = 0; i < contexts.length; i++) {
      const ctx = contexts[i];
      const browserLabel = getBrowserLabel(browsers[i] ?? (browsers[0] as any));
      const traceAbs = path.join(
        tracesDir,
        `trace-${scenarioName}-${browserLabel}-${timestamp}.zip`
      );

      await stopTracing(ctx, traceAbs);

      const rel = toPosix(path.relative(reportRoot, traceAbs));
      await this.attach(`TRACE: ${rel}`, "text/plain");
      await this.attach(
        `<p><strong>Trace:</strong> <a href="${rel}" download>${path.basename(
          traceAbs
        )}</a></p>`,
        "text/html"
      );
    }
  }

  let errorDetails = "";
  if (result.message) {
    errorDetails += `ERROR\n${result.message}\n`;
  } else if (result.exception) {
    if (result.exception instanceof Error) {
      errorDetails += `Error Exception: ${result.exception.toString()}\n`;
      if ((result.exception as Error).stack) {
        errorDetails += `Stack Trace: ${(result.exception as Error).stack}\n`;
      }
    } else {
      errorDetails += `Error Exception: ${String(result.exception)}\n`;
    }
  }

  if (nodeLogs.length > 0) {
    errorDetails += `Node logs:\n${nodeLogs.join("\n")}\n`;
    nodeLogs.length = 0;
  }

  if (errorDetails) {
    await this.attach(errorDetails, "text/plain");
  }
});

After(async function (scenario: ITestCaseHookParameter) {
  const mode = traceMode();
  const failed = scenario?.result?.status === Status.FAILED;
  const reportRoot = getReportRootAbs();
  const scenarioName = sanitizeFilePart(scenario?.pickle?.name || scenarioNameFromWorld(this as any));
  const timestamp = Date.now();

  // Evidence for a passing scenario: final screenshot (one per test and browser) and,
  // with EVIDENCE=both, also the walkthrough GIF.
  const evidence = evidenceMode();
  if (!failed && evidence === "both") {
    const evidenceDir = await ensureDirAbs(path.join(reportRoot, "evidence"));
    for (let i = 0; i < pages.length; i++) {
      const browserLabel = getBrowserLabel(browsers[i] ?? (browsers[0] as any));
      const gif = createGif(pageFrames.get(pages[i]) ?? []);
      if (!gif) continue;
      const gifAbs = path.join(evidenceDir, `gif-${scenarioName}-${browserLabel}-${timestamp}.gif`);
      fs.writeFileSync(gifAbs, gif);
      await this.attach(
        htmlGif(toPosix(path.relative(reportRoot, gifAbs)), `Scenario walkthrough (${browserLabel})`),
        "text/html"
      );
    }
  }
  if (!failed && evidence !== "off") {
    const evidenceDir = await ensureDirAbs(path.join(reportRoot, "evidence"));
    for (let i = 0; i < pages.length; i++) {
      const browserLabel = getBrowserLabel(browsers[i] ?? (browsers[0] as any));
      const shot = await pages[i].screenshot({ fullPage: true }).catch(() => undefined);
      if (!shot) continue;
      fs.writeFileSync(
        path.join(evidenceDir, `ok-${scenarioName}-${browserLabel}-${timestamp}.png`),
        shot
      );
      await this.attach(shot, "image/png");
    }
  }

  // The video finishes writing when the context closes: we keep the references beforehand.
  const videos = pages.map((page) => page.video());

  if (mode === "on") {
    for (const ctx of contexts) await stopTracing(ctx, undefined);
  } else if (mode === "on-failure" && !failed) {
    for (const ctx of contexts) await stopTracing(ctx, undefined);
  }

  for (const ctx of contexts) {
    await ctx.close().catch(() => undefined);
  }

  // Full video of the run: kept if the scenario failed (or always with VIDEO=on).
  const keepVideo = videoMode() === "on" || (videoMode() === "on-failure" && failed);
  for (let i = 0; i < videos.length; i++) {
    const video = videos[i];
    if (!video) continue;
    if (keepVideo) {
      const browserLabel = getBrowserLabel(browsers[i] ?? (browsers[0] as any));
      const videosDir = await ensureDirAbs(path.join(reportRoot, "videos"));
      const videoAbs = path.join(videosDir, `video-${scenarioName}-${browserLabel}-${timestamp}.webm`);
      const saved = await video.saveAs(videoAbs).then(() => true).catch(() => false);
      if (saved) {
        const rel = toPosix(path.relative(reportRoot, videoAbs));
        await this.attach(
          `<p><strong>Run video (${browserLabel}):</strong></p>` +
            `<video controls preload="metadata" style="max-width:100%" src="${rel}"></video>` +
            `<p><a href="${rel}" download>${path.basename(videoAbs)}</a></p>`,
          "text/html"
        );
      }
    }
    await video.delete().catch(() => undefined);
  }

  contexts.length = 0;
  pages.length = 0;
  nodeLogs.length = 0;
  pageLogs.clear();
  pageFrames.clear();
  traceState.clear();
});

AfterAll(async function () {
  const closePromise = Promise.all(
    browsers.map((b) => b.close().catch(() => undefined))
  );
  const flushPromise = flushHealingHistory().catch(() => undefined);
  await Promise.all([closePromise, flushPromise]);
});

export { browsers, pages };
