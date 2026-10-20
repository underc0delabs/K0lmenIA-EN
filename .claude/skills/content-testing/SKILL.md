---
name: content-testing
description: How to review the quality of a product's content and copy in its main language (separate from translations, which translation-analyst covers) — objective errors and typos — spelling and grammar (with LanguageTool if available), duplicated words ("the the"), unreplaced placeholders and template variables ({{name}}, ${var}, %s), forgotten Lorem ipsum and filler text, visible i18n keys (home.title.welcome), TODO/FIXME markers, spaces before punctuation and multiple spaces; and microcopy consistency — terms used inconsistently (sign in vs. log in), capitalization and punctuation, clear buttons and labels, understandable and actionable error messages, uniform tone, date/number/currency format, and cut-off or empty text; how to automate (extract the visible text of the website with Playwright and run it through the content tool; project term glossary), typical bugs and questions for the PO. Used by the content-reviewer.
---

# Content and typo review

**Text errors** (a typo, an unreplaced `{{name}}`, "the the", a translation key on display) damage trust and slip through to production. This reviews the content in the product's **main language**; **translations** between languages are covered by the `translation-analyst` (they are different and complementary things). It does not judge style or subjective tone, only objective issues and the project's rules.

## 1. Objective errors (typos and filler)

- **Spelling and grammar**: with **LanguageTool** (if installed, `--lt`) for the content's language; otherwise, the heuristic covers the most glaring issues.
- **Duplicated words** ("the the", "a a"), **spaces before punctuation**, **multiple spaces**.
- **Unreplaced placeholders**: `{{variable}}`, `${var}`, `%s`, `%(name)s` visible in the UI.
- Forgotten **Lorem ipsum** and filler text ("asdf", "test test", "xxx").
- **Visible i18n keys**: `home.header.title` showing instead of the text (cross-check with `translation-analyst`).
- **Markers**: TODO/FIXME/PENDING in the content.

## 2. Microcopy consistency

- **Consistent terms**: do not mix "sign in" / "log in" / "enter" for the same action; "cart" / "basket"; keep a project **glossary**.
- **Capitalization and punctuation**: uniform style in titles and buttons (Title Case vs. sentence case), no inconsistent trailing periods in labels.
- Clear, actionable **buttons and labels** ("Save changes" is better than "OK"); no ambiguous text.
- **Error messages** a person can understand (what happened and what to do), not codes or technical jargon.

## 3. Format and missing text

- **Dates, numbers and currency** in the locale's format; consistent units.
- **Cut-off, truncated or empty text** (labels without content, "undefined"/"null" on display).

## 4. Automate

- Extract the **visible text** of each page with Playwright (accessibility snapshot or the rendered content) and run it through `npm run content` (`tools/content/content.py`): heuristic always, and LanguageTool with `--lt` if available.
- Review the microcopy and term consistency by hand or against the project **glossary** (if it exists; if not, it is an `MI-XX`).
- Fixed content (not generated) is best reviewed once per release; dynamic content, with test data.

## 5. Typical content bugs

- `{{name}}` / `%s` unreplaced and on display.
- i18n key (`checkout.button.pay`) showing instead of the text.
- Duplicated word or typo in a title or CTA.
- Inconsistent terms for the same action across screens.
- Technical error message ("Error 500") shown to the end user.
- Lorem ipsum or "test" forgotten on a real page.
- Button with ambiguous text ("OK"/"Click here") or empty label.

## 6. Typical questions for the PO (content)

When it is not written down, they are `MI-XX`:

- What is the main language of the content?
- Is there a project **glossary** or style/microcopy guide?
- Title Case or sentence case in titles and buttons?
- Which terms are the "official" ones for key actions (login, cart, etc.)?
- Which content is fixed and which is generated dynamically?
