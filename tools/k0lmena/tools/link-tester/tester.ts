import dotenv from 'dotenv';
dotenv.config();

import axios from 'axios';
import * as cheerio from 'cheerio';
import { URL } from 'url';
import pLimit from 'p-limit';
import fs from 'fs';
import path from 'path';

// Output directory configuration
const OUTPUT_DIR = path.resolve(__dirname);
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'output.txt');
const ERROR_LOG_FILE = path.join(OUTPUT_DIR, 'error_log.txt');

// Make sure the output directory exists
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

let outputLines: string[] = [];
function logLine(line: string) {
  console.log(line);
  outputLines.push(line);
}

// Concurrency
const PAGE_CONCURRENCY = 5;
const RESOURCE_CONCURRENCY = 20;
const limitResource = pLimit(RESOURCE_CONCURRENCY);

type ResourceType = 'link' | 'image';
interface Resource { url: string; type: ResourceType; }

// Helper to format a duration as hh:mm:ss
function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}h ${minutes}m ${seconds}s`;
}

// Fetches the HTML of a URL
async function fetchHTML(pageUrl: string): Promise<string> {
  try {
    const resp = await axios.get<string>(pageUrl, {
      responseType: 'text',
      headers: { 'User-Agent': 'k0lmena-link-tester/1.0' }
    });
    return resp.data;
  } catch (error: any) {
    // Log the fetch error with context
    const msg = `Error fetching HTML from ${pageUrl}\n` +
                `Status: ${error.response?.status || 'no response'}\n` +
                `Message: ${error.message}`;
    throw new Error(msg);
  }
}

// Extracts valid links and images to test
function extractResources(html: string, baseUrl: string): Resource[] {
  const $ = cheerio.load(html);
  const items: Resource[] = [];

  // Links
  $('a[href]').each((_, el) => {
    const href = $(el).attr('href')!.trim();
    if (/^(data:|#|mailto:|tel:)/.test(href)) return;
    if (href.includes('[') || href.includes(']')) return;  // ignore URLs with brackets
    try {
      const u = new URL(href, baseUrl);
      if (u.hash) return;
      if (u.href.includes('PHPSESSID') || u.href.includes('/cdn-cgi/l/email-protection')) return;
      items.push({ url: u.href, type: 'link' });
    } catch {}
  });

  // Common image extensions
  const isImageExt = (p: string) => /\.(jpe?g|png|gif|svg)$/i.test(p);

  // Images in src and srcset
  $('img').each((_, el) => {
    const src = $(el).attr('src')?.trim();
    if (src && !src.startsWith('data:') && !src.includes('[') && !src.includes(']')) {
      try {
        const u = new URL(src, baseUrl);
        if (!u.hash && !u.href.includes('PHPSESSID') && isImageExt(u.pathname)) {
          items.push({ url: u.href, type: 'image' });
        }
      } catch {}
    }
    const srcset = $(el).attr('srcset');
    if (srcset) {
      srcset.split(',').forEach(part => {
        const urlPart = part.trim().split(/\s+/)[0];
        if (urlPart && !urlPart.startsWith('data:') && !urlPart.includes('[') && !urlPart.includes(']')) {
          try {
            const u = new URL(urlPart, baseUrl);
            if (!u.hash && !u.href.includes('PHPSESSID') && isImageExt(u.pathname)) {
              items.push({ url: u.href, type: 'image' });
            }
          } catch {}
        }
      });
    }
  });

  // Images in <source srcset>
  $('source[srcset]').each((_, el) => {
    $(el).attr('srcset')!.split(',').forEach(part => {
      const urlPart = part.trim().split(/\s+/)[0];
      if (urlPart && !urlPart.startsWith('data:') && !urlPart.includes('[') && !urlPart.includes(']')) {
        try {
          const u = new URL(urlPart, baseUrl);
          if (!u.hash && !u.href.includes('PHPSESSID') && isImageExt(u.pathname)) {
            items.push({ url: u.href, type: 'image' });
          }
        } catch {}
      }
    });
  });

  return items;
}

// Gets the status code
async function getStatusCode(url: string): Promise<number | null> {
  try {
    const head = await axios.head(url, { timeout: 5000, maxRedirects: 5, headers: { 'User-Agent': 'k0lmena-link-tester/1.0' } });
    return head.status;
  } catch (e: any) {
    const st = e.response?.status;
    if (st && st !== 405) return st;
  }
  try {
    const get = await axios.get(url, { timeout: 5000, maxRedirects: 5, responseType: 'stream', headers: { 'User-Agent': 'k0lmena-link-tester/1.0' } });
    return get.status;
  } catch (e: any) {
    return e.response?.status ?? null;
  }
}

// Checks that an image resource has an image content-type
async function isImageValid(url: string): Promise<boolean> {
  const cleanUrl = url.split('?')[0];
  try {
    const head = await axios.head(cleanUrl, { timeout: 5000, headers: { 'User-Agent': 'k0lmena-link-tester/1.0' } });
    return String(head.headers['content-type'] || '').startsWith('image/');
  } catch {
    return false;
  }
}

// Tests a list of resources
async function testResources(resources: Resource[]): Promise<{ brokenLinks: Resource[]; brokenImages: Resource[]; }> {
  const brokenLinks: Resource[] = [];
  const brokenImages: Resource[] = [];
  await Promise.all(resources.map(r => limitResource(async () => {
    const testUrl = r.type === 'image' ? r.url.split('?')[0] : r.url;
    const status = await getStatusCode(testUrl);
    const code = status ?? 0;
    let broken = false;
    if ([400, 404].includes(code) || (code >= 500 && code < 600)) broken = true;
    else if (r.type === 'image' && !(await isImageValid(r.url))) broken = true;
    if (broken) {
      if (r.type === 'link') brokenLinks.push(r);
      else brokenImages.push(r);
    }
  })));
  return { brokenLinks, brokenImages };
}

// Gets the sitemap URLs
async function getSitemapUrls(baseUrl: string): Promise<string[]> {
  try {
    const xml = await fetchHTML(baseUrl.replace(/\/$/, '') + '/sitemap.xml');
    const urls: string[] = [];
    const re = /<loc>(.*?)<\/loc>/g;
    let m;
    while ((m = re.exec(xml))) urls.push(m[1].trim());
    return urls;
  } catch {
    return [];
  }
}

// Full scan (crawler)
export async function crawlAndTest(baseUrl: string): Promise<void> {
  logLine('🚀 Starting full scan...');
  const baseHost = new URL(baseUrl).hostname;
  const visited = new Set<string>();
  const brokenLinksAll: Resource[] = [];
  const brokenImagesAll: Resource[] = [];
  let totalLinks = 0;
  let totalImages = 0;
  let currentPage = '';

  const sitemap = await getSitemapUrls(baseUrl);
  const queue = [baseUrl, ...sitemap.filter(u => new URL(u).hostname.endsWith(baseHost))];

  const limitPage = pLimit(PAGE_CONCURRENCY);
  const startTime = Date.now();

  try {
    while (queue.length) {
      const batch = queue.splice(0, PAGE_CONCURRENCY);
      await Promise.all(batch.map(page => limitPage(async () => {
        if (visited.has(page)) return;
        visited.add(page);
        currentPage = page;
        logLine(`🔍 Scanning: ${page}`);
        const html = await fetchHTML(page);
        const resources = extractResources(html, page);
        totalLinks += resources.filter(r => r.type === 'link').length;
        totalImages += resources.filter(r => r.type === 'image').length;
        const { brokenLinks, brokenImages } = await testResources(resources);
        brokenLinksAll.push(...brokenLinks);
        brokenImagesAll.push(...brokenImages);
        brokenLinks.forEach(r => logLine(`- 🚫 Broken link: ${r.url}`));
        brokenImages.forEach(r => logLine(`- 🚫 Broken image: ${r.url}`));
        resources.filter(r => r.type === 'link').forEach(r => {
          try {
            const u = new URL(r.url);
            if ((u.hostname === baseHost || u.hostname.endsWith(`.${baseHost}`)) && !visited.has(u.href) && !queue.includes(u.href)) {
              queue.push(u.href);
            }
          } catch {}
        });
      })));
    }
  } catch (error: any) {
    const timestamp = new Date().toISOString();
    const errContent = `=== Error on page: ${currentPage} ===\n` +
                       `Time: ${timestamp}\n` +
                       `Message: ${error.message}\n` +
                       `Stack:\n${error.stack}\n`;
    fs.writeFileSync(ERROR_LOG_FILE, errContent, 'utf-8');
    fs.writeFileSync(OUTPUT_FILE, outputLines.join('\n'), 'utf-8');
    throw error;
  }

  const endTime = Date.now();
  logLine('');
  logLine('✅ Full scan finished.');
  logLine(`Pages scanned: ${visited.size}`);
  logLine(`🔗 Total links: ${totalLinks} | 🚫 Broken links: ${brokenLinksAll.length}`);
  logLine(`🖼️ Total images: ${totalImages} | 🚫 Broken images: ${brokenImagesAll.length}`);
  logLine(`⏱️ Duration: ${formatDuration(endTime - startTime)}`);

  // Save the full results
  fs.writeFileSync(OUTPUT_FILE, outputLines.join('\n'), 'utf-8');
  logLine(`📄 Results saved to: ${OUTPUT_FILE}`);
}

// Single-page scan
async function testSinglePage(baseUrl: string): Promise<void> {
  logLine('🚀 Starting single-page scan...');
  const startTime = Date.now();
  let currentPage = baseUrl;
  try {
    const html = await fetchHTML(baseUrl);
    const resources = extractResources(html, baseUrl);
    const { brokenLinks, brokenImages } = await testResources(resources);
    brokenLinks.forEach(r => logLine(`- 🚫 Broken link: ${r.url}`));
    brokenImages.forEach(r => logLine(`- 🚫 Broken image: ${r.url}`));

    const endTime = Date.now();
    logLine('');
    logLine('🔚 Single-page results:');
    logLine(`🔗 Links scanned: ${resources.filter(r => r.type === 'link').length} | 🚫 Broken links: ${brokenLinks.length}`);
    logLine(`🖼️ Images scanned: ${resources.filter(r => r.type === 'image').length} | 🚫 Broken images: ${brokenImages.length}`);
    logLine(`⏱️ Duration: ${formatDuration(endTime - startTime)}`);
  } catch (error: any) {
    const timestamp = new Date().toISOString();
    const errContent = `=== Error on single page: ${currentPage} ===\n` +
                       `Time: ${timestamp}\n` +
                       `Message: ${error.message}\n` +
                       `Stack:\n${error.stack}\n`;
    fs.writeFileSync(ERROR_LOG_FILE, errContent, 'utf-8');
    fs.writeFileSync(OUTPUT_FILE, outputLines.join('\n'), 'utf-8');
    throw error;
  }

  // Save the results
  fs.writeFileSync(OUTPUT_FILE, outputLines.join('\n'), 'utf-8');
  logLine(`📄 Results saved to: ${OUTPUT_FILE}`);
}

// CLI with options
async function main() {
  const baseUrl = process.env.BASEURL;
  if (!baseUrl) { console.error('❌ Error: APP_URL is not defined in the .env'); process.exit(1); }
  const args = process.argv.slice(2);
  const full = args.includes('-full');

  // Clear previous lines
  outputLines = [];

  try {
    if (full) await crawlAndTest(baseUrl);
    else await testSinglePage(baseUrl);
  } catch (error) {
    console.error('❌ Error during the scan. See error_log.txt for more details.');
  }
}

if (require.main === module) main();
