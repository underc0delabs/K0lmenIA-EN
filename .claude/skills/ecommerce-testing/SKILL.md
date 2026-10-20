---
name: ecommerce-testing
description: How to test an online store regardless of the platform — catalog and search, product pages and variants, prices and amounts (rounding, currency, compare-at price), stock and overselling, cart, checkout (guest and with an account), taxes, shipping and zones, coupons and discounts, payments with the gateway in test mode, order statuses, refunds and returns, transactional emails, multi-currency and language, mobile, product page SEO and legal pages; what usually gets left out (thank-you page and duplicate orders, persistent cart, concurrency over the last unit, gift cards, digital products, subscriptions, B2B, installments, zero-decimal currencies, invoicing, analytics and pixels, feeds, cookie consent); design techniques by area, test data, smoke test, post-deploy and pre-campaign regression, web performance (what to measure in a store) and store security (price and quantity tampering, IDOR on orders and invoices, coupon and voucher abuse, webhook signatures, gateway in live mode, exposed admin panel or debug, PII), how to report a store bug, questions for the PO, which k0lmenIA agents cover each part and the typical bugs. Used by the shopify-tester, the wordpress-tester, the prestashop-tester and the vtex-tester, and by the case generators when the story is about a store.
---

# E-commerce testing

In a store, the bugs that cost the most are the ones that **change what the buyer pays** or **what the store receives**: a miscalculated total, a coupon applied twice, a product sold without stock, an approved payment with the order still "pending". This skill says what to look at on any platform; the skills for each platform (`shopify-testing`, `wordpress-testing`) add their own.

## 1. Before testing: the environment

- **Test store or staging**, never the live store with customers. If it is the live one, you only look (read-only survey) and you do not buy.
- **Gateway in test mode** (sandbox) and the provider's **test cards**. If the gateway is in live mode, **do not pay**: report it and wait until it is switched to test mode.
- **Your own data**: test customers, orders and coupons with the `QA-` prefix, written down so they can be cleaned up.
- **What is expected** (shipping amounts, rounding rule, free-shipping minimum, when stock is deducted) comes from the story or the business, **not from what the store does today**. If it is not defined, it is `MI-XX`.

## 2. What to test

```
+---------------------------+------------------------------------------+
| Area                      | What to check                            |
+===========================+==========================================+
| Catalog                   | Collections/categories, filters and      |
|                           | sorting, pagination, search (no results, |
|                           | accents, plural, SKU), hidden products   |
|                           | that do not show up                      |
+---------------------------+------------------------------------------+
| Product page and variants | Each combination changes price, image,   |
|                           | stock and URL; a nonexistent or sold-out |
|                           | combination cannot be bought             |
+---------------------------+------------------------------------------+
| Prices                    | Compare-at price higher than the price,  |
|                           | rounding, thousands and decimal          |
|                           | separators, currency, price with and     |
|                           | without taxes                            |
+---------------------------+------------------------------------------+
| Stock                     | Sold out: cannot be added (not even      |
|                           | through a direct URL); pre-              |
|                           | order/backorder: shows a notice; two     |
|                           | buyers for the last unit                 |
+---------------------------+------------------------------------------+
| Cart                      | Quantity 0, 1, maximum and more than the |
|                           | stock; remove; mini-cart and cart with   |
|                           | the same total; expired session; going   |
|                           | back                                     |
+---------------------------+------------------------------------------+
| Checkout                  | Guest, create account, logged in;        |
|                           | validation of each field (form-tester);  |
|                           | changing the address recalculates        |
|                           | shipping and taxes; double click on      |
|                           | "Pay"                                    |
+---------------------------+------------------------------------------+
| Taxes                     | By country/state, included in the price  |
|                           | or not, on shipping                      |
+---------------------------+------------------------------------------+
| Shipping                  | Each zone and method, outside any zone,  |
|                           | weight or value limits of each rate,     |
|                           | free shipping right at the minimum, in-  |
|                           | store pickup                             |
+---------------------------+------------------------------------------+
| Coupons                   | Valid, expired, uppercase/spaces, used   |
|                           | up, below the minimum, excluded          |
|                           | products, combined with another, one per |
|                           | customer                                 |
+---------------------------+------------------------------------------+
| Payments                  | Approved, declined, error, 3-D Secure,   |
|                           | leaving the gateway and coming back,     |
|                           | retrying; order status and stock in each |
|                           | case                                     |
+---------------------------+------------------------------------------+
| After-sales               | Order statuses, cancellation, full and   |
|                           | partial refund (returns stock), returns  |
+---------------------------+------------------------------------------+
| Emails                    | Confirmation, shipping, refund,          |
|                           | abandoned cart, password (email-         |
|                           | verifier)                                |
+---------------------------+------------------------------------------+
| Account                   | Signup, login, password recovery,        |
|                           | addresses, orders; a customer cannot see |
|                           | other customers' orders (permissions-    |
|                           | tester)                                  |
+---------------------------+------------------------------------------+
| Multi-currency/language   | Same amount on the storefront, cart,     |
|                           | checkout and email; translations         |
|                           | (translation-analyst)                    |
+---------------------------+------------------------------------------+
| Mobile                    | Full checkout on mobile, numeric         |
|                           | keyboard for card and phone, pay button  |
|                           | visible                                  |
+---------------------------+------------------------------------------+
| SEO and legal             | Product structured data, sitemap,        |
|                           | refund, privacy and terms policies       |
|                           | linked in the checkout                   |
+---------------------------+------------------------------------------+
```

