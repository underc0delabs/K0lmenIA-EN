---
name: vtex-testing
description: How to test a VTEX store — accounts, environments and workspaces (master vs. QA workspaces, bindings), storefront (Store Framework/VTEX IO, FastStore, legacy CMS Portal), VTEX IO apps and versions, the Catalog System (products, SKUs, categories, specifications, trade policies/sales channels), Pricing (price tables, fixed prices), Logistics (inventory by warehouse, docks, shipping policies/SLAs, carriers), Promotions & Taxes, Payments (payment conditions, gateways, antifraud, installments), the Checkout and the orderForm (cart, marketing data, totalizers), OMS/orders and statuses, Subscriptions, Master Data (CRM and entities), the marketplace/seller model (1P and 3P), B2B, multi-currency and multi-language per binding, the smoke test, regression after publishing an app or changing the theme, performance (VTEX IO/SSR, CDN, orderForm and search latency), security (AppKey/AppToken with least privilege, orderForm tampering, IDOR in OMS/Master Data, antifraud, workspace exposure), the public and read-only admin APIs, how to automate it with Playwright, typical bugs and questions for the PO. Used by the vtex-tester and the mappers when they automate a VTEX store.
---

# Testing on VTEX

VTEX is a **SaaS, API-first and natively marketplace** platform (widely used in LATAM). As in Shopify, VTEX handles the infrastructure, the checkout and much of the payments; what changes from one store to another (and where the bugs are) is **the catalog and its trade policies, the promotions, the shipping, the payment methods, the VTEX IO apps and the theme**. It builds on the `ecommerce-testing` skill.

## 1. Account, environments and workspaces

- A store is an **account** (`myaccount`). The admin lives at `myaccount.myvtex.com`; the APIs, at `myaccount.vtexcommercestable.com.br`.
- **Workspaces**: isolated copies of the account. **`master` is production**. For QA you use your **own workspace** (`qa--myaccount.myvtex.com`): same data, isolated changes. It is the equivalent of staging; **you never run destructive tests against master**.
- **Bindings and sales channels (trade policies)**: an account can have several storefronts (domains/languages/currencies) tied to **sales channels**. A product is sold on a channel only if it has that trade policy; test **each channel**.
- **Sales channel in the URL/API**: `?sc=1` sets the channel; prices and availability change per channel.

## 2. Storefront and apps (VTEX IO)

- Three generations of storefront: **Store Framework** (VTEX IO, React, SSR), **FastStore** (Next.js, headless) and the **legacy CMS Portal**. Confirm which one it uses: the theme, the deploy and where it breaks all change.
- **VTEX IO** are versioned apps that are installed per workspace (`vtex list`); a new app is tested in a workspace before promoting to master. A render error (`RenderRuntime`, blank screen, GraphQL error) is a bug.
- Review, intelligent-search (**Intelligent Search**), wishlist apps and pixels are usually the ones that break the most.

## 3. Catalog System

