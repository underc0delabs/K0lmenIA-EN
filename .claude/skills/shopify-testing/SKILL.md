---
name: shopify-testing
description: How to test a Shopify store — development vs. real stores, password-protected store, themes (Online Store 2.0, sections and blocks, previewing an unpublished theme, Theme Check), Liquid errors and missing translations, apps and app embeds, Shopify checkout (extensibility, guest and customer accounts), Bogus Gateway and Shopify Payments test mode, Markets (currency, language, taxes and prices per market), shipping profiles and locations, automatic and code discounts, accelerated checkout buttons (Shop Pay, Apple Pay, Google Pay), the removal of checkout.liquid, test orders and post-sale (refund with restock, edit, cancel), gift cards, subscriptions, Shopify Flow, B2B and POS, leftovers from uninstalled apps, metafields, search and filters, redirects, duties and rounding per market, webhooks with HMAC, the read-only GraphQL Admin API, the public endpoints (/products.json, /cart.js), customer events and pixels, how to automate it with Playwright (password, preview, captcha), typical bugs and questions for the PO. Used by the shopify-tester and the mappers when they automate a Shopify store.
---

# Testing on Shopify

Shopify handles the server, the checkout and the payments; what changes from one store to another is **the theme, the apps and the configuration** (markets, shipping, taxes, discounts). That is where almost all the bugs are. It builds on the `ecommerce-testing` skill.

## 1. The store

- **Development store** (`plan.partnerDevelopment = true`): you can place test orders without charges. This is where you test.
- **Real store**: read-only survey only. A test order, only with the gateway in test mode, with confirmation, and then it is canceled and archived.
- **Password-protected store** (`/password`): the public checks don't pass; with Playwright, you enter with the storefront password (from the `.env`, never in the chat).

## 2. Theme

- **Preview without publishing**: `?preview_theme_id=<id>` lets you test a new theme without affecting customers. Compare against the published one with `pixel-perfect`.
- **Sections and blocks** (Online Store 2.0): each template (home, collection, product, cart, page, blog, 404, search) can have different sections; walk through them all.
- **Liquid errors** (`Liquid error: ...`, `Could not find asset snippets/...`) and **missing translations** (`translation missing: en.products.product.add_to_cart`) appear on the page: they are bugs.
- **Theme Check** (`shopify theme check`, with the Shopify CLI and the theme code) finds Liquid errors, heavy assets and missing translations before publishing.
- The `Shopify.theme` object in the HTML says which theme and version is being viewed.
- **Before editing, duplicate**: the duplicated theme is the backup copy and the place to test. Compare the edited duplicate against the published one before publishing it.
- **Leftovers from uninstalled apps**: old apps pasted code into the theme (snippets, `{% render %}`, scripts); uninstalling them leaves calls to files that no longer exist (404 in the console, `Could not find asset`). New apps use **theme app extensions** (blocks and app embeds) that go away with the app.
- **Metafields and metaobjects** (`product.metafields...`): if the theme shows them (size chart, materials, spec sheet), test products with the metafield empty, long and formatted.
- **Search and filters** (Search & Discovery app): filters by variant, price and availability; order; synonyms; out-of-stock products (whether they are hidden or go to the end, per the rule).
- **`robots.txt.liquid`** and **URL redirects** (Navigation → Redirects): after a migration or after changing handles, the old URLs have to redirect, not give a 404.

## 3. Apps

- Apps inject scripts (app embeds) and blocks: check the console on each key page and the load time with and without the app (disable the embed in a duplicated theme).
- After installing or updating an app: regression of the product page, cart and checkout.
- Subscription, review, filter and translation apps are the ones that break the most.

## 4. Checkout and payments