## 3. What usually gets left out

Besides the areas in the previous table, these show up in almost every store and are almost never in the test cases:

```
+-------------------------+------------------------------------------+
| Area                    | What to check                            |
+=========================+==========================================+
| Thank-you page          | Reloading it or going back after paying  |
|                         | does not create a second order or charge |
|                         | again; the order number matches the      |
|                         | admin panel                              |
+-------------------------+------------------------------------------+
| Persistent cart         | The cart survives closing the browser;   |
|                         | on login it merges with the account's    |
|                         | cart without duplicating or losing       |
|                         | products                                 |
+-------------------------+------------------------------------------+
| Concurrency             | Two buyers for the last unit: one buys,  |
|                         | the other gets a clear notice (never     |
|                         | both)                                    |
+-------------------------+------------------------------------------+
| Abandoned cart          | The email arrives with the right cart    |
|                         | and the link restores it; it does not    |
|                         | arrive if the purchase was completed     |
+-------------------------+------------------------------------------+
| Gift cards and balance  | Partial balance, balance that is not     |
|                         | enough (pays the difference), expired,   |
|                         | used in two tabs at once                 |
+-------------------------+------------------------------------------+
| Digital products        | Download link only after paying,         |
|                         | download limit and expiration, no        |
|                         | shipping at checkout                     |
+-------------------------+------------------------------------------+
| Subscriptions           | First charge, renewal, plan change,      |
|                         | pause, cancellation, expired card on     |
|                         | renewal                                  |
+-------------------------+------------------------------------------+
| Customer pricing (B2B)  | Price list per group, per-order          |
|                         | minimums, price logged in and logged out |
+-------------------------+------------------------------------------+
| Installments            | Number of installments per card,         |
|                         | interest and financed total shown the    |
|                         | same at checkout, gateway and email      |
+-------------------------+------------------------------------------+
| Zero-decimal currencies | Chilean pesos, yen: no ".00" and no odd  |
|                         | rounding; the country's thousands        |
|                         | separator                                |
+-------------------------+------------------------------------------+
| Invoicing               | Tax data (tax ID such as EIN, VAT number |
|                         | or CUIT/RUT/NIF; tax status), invoice    |
|                         | type, invoice in the email or in My      |
|                         | account                                  |
+-------------------------+------------------------------------------+
| Addresses               | Countries without states, postal codes   |
|                         | with letters, long address, browser      |
|                         | autofill                                 |
+-------------------------+------------------------------------------+
| Stock alerts            | "Notify me when it's back": arrives only |
|                         | once when there is stock                 |
+-------------------------+------------------------------------------+
| Reviews and wishlists   | Review only from buyers (if that is the  |
|                         | rule), wishlists that survive login      |
+-------------------------+------------------------------------------+
| Analytics and pixels    | The purchase event fires only once (not  |
|                         | when reloading the thank-you page), with |
|                         | the right amount and currency            |
+-------------------------+------------------------------------------+
| Product feeds           | The Google Merchant or Meta feed has the |
|                         | storefront's price, availability and     |
|                         | currency                                 |
+-------------------------+------------------------------------------+
| Cookies and consent     | Without accepting, marketing pixels are  |
|                         | not loaded; the banner does not cover    |
|                         | the pay button on mobile                 |
+-------------------------+------------------------------------------+
```

## 4. The numbers have to add up

In every test purchase, write down and verify: **subtotal + shipping + taxes − discounts = total**, and that the same total shows up in the cart, the checkout, the gateway, the order in the admin panel and the email. Any difference of cents is a finding.

- With **installments**, also: financed total = installment × number of installments, the same at checkout and at the gateway.
- With a **partial refund**: amount refunded + amount still charged = original total; stock comes back only for what was returned.
- With **several currencies**: rounding is applied once (per line or per total, per the business rule); if the rule is not written down, it is `MI-XX`.

## 5. Design techniques that pay off most in a store

With the `design-techniques` skill:

