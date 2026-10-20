// tools/debug/debugHook.ts
import { BeforeAll, AfterAll, BeforeStep } from '@cucumber/cucumber';
import { chromium, Browser, Page } from 'playwright';

const debugMode = ['1', 'true'].includes((process.env.CUCUMBER_DEBUG || '').toLowerCase());

let browser: Browser;
let page: Page;

BeforeAll(async function () {
  if (!debugMode) return;
  // Launch in headful mode for inspection
  browser = await chromium.launch({ headless: false });
  const context = await browser.newContext();
  page = await context.newPage();
  // Expose the page on the World so the steps can use it:
  (this as any).page = page;
});

BeforeStep(async function () {
  if (!debugMode) return;
  // Pause before each step to open the Playwright UI inspector
  await page.pause();
});

AfterAll(async function () {
  if (!debugMode) return;
  await browser.close();
});