- **Bogus Gateway** (test provider): card number `1` approved, `2` declined, `3` gateway error; any name, a future date and CVV.
- **Shopify Payments in test mode**: the Shopify test cards (for example, 4242 4242 4242 4242 approved, and the decline and 3-D Secure ones from their documentation).
- Test as a **guest** and with **customer accounts** (the new ones are passwordless, with a code by email).
- The **checkout extensions** (checkout extensibility) and the discount/shipping/payment **functions** change the checkout: each one is a case.
- The checkout total has to match `/cart.js` and the order in the admin.
- **Accelerated checkout buttons** (Shop Pay, Apple Pay, Google Pay, PayPal) on the product page and the cart: they **skip the cart**, so they also skip whatever the theme validates there (required note, terms checkbox, minimum purchase). Test that those rules are still enforced or that the buttons aren't shown.
- **`checkout.liquid` no longer exists**: Shopify removed it and the old Plus customizations (scripts in the checkout, the thank-you page and the order status) are replaced by **checkout extensions** and **pixels**. If the store comes from that era, test that what the old code did (tracking, extra fields, messages) still works.
- **Manual payments** (bank transfer, cash, cash on delivery): the order stays with the payment pending; marking it as paid from the admin does or doesn't decrease stock depending on the configuration.

## 5. Orders and post-sale

