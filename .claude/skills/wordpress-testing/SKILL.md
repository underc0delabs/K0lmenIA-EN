---
name: wordpress-testing
description: How to test a WordPress site and a WooCommerce store — environments (staging, copy of production, WP-CLI), plugins and themes (updates, conflicts, child theme, overridden and outdated WooCommerce templates), block editor, cache, WP-Cron, the REST API and the Store API, the WooCommerce REST API with a read key (system status), classic vs. block checkout and their settings (guest, create account), gateways in test mode and offline payments, HPOS order storage and plugin compatibility, Action Scheduler (failed actions), product types (grouped, external, virtual, downloadable, subscriptions, bookings), shipping zones and methods, taxes and tax classes, coupons, stock and backorders, order statuses and refunds, WooCommerce emails and SMTP, webhooks that get disabled, multisite and multi-language (WPML, Polylang), builders and block themes, backup, automatic updates and troubleshooting mode, non-store sites (forms, comments, redirects, SEO, media), roles (customer, shop manager), how to automate it with Playwright, typical bugs and questions for the PO. Used by the wordpress-tester and the mappers when they automate a WordPress or WooCommerce site.
---

# Testing on WordPress and WooCommerce

In WordPress, almost everything that breaks comes from **the combination of plugins, theme and versions**: an update changes something somewhere else. That is why each update is tested on **staging** with the regression of the main flow. It builds on the `ecommerce-testing` skill.

## 1. Environments

- **Staging** or a local copy (Docker, Local, WP-CLI). If it is a copy of production, it may have **real customers and orders**: don't send emails to customers (use Mailpit, see `email-verifier`) and mask the data in screenshots.
- **WP-CLI** (`wp plugin list`, `wp core check-update`, `wp cron event list`) gives the real state of the site; only read commands are used.
- The **permalink** has to be in a "pretty" mode for `/wp-json/` to work.

## 2. Plugins and theme

- **Updates**: an outdated plugin is not a bug, but **updating it is a risk**: it is updated on staging and the regression of catalog, cart, checkout and My Account is run, watching the console.
- **Conflicts**: if something fails, deactivate plugins one by one (on staging) or test with a default theme to isolate.
- **Child theme**: changes go in the child; if the parent was edited, they are lost on update.
- **Overridden WooCommerce templates** by the theme (`theme/woocommerce/...`): if their version is old ("outdated templates" in the system status), the cart, the checkout or the emails may look wrong or lose fields. It is one of the most important findings.
- **Cache** (plugin, server or CDN): the cart, the checkout and My Account are **not** cached; test with two browsers that one cart doesn't show up in another. After changing prices or the theme, purge the cache and verify the change is visible.
- **Before updating**: backup (database and files) and a way to roll back. An update is tested on staging and only then moved to production.
- **Automatic updates** of plugins or of WordPress in production: they update without going through staging. If they are active on critical plugins (WooCommerce, gateways, shipping), it is a risk to discuss with the team.
- **Isolate a conflict without affecting visitors**: the *Health Check & Troubleshooting* plugin has a troubleshooting mode that deactivates plugins and changes the theme only for your session. *Tools → Site Health* summarizes configuration problems.
- **Builders** (Elementor, Divi, WPBakery) and **block themes** (full site editor): a change in a template or a global part (header, footer) shows up on every page that uses it; test several pages, not just the edited one.

## 3. WP-Cron

- WP-Cron runs when someone visits the site. Without visits or if it is disabled (`DISABLE_WP_CRON`) without a server cron, unpaid orders aren't canceled, scheduled sales don't start or end and some emails don't go out.
- Events overdue by more than an hour in `wp cron event list` = the cron isn't running.
- **Action Scheduler** (WooCommerce → Status → Scheduled Actions, or `wp action-scheduler action list --status=failed`): the queue where WooCommerce and its extensions leave deferred emails, webhooks, subscription renewals and reports. **Failed** actions or **pending ones with a past-due date** are tasks that didn't run.

## 4. WooCommerce: checkout

- **Classic checkout (shortcode) or block checkout**: many gateways, extra fields and shipping plugins only work with one. Verify which one the page uses and that each checkout plugin is compatible.
- The **Cart, Checkout and My Account** pages have to exist, be published and have their shortcode or block (the system status says so).
- **Gateways**: each one in **test mode** (Stripe test, Mercado Pago sandbox, PayPal sandbox). Approved, declined, 3-D Secure, going back from the gateway and retrying. After paying: order status (processing), stock decremented, order note and email.
- A gateway in **real mode** in QA is a finding: you don't pay with it.
- **Checkout settings** that change the flow: allow guest purchase, create an account during payment, generate the password automatically, log in during payment, required terms page. Each combination is a path.
- **Offline payments** (bank transfer, check, cash on delivery): the order stays **on hold**; if "hold stock" is short and the cron runs, it cancels on its own before the customer transfers.

