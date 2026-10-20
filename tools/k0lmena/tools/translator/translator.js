// Translation and internationalization review (translation-analyst agent).
//
// Usage (from the repo root):
//   npm run translator -- [--url https://my-app.com] [--languages en-US,es-AR,pt-BR] [--pages url1,url2]
//                        [--max-pages 5] [--depth 1] [--resolutions 1366x768,390x844]
//                        [--language-url "https://my-app.com/{short_language}/"] [--story US-001] [--headed]
//
// It visits each page in each language (the first one in --languages is the reference) and looks for:
//   - untranslated texts: in a language other than the page's, or identical to the reference version,
//     also in placeholders, alternative texts, titles and aria-label,
//   - visible translation keys (home.title, MISSING_TRANSLATION, {{ t('...') }}),
//   - badly encoded characters (Ã©, â€™, �),
//   - truncated or overflowing texts (translations are usually longer) and horizontal scroll,
//   - formats from another region: numbers (1.234,56 vs 1,234.56) and month or day names in another language,
//   - the HTML lang attribute that does not match the language.
// How it switches language, in this order: the page's <link rel="alternate" hreflang>, the
// --language-url template (TRANSLATOR_LANGUAGE_URL in the .env) with {language} and {short_language}, or the same URL asking
// the browser for the language (locale and Accept-Language).
// It takes a screenshot of each page in each language and resolution, with the problems marked.
//
// It leaves everything in output/translator/<US or host>/ (translator.json, translator-report.html, screenshots/ and crops/);
// the previous run moves to history/ (the last 5 are kept). It only navigates with GET.
const fs = require('fs');
const path = require('path');
const { normalize, slug, stamp, walkScroll, load } = require('../explorer/explore.js');
const { parseResolutions, discover } = require('../pixel-perfect/pixel-perfect.js');
const visual = require('../visual/compare.js');
const { archive } = require('../history/history.js');

const ROOT = path.resolve(__dirname, '..', '..', '..', '..');
const fromCwd = (p) => path.resolve(process.env.INIT_CWD || process.cwd(), p);
const GENERATED = ['translator.json', 'analysis.json', 'translator-report.html', 'screenshots', 'crops'];
const SEV_ORDER = { 'Critical': 0, 'High': 1, 'Medium': 2, 'Low': 3 };

