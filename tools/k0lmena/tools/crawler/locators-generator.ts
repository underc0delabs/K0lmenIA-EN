import * as pomGenerator from "./locatorGenerator";
import { chromium } from "@playwright/test";
import fs from "fs";
import path from "path";
import dotenv from "dotenv";

dotenv.config();

async function run() {
  const inputUrl = process.argv[2] || process.env.BASEURL;
  if (!inputUrl) {
    console.error("Provide a URL as a parameter or set APP_URL in the .env.");
    process.exit(1);
  }

  const outputDir = path.join(__dirname, "output");
  if (!fs.existsSync(outputDir)) fs.mkdirSync(outputDir, { recursive: true });
  const outputFile = path.join(outputDir, "locators-output.ts");

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(inputUrl);

  // Interactive elements are considered: links with href, buttons, inputs, selects, textareas, 
  // and elements with role="link" (besides the a elements that have an href)
  const elements = await page.evaluate(() => {
    const selectorList = "a[href], button, input, select, textarea, [role='link']";
    const nodeList = document.querySelectorAll(selectorList);

    function getUniqueSelector(el: Element): string {
      let baseSelector = "";
      if (el.id) {
        baseSelector = `#${CSS.escape(el.id)}`;
      } else if (el.hasAttribute("data-testid")) {
        baseSelector = `[data-testid="${CSS.escape(el.getAttribute("data-testid") || "")}"]`;
      } else if (el.hasAttribute("aria-label")) {
        baseSelector = `[aria-label="${CSS.escape(el.getAttribute("aria-label") || "")}"]`;
      } else if (el.hasAttribute("role")) {
        baseSelector = `[role="${CSS.escape(el.getAttribute("role") || "")}"]`;
      } else if (el.className && el.className.trim() !== "") {
        const candidate = "." + el.className.trim().split(/\s+/).map(cls => CSS.escape(cls)).join(".");
        // We use the class-based selector only if it is unique.
        if (document.querySelectorAll(candidate).length === 1) {
          baseSelector = candidate;
        } else {
          baseSelector = el.tagName.toLowerCase();
        }
      } else {
        baseSelector = el.tagName.toLowerCase();
      }
      // If the resulting selector matches more than one element, :nth-of-type() is added
      const matchingNodes = document.querySelectorAll(baseSelector);
      if (matchingNodes.length > 1 && el.parentElement) {
        const siblings = el.parentElement.querySelectorAll(el.tagName.toLowerCase());
        const index = Array.from(siblings).indexOf(el) + 1;
        return baseSelector + `:nth-of-type(${index})`;
      }
      return baseSelector;
    }

    return Array.from(nodeList).map(el => {
      const text = el.textContent ? el.textContent.trim() : "";
      return {
        tag: el.tagName.toLowerCase(),
        text: text,
        selector: getUniqueSelector(el)
      };
    });
  });

  await browser.close();

  const pageName = new URL(inputUrl).hostname;
  pomGenerator.generatePOM(elements, outputFile, pageName);
  console.log("POM generated successfully.");
}

run();