## 5. Order storage (HPOS)

- WooCommerce stores orders in **its own tables** (HPOS, High-Performance Order Storage) instead of WordPress posts. In *WooCommerce → Settings → Advanced → Features* it says which mode is used, whether the **synchronization** with the old tables is on and which plugins **are not compatible**.
- A plugin incompatible with HPOS may not see new orders (invoicing, shipping, ERP, reports). With HPOS active, test each plugin that reads or writes orders: it creates its data, the order shows complete in the admin and in My Account, and the order search finds it.
- When **switching modes** (enabling HPOS or disabling the synchronization) on staging: the old orders stay visible with their notes, refunds and metadata.

## 6. Product types

- **Simple, variable, grouped and external/affiliate**: the grouped one adds several at once (quantities per child); the external one goes to another site and doesn't go through the cart.
- **Virtual** (no shipping) and **downloadable**: the checkout doesn't ask for shipping; the download link appears only with a paid order (processing or completed), respects the **download limit** and the **expiration**, and can't be opened without a session if the rule requires it.
- Extensions with their own products: **Subscriptions** (renewal, plan change, cancellation, expired card), **Bookings** (availability, overlapping bookings, time zone), **Memberships** (content and prices per plan), **Product Add-Ons** (extra fields that add to the price).

## 7. Shipping, taxes and coupons

- **Shipping zones**: the first zone that matches the address is chosen, in order; an address that doesn't match any falls into "Rest of the World". A zone with no enabled methods leaves no shipping.
- **Free shipping** with a minimum: right at the minimum, one cent below and with a coupon that drops the subtotal below the minimum.
- **Taxes**: prices with or without taxes (`woocommerce_prices_include_tax`), by country and state, on shipping, and rounding per line or per total. **Tax classes** (standard, reduced rate, zero rate) per product; how prices are shown in the shop and in the cart (they can differ: with taxes in the shop and without taxes in the cart confuses the buyer); "calculate tax based on" the shipping address, the billing address or the shop's.
- **Coupons**: percentage, fixed cart, fixed product; expired, used up, individual use, excluded products or categories, minimum and maximum, restriction by email.

## 8. Stock and orders

- **Manage stock** per product or variation; **backorders** (no, notify, yes). Low stock and out of stock trigger emails to the administrator.
- **Order statuses**: pending payment, processing, on hold, completed, canceled, refunded, failed. An unpaid order cancels on its own after the "hold stock" time (if the cron runs).
- **Refund** full and partial: returns stock if marked, and the gateway refunds the money only if it supports it.

## 9. WooCommerce emails

New order (to the shop), canceled and failed order (to the shop), order on hold, processing, completed, refunded, note to the customer, password reset and new account. They are tested with the `email-verifier` and Mailpit.

- Without an **SMTP** plugin (WP Mail SMTP, FluentSMTP…) or a sending service, WordPress sends with the server's mail function: many emails don't go out or go to spam. Verify they go out through the configured service.
- On **multi-language** sites, the email goes out in the customer's language (the order's), not the administrator's.

## 10. Multisite and multi-language

- **Multisite**: each site in the network has its active plugins, users and roles; a plugin activated "network-wide" affects everyone. Test on the relevant network site.
- **WPML or Polylang** (with WooCommerce Multilingual or similar): translated products, categories and slugs, the language switcher keeps the cart, the checkout and the emails in the chosen language, and the prices per currency if there is multi-currency. The translations are reviewed by the `translation-analyst`.

## 11. Webhooks

WooCommerce **disables a webhook** after several consecutive delivery failures (it becomes `disabled`): the ERP or the integration stops receiving orders without anyone noticing. Each webhook signs the body with **X-WC-Webhook-Signature**.

## 12. Roles

- **Customer**: My Account, their orders and addresses; never other people's orders (changing the ID in the "view order" URL).
- **Shop manager** (`shop_manager`): orders, products and coupons, but not plugins or administrator users.
- The `permissions-tester` tests it.

## 13. WordPress sites that aren't a store

- **Forms** (Contact Form 7, Gravity Forms, WPForms, Elementor): validations (`form-tester`), confirmation message, that the email reaches the right person (`email-verifier`) and that the antispam doesn't block legitimate submissions.
- **Comments**: moderation, the first comment stays pending if that is the rule, links are flagged as spam.
- **Menus, search and 404**: all the menu links open (`web-explorer`), search finds posts and pages, the 404 offers a way forward.
- **Redirects** (the Redirection plugin or the SEO one): old URLs redirect with 301 after changing a slug or migrating.
- **SEO** (Yoast, Rank Math): title and description of each page type, canonical, the plugin's sitemap and that "Discourage search engines from indexing this site" (Settings → Reading) is on in staging and **off** in production.
- **Media**: generated image sizes, lazy loading, formats (WebP/AVIF) and alt text (`accessibility-analyst`).
- **Users and privacy**: registration (if it is open, with what default role), export and erase personal data (Tools → Export/Erase Personal Data).