- Orders placed with Bogus Gateway or in test mode are marked as **test** in the admin; they still decrease stock and send emails.
- **Refund** from the admin: full or partial, with or without **restocking** (the *Restock* checkbox), and with or without refunding shipping.
- **Edit an order** (add or remove products, change quantities): it recalculates the total and asks for a charge or a refund for the difference.
- **Cancel** an order: refund and restock according to what is checked.
- **Native gift cards**: they are sold as a product, arrive by email with the code, are used at checkout (partial balance, balance that isn't enough) and can be deactivated.
- **Subscriptions** (apps on *selling plans*): the plan selector on the product page, the first charge, the renewal and the cancellation from the customer account.
- **Shopify Flow** and automation apps: tags, notices and automatic changes triggered by the order; test that they trigger once and with the correct order.
- **B2B** (Plus): companies and locations, catalogs with their own prices, minimums and payment terms (net 30).
- **POS and in-store pickup**: stock is shared between the online store and the point of sale; pickup or local delivery are only offered at the configured addresses or locations.

## 6. Markets, currency and taxes

- Each **market** can have its own currency, language, domain or subfolder, prices and rounding: test as a shopper in each one (change the country in the selector or through the market URL).
- **Taxes included or not** (`taxesIncluded`) change the price shown; taxes on shipping (`taxShipping`) change the total.
- **Price rounding** per market (for example, to .99 or to whole numbers) and **fixed prices** per market instead of automatic conversion: test both.
- **Duties and import taxes** on international sales: if they are charged at checkout, that they appear in the total and in the order.
- **Geolocation redirect** (or the "Do you want to go to your country's store?" notice): that it doesn't prevent choosing another country by hand and doesn't break the checkout.
- **Languages** (Translate & Adapt or another app): theme, notification and checkout texts in each language (`translation-analyst`).

## 7. Shipping, locations and inventory

- **Shipping profiles**: products with different profiles in the same cart add up rates; a profile with no active methods leaves products that can't be bought.
- **Locations**: which one stock is drawn from and whether in-store pickup is offered.
- **Continue selling when out of stock** (`inventoryPolicy = CONTINUE`) is pre-order: confirm with the business that it is intentional.

## 8. Discounts

- **By code** (basic, buy X get Y, free shipping) and **automatic**; the **combination** rules between product, order and shipping discounts are the most common source of miscalculated totals.
- Usage limit, one per customer, dates, minimum purchase or quantity, included products or collections.

## 9. Webhooks

- Each webhook signs the body with **X-Shopify-Hmac-Sha256**: the receiver has to validate it and reject a tampered one.
- Shopify retries: the receiver has to process the same event **only once** (`X-Shopify-Webhook-Id`).
- A webhook to `http://`, `localhost` or a tunnel (ngrok) in a shared environment is a finding.

## 10. APIs for the survey (read-only)

- **Public**: `/products.json` (catalog, paginated), `/products/<handle>.js`, `/cart.js` (current cart), `/policies/<policy>`.
- **Admin API GraphQL** with the token of a **custom app with `read_*` scopes** only (`read_products`, `read_inventory`, `read_themes`, `read_shipping`, `read_markets`, `read_discounts`, `read_locations`). Never mutations. It has a **cost limit** per query: if it responds `THROTTLED`, wait and retry.
- The API version (`SHOPIFY_API_VERSION`) is quarterly (`2026-07`, `2026-10`…) and each one lasts a year. If a query fails on a version, it may be that the field changed name: the survey records it under "Queries that couldn't be made".
- `/products.json` returns up to 250 products per page (`?limit=250&page=N`) and doesn't show stock; the real stock comes from the Admin API.

## 11. Analytics and pixels

- **Customer events** (Settings → Customer events: Google, Meta, TikTok and custom pixels) fire at checkout: the purchase event (`checkout_completed`) has to fire **once**, with the amount, the currency and the order's products, and not fire again when the order status page is reloaded.
- With the cookie banner not accepted, the marketing pixels must not load (Shopify respects consent if the banner is configured correctly).

## 12. Automate with Playwright (web-mapper)

- Locate by role and accessible name; the section IDs (`shopify-section-template--1234__main`) change when the theme is edited.
- The **checkout** lives on another domain or subpath and loads card fields in **iframes** (`card-fields`): use `frameLocator`.
- Wait for `/cart/add.js` and `/cart/change.js` to respond before reading the cart counter.
- Dismiss the cookie notice and the subscription popups at the start of the scenario.
- **Password-protected store**: fill the `/password` form once and reuse the saved session (`npm run login`), not in every scenario.
- **Theme preview**: `?preview_theme_id=<id>` adds a preview bar at the bottom; close it so it doesn't cover the buy button on mobile.
- **Captcha** (bot protection on accounts and contact forms): it is not bypassed. In the development store, ask for it to be disabled for the automated tests or leave those steps as manual.
- **Data that changes on its own** (stock, a market's prices): verify relative to the data you read at the start, not against a fixed number.

## 13. Typical Shopify bugs

- `Liquid error` or `translation missing` visible after editing the theme.
- An app that duplicates the buy button or breaks the variant selector.
- Price per market without rounding or in the main market's currency.
- Discounts that combine when they shouldn't.
- A product out of stock at the fulfillment location that is still offered.
- Refund or privacy policy unpublished (missing in the checkout footer).
- An accelerated checkout button that lets you buy without meeting the minimum or without the cart's terms checkbox.
- Leftovers from an uninstalled app that give 404 in the console or leave an empty block.
- Old URLs without a redirect after changing a product's or collection's handle.
- Pixel purchase event duplicated when reloading the order status page.
- Refund done without restocking when the rule was to restock.
- An empty metafield that leaves a title without content on the product page.

## 14. Typical questions for the PO (Shopify)

In addition to those of the `ecommerce-testing` skill, when it isn't written down they are `MI-XX`:

- Is any product still sold when out of stock (pre-order)? Which ones?
- Which discounts can be combined (product, order, shipping)?
- Are prices per market converted automatically or fixed? With what rounding?
- Do the accelerated checkout buttons go on the product page, in the cart or nowhere?
- Are customer accounts required, optional or disabled?
- Which apps are in the scope of the test and which are third-party that aren't tested?
- Does a refund restock by default?

## 15. Smoke, regression, performance and security (Shopify)

The generic part (the five test types) is in `ecommerce-testing`; here, what is specific to Shopify.

- **Smoke** (development store or a theme in preview): home, collection and product page with no `Liquid error` or `translation missing`; add to cart and reach the checkout; the gateway in test mode (Bogus Gateway or Shopify Payments test). Fast and blocking.
- **Regression**: after **publishing a theme**, **installing or updating an app** or a **checkout extensibility** change, run the complete purchase flow (guest and account, approved and declined) watching the console; add `pixel-perfect` against the published theme and `cross-browser`. Use the theme **preview** (`?preview_theme_id=`) to test before publishing. Compare with `Theme Check`.
- **Performance**: Shopify's **Online Store speed report** and Lighthouse (`web-performance-auditor`) on home, collection and product page; the impact of each **app embed** (measure with and without the embed in a duplicated theme); images served by Shopify's CDN at the correct size; heavy Online Store 2.0 sections. The server, the checkout and the payments are handled by Shopify, so the margin is in **theme and apps**.
- **Security**: Shopify handles the infrastructure and the PCI of the checkout, so the focus is the **configuration**: webhooks signed with **X-Shopify-Hmac-Sha256** and processed only once (`X-Shopify-Webhook-Id`); Storefront API tokens and private app keys with the **minimum scope**; that no tokens or secrets remain in the theme code or in public metafields; customer accounts (that a customer doesn't see other customers' orders); **app proxy** that validates the signature; the storefront password in staging. The active security, with `security-analyst` / `web-pentester`.