- **Product → SKUs** (VTEX's variants): each SKU has its reference (RefId), EAN, images, dimensions and specifications. A SKU without a price or without stock in the channel can't be bought.
- **Categories, brands and specifications** (fields and filters): products without an active category or without a required specification don't appear properly in the catalog or the filters.
- **Trade policies**: the SKU has to be in the channel's trade policy to be sold there.
- **Indexing**: after loading or changing products, the search (Intelligent Search) takes time to index; a product that is "new and doesn't appear" may be indexing, not a bug.

## 4. Pricing

- Prices live in **price tables** per channel/list; there are also **fixed prices** by date or quantity. The `Price` (with promo) and the `ListPrice` (struck through): the struck-through one has to be **higher** than the price.
- A SKU **without a price** in the channel's table is not sold even if it has stock.

## 5. Logistics (inventory and shipping)

- **Inventory by warehouse** and **docks**; the available stock depends on the warehouse that covers the buyer's region.
- **Shipping policies (SLAs)** and **carriers**: each one with region, cost, weight and time. **With no active SLA you can't buy with shipping.** Test by **region/ZIP (postal code)**, free shipping, pickup point and the recalculation when the address changes.

## 6. Promotions & Taxes

- **Promotions** (regular, combo, "buy together", progressive, by coupon): dates, channel, conditions and **accumulation** (which promos combine). Misconfigured accumulation is the typical cause of miscalculated totals.
- **Coupons**: valid, expired, by channel, usage limit.
- **Taxes**: by region or integrated with a tax provider; the total has to reflect them.

## 7. Payments

- **Payment conditions** and **gateways** per channel; each method in **sandbox** (approved, declined, 3-D Secure) and, if applicable, **installments** (interest and total financed equal across checkout, gateway and email).
- **Antifraud**: it must not reject a legitimate test purchase; review the analysis flow (approved/denied/under analysis).
- A payment condition in **real mode** in QA is a finding.

## 8. Checkout and orderForm

- The cart and the checkout are the **orderForm** (API `/api/checkout/pub/orderForm`): items, prices, shipping, payment, **marketing data** (coupons/UTM) and totalizers.
- **The books have to balance**: the orderForm total = the checkout's = the gateway's = the order's (OMS) = the email's. Any difference is a finding.
- Test **guest and with an account**, an address change that recalculates shipping and taxes, double-clicking pay (doesn't duplicate the order), and the confirmation page (reloading it doesn't create another order or re-trigger the purchase pixel).

## 9. OMS, post-sale and subscriptions

- **OMS**: order statuses (payment-pending, payment-approved, handling, invoiced, shipped, delivered, canceled); that the transitions and the emails go out at the correct moment.
- **Cancellation and return**: restock and refund according to the rule.
- **Subscriptions** (if the app is present): first charge, renewal, change and cancellation.
- **Marketplace/seller**: VTEX is natively marketplace (1P and 3P); an order with different sellers is split and each seller handles its own shipping and status.

## 10. Master Data and B2B

- **Master Data** stores customers (CL), addresses (AD) and custom entities. A customer sees only their own; test that someone else's data isn't accessed through the API (IDOR).
- **B2B** (VTEX B2B Suite): organizations, costs and roles; price lists and order approval per organization.

## 11. Smoke test

Fast and blocking (in a QA workspace, not in master):

1. The home, a category and a product page open with no render error or broken console.
2. The search (Intelligent Search) returns results.
3. Add a SKU to the cart and reach the checkout (orderForm with the item and the total).
4. Login of a test customer and "My orders" load.
5. There is at least one active sales channel, one shipping SLA and one payment condition (in sandbox).

## 12. Regression

- After **promoting a VTEX IO app**, **changing the theme** or touching catalog/prices/promos, run the complete purchase flow in the QA workspace before promoting to master: catalog → product page with SKUs → cart → checkout guest and with account → payment approved and declined → order status → email, watching the console.
- Add **visual regression** (`pixel-perfect`) and **cross-browser** (`cross-browser`) when the theme changed, and compare the QA workspace against master.

## 13. Performance

- Measure with the `web-performance-auditor` (CWV) on home, category with filters, product page and search; for load, the `performance-mapper` (`performance-guide`).
- Specific to VTEX: the **VTEX IO SSR** and the **CDN**, the **orderForm latency** and that of **search (Intelligent Search)**, the impact of each VTEX IO app (blocks render / inflates the JS). The checkout and the orderForm are not cached.

## 14. Security

The scanning and exploitation are done by the `security-analyst` and the `web-pentester`; specific to VTEX:

- **AppKey/AppToken with least privilege** (License Manager roles), never in the front or in the repo; rotation.
- **orderForm tampering**: changing price, quantity or marketing data in the API; the server has to recalculate and reject.
- **IDOR** in OMS (`/api/oms/.../orders/{id}`) and Master Data: not seeing other people's orders, addresses or documents.
- **Antifraud** active and payment **webhooks/hooks** validated and processed only once.
- **Workspaces and exposure**: a QA workspace with sensitive data publicly accessible; `pvt` endpoints that respond without credentials.

## 15. APIs for the survey (read-only)

- **Public** (no credentials): Catalog System `GET /api/catalog_system/pub/products/search` (channel catalog with SKUs, price and availability in `commertialOffer`), `GET /api/catalog_system/pub/portal/pagetype/...`, and the `GET /api/checkout/pub/orderForm/{id}` of an existing orderForm.
- **Admin** (`X-VTEX-API-AppKey` and `X-VTEX-API-AppToken` headers, read-only): sales channels (`/api/catalog_system/pvt/saleschannel/list`), shipping policies (`/api/logistics/pvt/shipping-policies`), promotions (`/api/rnb/pvt/benefits/calculatorconfiguration`), inventory, pricing and OMS. Never write methods.
- The `npm run vtex` tool always surveys the storefront and the public catalog, and with AppKey/AppToken it adds channels, shipping and promotions.

## 16. Automate with Playwright (web-mapper)

- Locate by role and accessible name; in Store Framework the block `class`es (`vtex-store-components-*`) change when the app is updated.
- Wait for the **orderForm** calls (`/api/checkout/pub/orderForm`) to respond before reading the total or the cart counter; the search calls Intelligent Search.
- Test against the **QA workspace** (`qa--myaccount.myvtex.com`), not master.
- Dismiss the cookie notice and the newsletter popups at the start of the scenario.
- Captcha on login or contact: it is not bypassed; ask for it to be disabled in the QA workspace or leave those steps as manual.

## 17. Typical VTEX bugs

- A product without a price or without stock in the channel that still appears (or the other way around: with stock but outside the trade policy).
- Promotions that accumulate when they shouldn't, or that don't respect the channel or the date.
- A shipping SLA with no coverage for a region → you can't buy there.
- An orderForm total different from the OMS order's (taxes, shipping, promo).
- A VTEX IO app promoted to master that breaks the product page or the checkout.
- Purchase pixel duplicated when reloading the confirmation.
- Struck-through price (ListPrice) lower than or equal to the selling price.
- A marketplace order with several sellers that isn't split well.
- AppKey/AppToken with excess permissions or exposed in the front.
- A QA workspace with production data publicly accessible.

## 18. Typical questions for the PO (VTEX)

In addition to those of the `ecommerce-testing` skill, when it isn't written down they are `MI-XX`:

- Which storefront does it use (Store Framework, FastStore, legacy)?
- Which sales channels (trade policies) are in the test and with what currency each one?
- Which promotions can accumulate with each other?
- Which payment methods and in what mode (sandbox)? Are there installments?
- Is there a marketplace with 3P sellers? And subscriptions or B2B?
- Which workspace is it tested on (never master)?
- Which VTEX IO apps are in scope and which are third-party?