## 14. APIs for the survey (read-only)

- **`/wp-json/`**: site name and namespaces (which plugins expose an API: `wc/v3`, `yoast/v1`, `contact-form-7/v1`…).
- **Store API** (`/wp-json/wc/store/v1/products`): public catalog; prices come in **minor units** (`1599` with `currency_minor_unit: 2` = 15.99).
- **WooCommerce REST API** (`/wp-json/wc/v3/...`) with a **read-only** key (WooCommerce → Settings → Advanced → REST API, *Read* permission): `system_status`, `payment_gateways`, `shipping/zones`, `coupons`, `webhooks`, `settings/general`, `products`.

## 15. Automate with Playwright (web-mapper)

- Block checkouts are React: wait for it to finish recalculating (the summary spinner) before reading the total.
- The Stripe and other gateways' card fields go in **iframes**.
- `?add-to-cart=<id>` adds directly to the cart: useful to set up the scenario quickly.
- Nonces expire: don't record URLs with `_wpnonce`.

## 16. Typical bugs

- The checkout stops working after updating WooCommerce because the theme has old templates.
- A cache plugin that shows another visitor's cart.
- A paid order that stays "pending" because the gateway's notification doesn't arrive (outbound calls blocked, notification URL misconfigured).
- A disabled webhook and the ERP with no orders.
- Scheduled sales that don't start because the cron isn't running.
- Free shipping that keeps being offered after applying a coupon that drops the subtotal below the minimum.
- An invoicing or shipping plugin that doesn't see new orders because it isn't HPOS-compatible.
- Failed scheduled actions: subscription renewals or deferred emails that never went out.
- A critical plugin that updated itself in production and broke the checkout.
- Bank-transfer orders canceled on their own before the customer pays ("hold stock" too short).
- Download links that don't expire or that open without having paid.
- Emails that don't arrive because the site has no SMTP configured.
- Production with "Discourage search engines" enabled after copying staging.

## 17. Typical questions for the PO (WordPress / WooCommerce)

In addition to those of the `ecommerce-testing` skill, when it isn't written down they are `MI-XX`:

- Is guest purchase allowed? Is the account created during payment?
- How many minutes is stock held for an unpaid order? Does it apply to bank transfers?
- Are backorders allowed and on which products?
- Are prices entered with or without taxes? How are they shown in the shop and in the cart?
- Which plugins are in the scope of the test and who updates them?
- Are automatic updates active in production?
- How long and how many times can a downloadable product be downloaded?

## 18. Smoke, regression, performance and security (WordPress / WooCommerce)

The generic part (the five test types) is in `ecommerce-testing`; here, what is specific to WordPress.

- **Smoke** (staging): home, a category and a product page without the WordPress "critical error" or PHP notices; `/wp-json` responds; add to cart and reach the checkout; "My Account" loads; the gateway in test mode. In WooCommerce, the **system status** (WooCommerce → Status) is the background smoke: no database pending update, no outdated templates, with `remote_post` OK.
- **Regression**: WooCommerce is sensitive to the **combination of plugins, theme and versions**. After **updating** WordPress, WooCommerce, the theme or a plugin (on staging, with a backup), run the regression of catalog → cart → checkout (classic or block) → payment → My Account watching the console; add `pixel-perfect` and `cross-browser` if the theme changed. The *Health Check & Troubleshooting* mode isolates a conflict without affecting visitors.
- **Performance**: object cache (Redis/Memcached) and page cache (plugin/server/CDN), bloated **autoloaded options** (`autoload`), overloaded **WP-Cron**, number of plugins and their weight (Query Monitor for the query count and the slow queries), HPOS vs. posts for orders. The cart, the checkout and My Account are not cached: verify it. Measure with `web-performance-auditor` and, for load, `performance-mapper`.
- **Security**: **outdated plugins/theme/core** are the main source of CVEs (the survey flags the ones with an update available); **user enumeration** through `/wp-json/wp/v2/users` and `?author=1`; **XML-RPC** (`xmlrpc.php`) for brute force and amplification; `wp-login.php` with no attempt limit; `wp-config.php`, `debug.log` and backups accessible by URL; file permissions; nonces/CSRF in forms; the **WooCommerce REST API** must not expose orders without a key; a customer doesn't see other people's orders (`?view-order=` / IDOR). The active security, with `security-analyst` / `web-pentester`.