```
+---------------------+------------------------------------------+
| Technique           | Where to apply it                        |
+=====================+==========================================+
| Boundary values     | Free-shipping and coupon minimums        |
|                     | (exact, one cent less), weight brackets  |
|                     | of each rate, stock 0 / 1 / maximum,     |
|                     | maximum quantity per order, minimum      |
|                     | installments                             |
+---------------------+------------------------------------------+
| Equivalence classes | Addresses by shipping zone, cards by     |
|                     | result (approved, declined, insufficient |
|                     | funds, 3-D Secure), product types        |
|                     | (simple, variable, digital,              |
|                     | subscription)                            |
+---------------------+------------------------------------------+
| Decision table      | Discount combinations (coupon +          |
|                     | automatic + free shipping), taxes        |
|                     | included or not by country, guest or     |
|                     | with an account                          |
+---------------------+------------------------------------------+
| State transition    | Order statuses (pending, paid, shipped,  |
|                     | delivered, cancelled, refunded) and      |
|                     | payment statuses; which transition       |
|                     | should not be possible                   |
+---------------------+------------------------------------------+
| Pairwise            | Browser × device × payment method ×      |
|                     | currency when you cannot test everything |
+---------------------+------------------------------------------+
```

## 6. Test data

- **Test cards** from each provider (Stripe, Mercado Pago, PayPal, Adyen…): one approved, one declined, one with 3-D Secure and one with insufficient funds, taken from the provider's documentation.
- **Addresses**: one per shipping zone, one outside every zone, one from each country with different taxes.
- **Products**: one simple, one with variants, one out of stock, one on pre-order, one digital, one with a weight at the limit of a rate, one excluded from coupons.
- **Customers**: guest, with a new account, with an order history and, if applicable, from a B2B group.
- The `test-data-generator` builds them; all of them with the `QA-` prefix and written down so they can be cleaned up.

## 7. Smoke, regression and campaigns

**Smoke test (5–10 min, after each deploy or to know whether the store "is alive"):**

1. The home page, a category and a product page open without errors and without a red console.
2. Searching for a known product returns results.
3. Add to cart, go to checkout and get as far as payment (without paying).
4. A test customer's login and "My account" load.
5. The gateway is in test mode (if it is in live mode, stop and report it).

If any of this fails, it is a **blocker**: there is no point in continuing with the rest until it is fixed.

**Regression after a technical change** (theme or template, app/plugin/module, version or gateway update): run the full main flow —catalog → product page with variants → cart → guest and account checkout → approved and declined payment → order status → email— watching the console, plus the areas the change touches. Ideally it is **automated** (`web-mapper` and then `npm test`, no tokens), adding **visual regression** (`pixel-perfect`) and **cross-browser** (`cross-browser`) when the theme changed. After updating something, purge the cache and check that the change shows.

**Before a campaign or a release (campaign regression):**