// Very frequent words of each language (to detect which language a text is in).
const WORDS = {
  es: 'el la los las de del que y en un una por con para es se su sus al lo como más pero ya este esta entre cuando muy sin sobre también hasta hay donde desde todo nos ni otros ese eso esto antes algunos qué unos otro otra tanto esa estos mucho nada poco estar estas algo mi tu ver comprar carrito buscar ingresar cuenta envío envíos precio inicio productos ayuda contacto agregar iniciar sesión registrarse olvidaste contraseña gratis pedido pedidos cerrar volver siguiente anterior enviar mensaje nuestro nuestra usted días hoy semana',
  en: 'the of and to in is you that it was for on are as with they at be this have from or had by but not what all were we when your can there an each which she do how their if will up other about out many then them these so some her would make like into time has two more go see no way could people my than first been who its now find down day did get come made may home search cart sign login account price shipping buy view add free order orders close back next previous send message our week today checkout your products product total welcome store deals valid until rights reserved',
  pt: 'o os a as de do da dos das que e em um uma para com não por mais como mas foi ao ele tem à seu sua ou ser quando muito há nos já está eu também só pelo pela até isso ela entre era depois sem mesmo aos ter seus quem nas esse eles estão você essa nem suas meu minha numa pelos elas qual será nós lhe deles essas esses pelas este dele vocês nosso nossa carrinho entrar conta preço frete comprar buscar início produtos ajuda contato adicionar grátis pedido fechar voltar próximo enviar mensagem semana hoje',
  fr: 'le la les de des du un une et en est que qui dans pour pas sur au avec ce il elle ne se plus par son sa ses ou mais nous vous leur on tout aux été être avoir fait comme bien sans panier compte prix livraison acheter rechercher accueil produits aide contact ajouter gratuit commande fermer retour suivant envoyer',
  it: 'il lo la i gli le di del della dei che e un una per con non è sono si da al alla come più ma anche questo questa tutto ci ne nel nella carrello accedi conto prezzo spedizione acquista cerca prodotti aiuto contatto aggiungi gratis ordine chiudi indietro avanti invia',
  de: 'der die das und ist nicht ein eine zu den von mit sich des auf für im dem es auch an werden aus er hat dass sie nach wird bei einer um am sind noch wie einem über so zum kann nur war warenkorb anmelden konto preis versand kaufen suchen startseite produkte hilfe kontakt hinzufügen kostenlos bestellung schließen zurück weiter senden',
};
const DICT = Object.fromEntries(Object.entries(WORDS).map(([k, v]) => [k, new Set(v.split(/\s+/))]));
const MONTHS = {
  es: 'enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre lunes martes miércoles jueves viernes sábado domingo',
  en: 'january february march april june july august september october november december monday tuesday wednesday thursday friday saturday sunday',
  pt: 'janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro segunda-feira terça-feira quarta-feira quinta-feira sexta-feira sábado domingo',
  fr: 'janvier février mars avril mai juin juillet août septembre octobre novembre décembre lundi mardi mercredi jeudi vendredi samedi dimanche',
  it: 'gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre lunedì martedì mercoledì giovedì venerdì sabato domenica',
  de: 'januar februar märz april mai juni juli august september oktober november dezember montag dienstag mittwoch donnerstag freitag samstag sonntag',
};
const MONTH = Object.fromEntries(Object.entries(MONTHS).map(([k, v]) => [k, new Set(v.split(/\s+/))]));
const KEY_RE = /^(?:[a-z][a-z0-9_]*\.){1,5}[a-z0-9_]+$|MISSING[_ ]TRANSLATION|translation missing|\[missing "[^"]+" translation\]|\{\{\s*(?:t|\$t|i18n)\s*\(|__\(['"]/i;
// A domain (qarmy.ar, store.com.ar) is not a key even if it has the same shape.
const DOMAIN = /\.(com|net|org|edu|gov|io|ar|es|br|mx|cl|uy|co|pe|uk|us|de|fr|it|pt|dev|app|ai|info|biz|tv|me)$/i;
const KEY = { test: (t) => KEY_RE.test(String(t).trim()) && !DOMAIN.test(String(t).trim()) && !/[A-Z]{2,}\./.test(String(t).trim()) };
const MOJIBAKE = /Ã[\u0080-¿¡-ÿ]|â€[™œ\u009d“”˜]|Â[ ¡-¿]|�/;

function parseArgs(argv) {
  const a = { maxPages: 5, depth: 1, resolutions: '1366x768,390x844', headed: false,
    languages: (process.env.TRANSLATOR_LANGUAGES || '').split(',').map((x) => x.trim()).filter(Boolean), languageUrl: process.env.TRANSLATOR_LANGUAGE_URL || '' };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const v = () => argv[++i];
    if (k === '--url') a.url = v();
    else if (k === '--languages') a.languages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--pages') a.pages = v().split(',').map((x) => x.trim()).filter(Boolean);
    else if (k === '--max-pages') a.maxPages = parseInt(v(), 10);
    else if (k === '--depth') a.depth = parseInt(v(), 10);
    else if (k === '--resolutions') a.resolutions = v();
    else if (k === '--language-url') a.languageUrl = v();
    else if (k === '--story') a.story = v();
    else if (k === '--output') a.output = v();
    else if (k === '--headed') a.headed = true;
    else if (k === '-h' || k === '--help') a.help = true;
    else throw new Error(`Unknown option: ${k}`);
  }
  if (a.story && !/^[A-Za-z]+-\d+$/.test(a.story)) throw new Error('--story must be an ID like US-001.');
  return a;
}

