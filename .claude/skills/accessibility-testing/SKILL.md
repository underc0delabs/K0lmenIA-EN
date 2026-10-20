---
name: accessibility-testing
description: How to audit accessibility (a11y) on all three platforms — web (WCAG 2.2, POUR principles, A/AA/AAA levels, axe-core, keyboard navigation and focus traps, visible focus, reflow at 320px, contrast, ARIA and roles, forms and error messages, headings and landmarks, NVDA/VoiceOver screen readers), mobile (Android TalkBack and iOS VoiceOver, accessible labels —contentDescription / accessibilityLabel—, touch target size 48dp/44pt, dynamic font scaling, focus order and grouping, gesture alternatives, captions, Accessibility Scanner and Accessibility Inspector, accessibility ids with Appium) and desktop (UI Automation — Name/ControlType of each control, full keyboard navigation and tab order, NVDA/JAWS/Narrator readers, high contrast mode, text and DPI scaling, controls without an accessible name). WCAG mapping to mobile/desktop, how to automate each platform (axe-core for web, Appium for mobile, the control tree on desktop) and what needs human judgment, how to prioritize by impact, and questions for the team. Used by the accessibility-analyst, and referenced by the mobile-tester and the desktop-tester.
---

# Accessibility (a11y): web, mobile and desktop

Accessibility means that **anyone** —using a screen reader, keyboard only, with low vision, color blindness or reduced motor skills— can use the product. The baseline is **WCAG 2.2** and its **POUR** principles (Perceivable, Operable, Understandable, Robust); mobile and desktop adapt those principles to their accessibility APIs. A tool runs the automatic checks; what needs human judgment is reviewed by hand.

## 1. What all three platforms share (POUR)

- **Perceivable**: everything visual has an alternative (alt text on images, captions on video), sufficient **contrast**, and information does not depend on color alone.
- **Operable**: everything can be used **with the keyboard only** (or switch/reader), **focus is visible** and its order is logical, no **focus traps**, touch/click targets are large enough.
- **Understandable**: clear labels and error messages, predictable behavior, declared language.
- **Robust**: each control exposes its **name, role and state** to the accessibility API (ARIA on web, labels on mobile, UIA on desktop); anything without an accessible name **cannot be used with a reader nor automated**.

## 2. Web (WCAG 2.2)

- **Automatic** (axe-core, `npm run accessibility`): contrast, misused roles/ARIA, images without alt, forms without labels, language, headings; **keyboard** (invisible focus, traps) and **reflow** at 320px.
- **Manual** (with Playwright MCP and `e2e-execution`): heading order and **landmarks**, menus/modals with the keyboard and intentionally trapped focus, error messages associated with the field, dynamic content announced (`aria-live`), and a pass with a **screen reader** (NVDA/VoiceOver).
- Default target level: **AA**.

## 3. Mobile (Android / iOS)

- **Accessible labels**: Android `contentDescription` / `labelFor`, iOS `accessibilityLabel`. An icon-only button without a label is invisible to TalkBack/VoiceOver (and to Appium).
- **Touch targets**: minimum ~**48dp** (Android) / **44pt** (iOS).
- **Dynamic font scaling** (Dynamic Type / large system font size): text grows without being cut off or covering controls.
- **Order and grouping** of the reader's focus; **alternatives to complex gestures** (whatever is done by swiping can also be done another way); **captions** on video.
- **Contrast** and not depending on color.
- Tools: **TalkBack** (Android) and **VoiceOver** (iOS) for manual review; **Accessibility Scanner** (Android) and **Accessibility Inspector** (Xcode) for the automatic part; with **Appium** you read the accessibility ids/labels (what is missing for a11y is also missing for automation). Complemented by `mobile-testing`.

## 4. Desktop (Windows / UI Automation)

- Each control exposes **Name** and **ControlType** through **UI Automation (UIA)**; a control without an accessible name is not read by NVDA/JAWS/Narrator and cannot be automated. The tool `tools/desktop/controls.py` (`npm run desktop`) already **flags controls without an accessible name**.
- **Full keyboard navigation** and logical tab order, visible focus, mnemonics (Alt+letter), Esc/Enter in dialogs.
- Windows **high contrast mode** and **text/DPI scaling**: the app stays usable, with no cut-off text.
- Review with a reader (NVDA is free). Complemented by `desktop-testing`.

## 5. WCAG mapping to mobile/desktop

WCAG criteria carry over: "alt text" → accessible label; "keyboard" → keyboard navigation (desktop) or reader/switch (mobile); "contrast" and "reflow/zoom" → font scaling and high contrast; "name, role, value" → UIA/labels. Use WCAG as a checklist outside the web too.

## 6. How to prioritize

By **impact on use**: first what **blocks** (a task cannot be completed with a reader or keyboard only: a button without a name, a focus trap, an unreachable control), then what **hinders** (low contrast, barely visible focus, small target) and finally the minor issues. State **who** each barrier affects.

## 7. What is automatic and what needs human judgment

- **Automatic**: contrast, missing names/labels, wrong roles, small targets, language. The per-platform tool runs it, without spending tokens per screen.
- **Human judgment**: whether the label **makes sense**, whether the reading order is logical, whether a dynamic change is announced, whether the whole flow can be done with a reader. That is reviewed by hand.

## 8. Typical questions for the team

When it is not written down, they are `MI-XX`:

- Which platforms (web, Android, iOS, desktop) and which target WCAG level (A/AA/AAA)?
- Do screen readers, keyboard only, high contrast and large fonts need to be supported?
- Which flows are critical to audit end to end with a reader?
- Is there an in-house accessibility guide or a legal standard to comply with?