1. Buy a simple product and one with variants, as a guest and with an account, with the test gateway: approved and declined.
2. Apply the campaign coupon or discount: valid, before the start date and after the end date (in the store's time zone).
3. Scheduled campaign prices: they start and end at the agreed time.
4. Free shipping right at the minimum and one cent below.
5. Stock of the products on sale and what happens when they sell out.
6. Confirmation and shipping emails.
7. Product page, collection and checkout on mobile: load time (`web-performance-auditor`) and no console errors.
8. If heavy traffic is expected: load test with the `performance-mapper` and check that the cache does not show other people's carts.

## 8. Web performance (what to measure in a store)

Speed is measured with the `web-performance-auditor` (Lighthouse, Core Web Vitals) and load with the `performance-mapper` (guided plan with `performance-guide`); this skill says **where** to look in a store:

- **Pages that matter**: home, **category with many products** (pagination, filters, sorting), **product page** (with variants and gallery), **search results**, cart and checkout. Measuring only the home page is not enough.
- **Core Web Vitals**: LCP (main image of the product page and home banner), CLS (price, button or banners that move while loading), INP (filters, variant selector, add to cart).
- **Image weight**: modern formats (WebP/AVIF), the right size per device, lazy-load below the first screen.
- **Third-party scripts**: apps, modules and pixels that block rendering or bloat the JS; measure with and without them to see how much each one costs.
- **Cache and its correctness**: the cache speeds things up, but **the cart, the checkout and "My account" are not cached**: with two browsers, a cart must not show up in the other one. After changing prices or stock, the change has to show (purge the cache).
- **Backend**: pages with hundreds of SQL queries (N+1 from a module), high TTFB, slow internal APIs (`data-verifier` helps look at the database).
- **Load and peaks**: before a high-traffic campaign, load test the **purchase flow** (not just the home page) and confirm that under load the cache does not show another buyer's data.

## 9. Store security (what to review)

Scanning and exploitation are done by the `security-analyst` (passive) and the `web-pentester` (active and authorized); this skill lists the **store-specific** risks so they do not slip through:

- **Price and quantity tampering**: change the price, the quantity (0, negative, huge) or the total in the call that adds to the cart or creates the order. The server has to recalculate and reject, never trust the value the client sends.
- **IDOR / another customer's data**: view **someone else's** order, invoice, address or download by changing the id in the URL or the API; "My account" and invoices only for their owner.
- **Coupon and voucher abuse**: reusing a single-use coupon, applying it several times, guessable codes, a gift card balance spent in two tabs at once.
- **Webhooks and payment notifications**: the gateway notification is validated (signature/HMAC) and processed **only once**; a payment cannot be marked approved by forging the callback.
- **Exposure**: a gateway in live mode in QA, an accessible admin panel or debug mode, and `logs`, `.env` or backups downloadable by URL are findings.
- **PII and secrets**: personal data or tokens in the URL, the email or the HTML; API keys with more permissions than needed (least privilege).
- **Brute force and abuse**: login, password recovery, coupon application and account signup with attempt limits (rate limiting) and captcha where appropriate.
- **Transport**: HTTPS on the whole site, security headers and `Secure`/`HttpOnly` session cookies.
- **Payments (PCI)**: card data goes straight to the gateway (iframe/tokenization) and the store does not store it. For money, idempotency and reconciliation, the `wallet-tester`.

## 10. Which agent covers each part

```
+---------------------------------------+--------------------------------------+
| Part                                  | Tool or agent                        |
+=======================================+======================================+
| Purchase flows in the browser         | Playwright MCP (e2e-execution skill) |
+---------------------------------------+--------------------------------------+
| Checkout validations                  | form-tester                          |
+---------------------------------------+--------------------------------------+
| Store emails                          | email-verifier                       |
+---------------------------------------+--------------------------------------+
| Roles (customer, manager)             | permissions-tester                   |
+---------------------------------------+--------------------------------------+
| Product page and checkout speed       | web-performance-auditor              |
+---------------------------------------+--------------------------------------+
| Checkout accessibility                | accessibility-analyst                |
+---------------------------------------+--------------------------------------+
| Visual changes to the theme           | pixel-perfect                        |
+---------------------------------------+--------------------------------------+
| Safari and Firefox                    | cross-browser                        |
+---------------------------------------+--------------------------------------+
| Translations and price formats by     | translation-analyst                  |
| country                               |                                      |
+---------------------------------------+--------------------------------------+
| Gateway down or slow                  | resilience-tester                    |
+---------------------------------------+--------------------------------------+
| High-traffic campaigns                | performance-mapper                   |
+---------------------------------------+--------------------------------------+
| Orders and stock in the database      | data-verifier                        |
+---------------------------------------+--------------------------------------+
| Test data                             | test-data-generator                  |
+---------------------------------------+--------------------------------------+
| Security                              | security-analyst, web-pentester      |
+---------------------------------------+--------------------------------------+
| Money, idempotency and reconciliation | wallet-tester                        |
+---------------------------------------+--------------------------------------+
| Regression without tokens             | web-mapper and then npm test         |
+---------------------------------------+--------------------------------------+
```

## 11. How to report a store bug

Besides the project template (`bug-report-generator`), a store bug includes: the **test order number**, the **amounts** (subtotal, shipping, taxes, discounts, expected and actual total), the **coupon** or discount, the **address or zone**, the **currency or market**, the **payment method and test card** (only its type, never the full number of a real one), the **device and browser** and whether it was a **guest or an account**.

## 12. Typical questions for the PO

When the story does not say, they are `MI-XX`:

- Is rounding per line or per total? Are prices shown with taxes included?
- When is stock deducted: when adding to the cart, when paying or when the payment is confirmed?
- How long is stock reserved for an unpaid order?
- Can coupons be combined with each other and with automatic discounts?
- Is free shipping calculated before or after the discount?
- What happens to an order if the payment stays pending (bank transfer, cash)?
- Can people buy without an account? Which tax data is mandatory?
- Does a partial refund return the shipping? And the stock?

## 13. Typical bugs

- The email or order total does not match the checkout total (rounding, taxes on shipping).
- A coupon applied twice or on excluded products.
- A sold-out product that can be added through a direct URL or from the mini-cart.
- A payment approved at the gateway with the order in "pending" or "failed" (a webhook or notification that did not arrive).
- Reloading the thank-you page creates a duplicate order or fires the purchase event again.
- Two buyers get the last unit.
- A refund that does not return the stock.
- An address change that does not recalculate shipping.
- Free shipping still offered after a coupon brings the subtotal below the minimum.
- A compare-at price lower than the sale price.
- A different currency between storefront and checkout, or ".00" in a zero-decimal currency.
- A scheduled sale that starts or ends at a different time (server time zone).
- A cart that is lost or duplicated on login.
- A checkout that breaks after updating the theme or a plugin/app.