const short = (language) => String(language).toLowerCase().split(/[-_]/)[0];

// Which language is this text in? null if it is short or there are no clear signals.
function detectLanguage(text) {
  const words = String(text).toLowerCase().normalize('NFC').match(/[\p{L}]+(?:-[\p{L}]+)?/gu) || [];
  if (words.length < 2) return null;
  const points = {};
  for (const [k, dict] of Object.entries(DICT)) points[k] = words.filter((p) => dict.has(p)).length;
  const order = Object.entries(points).sort((x, y) => y[1] - x[1]);
  const [best, second] = order;
  // Short texts (buttons, placeholders): only if ALL the words belong to a single language.
  if (words.length < 3) return best[1] === words.length && (!second || second[1] < best[1]) ? best[0] : null;
  if (best[1] < 2 || best[1] < words.length * 0.2) return null;
  if (second && best[1] - second[1] < 1) return null; // tie: unknown
  return best[0];
}

// Number with separators from another region: "1.234,56" in English or "1,234.56" in Spanish.
function oddNumberFormat(text, language) {
  const base = short(language);
  const comma = ['es', 'pt', 'fr', 'it', 'de'].includes(base); // decimal comma
  const bad = [];
  for (const m of String(text).matchAll(/\b\d{1,3}(?:([.,])\d{3})+(?:([.,])\d{1,2})?\b/g)) {
    const [num, thousands, dec] = m;
    if (dec && thousands === dec) continue;
    const decimal = dec || null;
    if (decimal && ((comma && decimal === '.') || (!comma && decimal === ','))) bad.push(num);
    else if (!decimal && ((comma && thousands === ',') || (!comma && thousands === '.'))) bad.push(num);
  }
  return bad;
}

function otherLanguageMonths(text, language) {
  const base = short(language);
  const words = String(text).toLowerCase().match(/[\p{L}-]+/gu) || [];
  const others = new Set();
  for (const p of words) {
    if (MONTH[base] && MONTH[base].has(p)) continue;
    for (const [k, set] of Object.entries(MONTH)) if (k !== base && set.has(p) && !(MONTH[base] || new Set()).has(p)) others.add(p);
  }
  // "mayo"/"marzo"/"agosto" are the same in several languages: it only counts if it is not a word of the language.
  return [...others].filter((p) => !(DICT[base] && DICT[base].has(p)));
}

// In the page: visible texts (with their box) and whether they are truncated or overflowing.
function _textsInPage() {
  const route = (el) => {
    const parts = [];
    for (let n = el; n && n.nodeType === 1 && n !== document.body && parts.length < 6; n = n.parentElement) {
      let i = 1;
      for (let s = n.previousElementSibling; s; s = s.previousElementSibling) if (s.tagName === n.tagName) i++;
      parts.unshift(`${n.tagName.toLowerCase()}:${i}`);
    }
    return parts.join('>');
  };
  const sx = window.scrollX;
  const sy = window.scrollY;
  const output = [];
  const seen = new Set();
  const visible = (el) => {
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0 && r.width > 0 && r.height > 0;
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n && output.length < 1500; n = walker.nextNode()) {
    const t = n.textContent.replace(/\s+/g, ' ').trim();
    if (t.length < 2 || !/\p{L}/u.test(t)) continue;
    const el = n.parentElement;
    if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'CODE', 'PRE'].includes(el.tagName) || seen.has(el) || !visible(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const text = (el.innerText || t).replace(/\s+/g, ' ').trim().slice(0, 300);
    // Truncated: the content does not fit in its box and is hidden (overflow) or ends in "…".
    const truncated = (el.scrollWidth > el.clientWidth + 2 && ['hidden', 'clip'].includes(cs.overflowX)) || cs.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1;
    // Overflows: the text goes out of its container (without being hidden).
    const parent = el.parentElement;
    const pr = parent ? parent.getBoundingClientRect() : null;
    const overflows = !truncated && pr && cs.whiteSpace.includes('nowrap') && r.right > pr.right + 4;
    output.push({ key: route(el), tag: el.tagName.toLowerCase(), text, x: Math.round(r.left + sx), y: Math.round(r.top + sy), w: Math.round(r.width), h: Math.round(r.height),
      truncated, overflows: Boolean(overflows) });
  }
  // Attribute texts that are also translated.
  for (const el of document.querySelectorAll('[placeholder],[alt],[title],[aria-label]')) {
    if (output.length >= 1800) break;
    for (const at of ['placeholder', 'alt', 'title', 'aria-label']) {
      const v = (el.getAttribute(at) || '').trim();
      if (v.length < 2 || !/\p{L}/u.test(v)) continue;
      const r = el.getBoundingClientRect();
      output.push({ key: `${route(el)}@${at}`, tag: el.tagName.toLowerCase(), attribute: at, text: v.slice(0, 200),
        x: Math.round(r.left + sx), y: Math.round(r.top + sy), w: Math.round(r.width), h: Math.round(r.height) });
    }
  }
  return { lang: document.documentElement.getAttribute('lang') || '', title: document.title,
    alternates: [...document.querySelectorAll('link[rel="alternate"][hreflang]')].map((l) => ({ language: l.getAttribute('hreflang'), url: l.href })),
    texts: output, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    height: document.documentElement.scrollHeight };
}

// URL of a page in a language (and how it was obtained).
function urlInLanguage(url, language, alternates, template, reference) {
  const alt = (alternates || []).find((x) => x.language.toLowerCase() === language.toLowerCase())
    || (alternates || []).find((x) => short(x.language) === short(language));
  if (alt) return { url: alt.url, method: 'hreflang' };
  if (template) {
    const u = new URL(url);
    const pl = template.replace(/\{language\}/g, language).replace(/\{short_language\}/g, short(language));
    if (/^https?:/i.test(pl)) return { url: new URL(u.pathname.replace(/^\/[a-z]{2}(-[a-z]{2})?(?=\/|$)/i, '').replace(/^\//, '') + u.search, pl.endsWith('/') ? pl : `${pl}/`).href, method: 'template' };
    if (pl.startsWith('?') || pl.startsWith('&')) { const v = new URL(url); const [k, val] = pl.replace(/^[?&]/, '').split('='); v.searchParams.set(k, val); return { url: v.href, method: 'template' }; }
  }
  return { url, method: language === reference ? 'reference' : 'browser' };
}

function screenFindings(p, ref, language, reference) {
  const h = [];
  const base = short(language);
  const add = (type, severity, title, detail, t) => h.push({ type, severity, title, detail, text: t && t.text, element: t && t.key,
    box: t && t.w ? { x: t.x, y: t.y, w: t.w, h: t.h } : null });
  if (p.lang && short(p.lang) !== base) add('Lang attribute', 'Medium', `The HTML says lang="${p.lang}" and the page is ${language}`, 'Screen readers and search engines read the wrong language.');
  if (!p.lang) add('Lang attribute', 'Low', 'The HTML does not declare the language (lang)', 'Without lang, the screen reader does not know how to pronounce.');
  const refByKey = new Map((ref ? ref.texts : []).map((t) => [t.key, t]));
  for (const t of p.texts) {
    if (KEY.test(t.text.trim())) { add('Translation key', 'High', `The key “${t.text.slice(0, 60)}” is visible`, 'The translation for that key is missing: the person sees the internal name.', t); continue; }
    if (MOJIBAKE.test(t.text)) { add('Encoding', 'High', `Badly encoded characters: “${t.text.slice(0, 60)}”`, 'The text was saved or served with another encoding (UTF-8 vs Latin-1).', t); continue; }
    const det = detectLanguage(t.text);
    if (det && det !== base) {
      add('Untranslated', t.attribute ? 'Medium' : 'High', `${t.attribute ? `${t.attribute}: ` : ''}“${t.text.slice(0, 70)}” is in ${det}`, `The page is ${language} but this text is in another language.`, t);
      continue;
    }
    const r = refByKey.get(t.key);
    if (language !== reference && r && r.text === t.text && (t.text.match(/\p{L}{3,}/gu) || []).length >= 3 && short(reference) !== base) {
      add('Same as reference', 'Medium', `${t.attribute ? `${t.attribute}: ` : ''}“${t.text.slice(0, 70)}” is the same as in ${reference}`,
        'It was probably not translated (if it is a proper name or a brand, discard it).', t);
    }
    if (t.truncated) add('Truncated text', 'Medium', `“${t.text.slice(0, 60)}” does not fit in its place and is cut off`, `The ${t.tag} is smaller than the translated text.`, t);
    else if (t.overflows) add('Overflowing text', 'Medium', `“${t.text.slice(0, 60)}” goes out of its container`, 'The translated text is longer than the space it has.', t);
    const nums = oddNumberFormat(t.text, language);
    if (nums.length) add('Number format', 'Medium', `${nums.slice(0, 3).join(', ')} uses another region's format`, `In ${language} it is written ${new Intl.NumberFormat(language).format(1234.56)}.`, t);
    const months = otherLanguageMonths(t.text, language);
    if (months.length) add('Date in another language', 'Medium', `“${months.join(', ')}” is not in ${language}`, `The date or day of the week was not translated: “${t.text.slice(0, 80)}”.`, t);
  }
  if (p.overflow > 4 && (!ref || ref.overflow <= 4)) add('Overflow', 'Medium', `The page overflows ${p.overflow} px in width in ${language}`, 'A horizontal scroll appears: some translated text does not fit.', null);
  return h;
}

// The same problem (the same text) on several pages is a single finding.
function group(findings) {
  const groups = new Map();
  const output = [];
  for (const h of findings) {
    const k = `${h.type}|${h.language}|${h.text || h.title}`;
    const where = { page: h.page, url: h.url, resolution: h.resolution, crop: h.crop, screenshot: h.screenshot };
    if (!groups.has(k)) { const g = { ...h, where: [] }; groups.set(k, g); output.push(g); }
    groups.get(k).where.push(where);
  }
  return output;
}

function generateReport(folder) {
  const py = process.platform === 'win32' ? 'python' : 'python3';
  const r = require('child_process').spawnSync(py, [path.join(ROOT, 'scripts', 'generate_translation_report.py'),
    path.join(folder, 'translator.json'), path.join(folder, 'translator-report.html')], { encoding: 'utf8' });
  if (r.status !== 0) {
    const reason = (r.stderr || r.error || '').toString().trim().split(/\r?\n/).pop();
    console.log(`Could not generate the HTML report (${reason}). Generate it with: python scripts/generate_translation_report.py <folder>/translator.json <folder>/translator-report.html`);
    return false;
  }
  return true;
}

async function main() {
  const a = parseArgs(process.argv.slice(2));
  if (a.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').filter((l) => l.startsWith('//')).map((l) => l.slice(3)).join('\n'));
    return;
  }
  const url = a.url || (a.pages && a.pages[0]) || process.env.APP_URL || process.env.BASEURL;
  if (!url) throw new Error('No URL: pass it with --url or set APP_URL in the root .env.');
  if (!/^https?:\/\//i.test(url)) throw new Error(`The URL must start with http:// or https:// (got "${url}").`);
  const start = normalize(url);
  const host = new URL(start).hostname;
  const { chromium } = require('playwright');
  const browser = await chromium.launch({ headless: !a.headed });
  const ctx0 = await browser.newContext();
  const page0 = await ctx0.newPage();
  await load(page0, start).catch(() => {});
  const info0 = await page0.evaluate(_textsInPage).catch(() => ({ alternates: [], lang: '' }));
  // Languages: the requested ones or, otherwise, the ones the site declares (hreflang), with the page's own first.
  if (!a.languages.length) {
    const decl = [...new Set((info0.alternates || []).map((x) => x.language).filter((x) => x && x !== 'x-default'))];
    const own = info0.lang || (decl[0] || 'en');
    a.languages = [own, ...decl.filter((x) => short(x) !== short(own))];
  }
  if (a.languages.length < 2) {
    await browser.close();
    throw new Error(`Only one language was found (${a.languages.join(', ') || 'none'}): pass the ones you want to review with --languages en-US,es-AR (or TRANSLATOR_LANGUAGES in the .env).`);
  }
  const pages = await discover(page0, start, a);
  await ctx0.close();
  const reference = a.languages[0];
  const resolutions = parseResolutions(a.resolutions);
  const folder = a.output ? fromCwd(a.output) : path.join(ROOT, 'output', 'translator', a.story || host);
  archive(folder, GENERATED, 'translator.json');
  for (const n of GENERATED) fs.rmSync(path.join(folder, n), { recursive: true, force: true });
  const shotsDir = path.join(folder, 'screenshots');
  const cropsDir = path.join(folder, 'crops');
  for (const d of [shotsDir, cropsDir]) fs.mkdirSync(d, { recursive: true });
  const rel = (p) => path.relative(folder, p).split(path.sep).join('/');
  const relRoot = (p) => path.relative(ROOT, p).split(path.sep).join('/');
  console.log(`Translations: ${pages.length} page(s) × ${a.languages.length} language(s) (${a.languages.join(', ')}; reference ${reference}) × ${resolutions.length} resolution(s)`);
  console.log(`Output: ${relRoot(folder)}`);
  const t0 = Date.now();
  const screens = [];
  let findings = [];
  for (const [i, u] of pages.entries()) {
    const pageId = `${String(i + 1).padStart(2, '0')}-${slug(u)}`;
    for (const res of resolutions) {
      let ref = null;
      for (const language of a.languages) {
        const ctx = await browser.newContext({ viewport: { width: res.width, height: res.height }, deviceScaleFactor: 1, locale: language,
          extraHTTPHeaders: { 'Accept-Language': `${language},${short(language)};q=0.9` }, ...(res.width < 768 ? { isMobile: true, hasTouch: true } : {}) });
        const page = await ctx.newPage();
        const target = urlInLanguage(u, language, info0.alternates && i === 0 ? info0.alternates : null, a.languageUrl, reference);
        const p = { page: pageId, url: u, language_url: target.url, method: target.method, language, resolution: res.id };
        process.stdout.write(`[${language.padEnd(6)} ${res.id.padEnd(9)}] ${target.url} `);
        try {
          const { resp } = await load(page, target.url);
          p.status = resp ? resp.status() : 0;
          // The other pages: if they declare hreflang, that link is followed (more precise than the template).
          if (i > 0 && language !== reference) {
            const alt = await page.evaluate(() => [...document.querySelectorAll('link[rel="alternate"][hreflang]')].map((l) => ({ language: l.getAttribute('hreflang'), url: l.href })));
            const better = urlInLanguage(u, language, alt, a.languageUrl, reference);
            if (better.method === 'hreflang' && better.url !== target.url) { await load(page, better.url); p.language_url = better.url; p.method = 'hreflang'; }
          }
          await walkScroll(page);
          await page.evaluate(() => window.scrollTo(0, 0));
          await visual.stabilize(page);
          const info = await page.evaluate(_textsInPage);
          Object.assign(p, { lang: info.lang, title: info.title, texts: info.texts.length, overflow: info.overflow });
          const file = path.join(shotsDir, `${pageId}-${language}-${res.id}.png`);
          const height = Math.min(info.height, 9000);
          await page.screenshot({ path: file, fullPage: height === info.height, ...(height < info.height ? { clip: { x: 0, y: 0, width: res.width, height } } : {}) });
          p.screenshot = rel(file);
          const hs = screenFindings(info, ref, language, reference);
          for (const [k, h] of hs.entries()) {
            if (h.box && h.box.y < height) {
              const crop = path.join(cropsDir, `${pageId}-${language}-${res.id}-${k + 1}.png`);
              fs.writeFileSync(crop, visual.markedCrop(file, visual.windowOf([h.box], 60, 300, 120), h.box));
              h.crop = rel(crop);
            }
            findings.push({ ...h, language, page: pageId, url: p.language_url || u, resolution: res.id, screenshot: p.screenshot });
          }
          p.findings = hs.length;
          const untranslated = hs.filter((h) => h.type === 'Untranslated' || h.type === 'Same as reference').length;
          p.translated_pct = language === reference ? 100 : Math.max(0, Math.round((1 - untranslated / Math.max(1, info.texts.length)) * 1000) / 10);
          if (language === reference) ref = info;
          console.log(`→ ${hs.length} finding(s)`);
        } catch (e) {
          p.error = String(e.message || e).split('\n')[0].slice(0, 200);
          console.log(`→ error: ${p.error}`);
        }
        screens.push(p);
        await ctx.close();
      }
    }
  }
  await browser.close();
  findings = group(findings);
  findings.sort((x, y) => SEV_ORDER[x.severity] - SEV_ORDER[y.severity] || y.where.length - x.where.length);
  findings.forEach((h, i) => { h.id = `T-${String(i + 1).padStart(2, '0')}`; });
  const byLanguage = {};
  for (const language of a.languages) {
    const ps = screens.filter((p) => p.language === language && p.translated_pct != null);
    byLanguage[language] = { translated_pct: ps.length ? Math.round(ps.reduce((s, p) => s + p.translated_pct, 0) / ps.length * 10) / 10 : null,
      findings: findings.filter((h) => h.language === language).length, method: (ps.find((p) => p.method) || {}).method || null };
  }
  const count = (t) => findings.filter((h) => h.type === t).length;
  const result = {
    url: start, host, story: a.story || null, date: new Date().toISOString(), stamp: stamp(), duration_s: Math.round((Date.now() - t0) / 1000),
    tool: `Playwright ${require('playwright/package.json').version}`, languages: a.languages, reference, resolutions: resolutions.map((r) => r.id),
    summary: { pages: pages.length, languages: a.languages.length, screens: screens.length, findings: findings.length,
      untranslated: count('Untranslated') + count('Same as reference'), keys: count('Translation key'), encoding: count('Encoding'),
      truncated: count('Truncated text') + count('Overflowing text') + count('Overflow'), formats: count('Number format') + count('Date in another language'),
      lang: count('Lang attribute'), by_language: byLanguage,
      by_severity: Object.fromEntries(['Critical', 'High', 'Medium', 'Low'].map((s) => [s, findings.filter((h) => h.severity === s).length])) },
    findings, screens,
  };
  const output = path.join(folder, 'translator.json');
  fs.writeFileSync(output, JSON.stringify(result, null, 2), 'utf8');
  const r = result.summary;
  console.log(`\nUntranslated: ${r.untranslated} · visible keys: ${r.keys} · truncated or overflowing: ${r.truncated} · formats: ${r.formats} · findings: ${r.findings}`);
  for (const [k, v] of Object.entries(byLanguage)) console.log(`  ${k}: ${v.translated_pct ?? '—'} % translated · ${v.findings} finding(s) · ${v.method || ''}`);
  console.log(`Data: ${relRoot(output)}`);
  if (generateReport(folder)) console.log(`Report: ${relRoot(path.join(folder, 'translator-report.html'))}`);
}

if (require.main === module) {
  main().catch((e) => { console.error(`Error: ${e.message}`); process.exit(1); });
}

module.exports = { parseArgs, detectLanguage, oddNumberFormat, otherLanguageMonths, urlInLanguage, screenFindings, group, short, KEY, MOJIBAKE, GENERATED };
