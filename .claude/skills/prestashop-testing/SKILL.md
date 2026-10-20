---
name: prestashop-testing
description: How to test a PrestaShop store (1.6, 1.7 and 8.x) — environments and smoke testing with Docker, back office (BO) and front office (FO), Smarty themes and templates (.tpl, parent/child theme, overriding by the theme), modules and overrides (hooks, conflicts, native and third-party modules, the override/ folder), cache and performance (Smarty cache and force compile, combine-compress-cache CSS/JS, PS_CACHE, profiling and developer mode _PS_MODE_DEV_, SQL query count), friendly URLs and .htaccess, the checkout (guest, 5 steps vs. one page, carriers and zones, mandatory terms), gateways in test mode, products with combinations and stock (quantity, deny/allow orders when out of stock), specific prices and cart rules (vouchers), taxes and rounding, multistore (multishop) and multi-language/multi-currency, SEO and 301 redirects, transactional emails, the read-only Webservice API, how to automate it with Playwright, typical bugs and questions for the PO. Used by the prestashop-tester and the mappers when they automate a PrestaShop store.
---

# Testing on PrestaShop

PrestaShop is **self-hosted (PHP + MySQL)**: you control the server, the database, the theme and the modules. Unlike Shopify, almost everything that breaks comes from **the combination of modules, theme and configuration**, and from how **performance** is set up (cache and compilation). It builds on the `ecommerce-testing` skill.

Live versions: **1.6** (legacy, classic 5-step checkout), **1.7** and **8.x** (Symfony in the BO, one-page checkout, themes based on `classic`). Confirm the version before testing: it changes the BO, the checkout and the hooks.

## 1. Environments and smoke test

- Test on **staging** or a **local copy** (Docker is the fastest): never test orders against production.
- **Spin up PrestaShop locally with Docker** (installation smoke test):
  ```bash
  docker run -ti --name ps -e DB_SERVER=auto -p 8080:80 prestashop/prestashop:8
  # or with docker-compose: a mysql/mariadb service + a prestashop one pointing to DB_SERVER
  ```
  Smoke test after starting it: the **FO** opens at `/`, the **BO** at `/admin-XXXX` (the admin folder gets renamed automatically), you can log in with the installer's user, no PHP errors are visible and `var/logs/` (8.x) or `log/` has no fatals.
- **Maintenance mode** (`PS_SHOP_ENABLE = 0`, BO → Shop Parameters → General → Maintenance): the FO is closed except for the IPs in `PS_MAINTENANCE_IP`. On staging it's often like that on purpose; confirm before reporting it.
- **Demo data**: the installation ships a demo catalog ("Hummingbird" products, categories). If the real store has them, it's a cleanup bug.

## 2. Back office (BO) and front office (FO)

- What the business configures lives in the **BO**; what the customer sees, in the **FO**. Almost every test crosses both: you change something in the BO and verify it in the FO (with the cache cleared).
- **8.x / 1.7** have the BO in **Symfony** (new routes) coexisting with legacy pages; a Symfony error looks different from a legacy one. Check `var/logs/*.log`.
- **Multistore** is enabled in the BO (Advanced Parameters → Multistore) and adds a store selector at the top: each change can be "for all shops" or "for this shop". It's a typical source of "I configured it and it doesn't show".

## 3. Themes and templates (Smarty)

- The default theme in 1.7/8 is **`classic`**; themes are based on it. Templates are **Smarty** (`.tpl`) in `themes/<theme>/templates/`.
- **Child theme**: changes go in the child (it inherits from `classic` or the parent); if the parent was edited, the changes are lost when updating it.
- **Overridden templates**: a theme or a module can override `.tpl` files from the core or from another module (`themes/<theme>/modules/<module>/`). If they're left over from an old version, the cart, the checkout or the product page may look or behave wrong. It's one of the most important findings (equivalent to WooCommerce's "outdated templates").
- **Visible Smarty/PHP errors** (`Fatal error`, `Notice`, `Warning`, or a **PrestaShop exception** with a stack trace) show up on the page: they almost always mean that **developer mode was left on** (see §5) and they're bugs in production.
- After editing a `.tpl`, you have to **recompile/clear** (see §5) for the change to show.

## 4. Modules and overrides

- **Modules** add features and plug in through **hooks** (`displayHeader`, `displayProductAdditionalInfo`, `actionValidateOrder`, …). A badly built module hanging off a hook breaks that area on every page.
- **Conflicts**: if something fails, disable modules one at a time in the BO to isolate it. Payment, shipping, translation and page builder modules are the ones that break things most.
- **Overrides** (`override/classes/...`, `override/controllers/...`): PHP that overrides core classes. Two modules overriding the same class **clash**. If the store has `PS_DISABLE_OVERRIDES = 1`, overrides aren't applied (it may be intentional for security, or a bug if something stopped working). After installing or updating modules it's a good idea to delete `cache/class_index.php`.
- **Leftovers from uninstalled modules**: overridden `.tpl` files, overrides or hooks still pointing to files that no longer exist (fatals or 404s in the console).
- After installing/updating a module: regression of the product page, cart, checkout and "My account", watching the console and `var/logs/`.

## 5. Cache, compilation and performance

This is specific to PrestaShop and weighs a lot (BO → Advanced Parameters → **Performance**):

- **Smarty · Template compilation**: in production it must be *"Recompile templates if the files have been updated"* (`PS_SMARTY_FORCE_COMPILE = 0`). *"Force compilation"* (1 or 2) makes the **whole** site slow.
- **Smarty · Cache** (`PS_SMARTY_CACHE`): enabled in production.
- **Combine, compress and cache (CCC)** CSS (`PS_CCCCSS`) and JS (`PS_CCCJS`): reduces the number of requests and bytes. Enable them and **verify that the theme doesn't break** (that's the typical risk of enabling CCC).
- **PrestaShop cache** (`PS_CACHE_ENABLED`, with FS/Memcached/Redis depending on the server).
- **Developer mode** (`_PS_MODE_DEV_` in `config/defines.inc.php`): turns on errors and profiling and disables part of the cache → **slow and leaks information**. In production it must be **off**. `prestashop.py` with `--local` detects it.
- **Profiling** (`_PS_DEBUG_PROFILING_`): shows times and the **SQL query count** per page — useful for finding pages with hundreds of queries (a module's N+1). Staging only.
- Measure the real speed with the **`web-performance-auditor`** (Lighthouse) on the home page, a **category with many products** (pagination/filters) and a **product page**, with and without CCC and cache. For load, the **`performance-mapper`** (guided plan with `performance-guide`).

## 6. Friendly URLs and .htaccess

- **Friendly URLs** (BO → Traffic & SEO → SEO & URLs) need `mod_rewrite` and a generated `.htaccess`. If they're enabled but the `.htaccess` wasn't regenerated, product and category pages return 404.
- After changing the `link_rewrite` of a product or category, the old URL must **redirect with a 301**, not return 404 (BO → SEO, or a redirects module).

## 7. Checkout

- **1.7 / 8.x**: **one-page** checkout (`PS_ORDER_PROCESS_TYPE = 1`) with sections (personal information, address, carrier, payment). **1.6**: **5 steps**. Confirm which one it is.
- **Guest checkout** (`PS_GUEST_CHECKOUT_ENABLED`): if enabled, you can buy without creating an account; if not, it forces signing up or logging in. Test the path that applies.
- **Carriers and zones**: each carrier has zones, ranges by weight or by price, and a cost (or free). **Without any active carrier you can't buy.** Products in one cart that fall under different carriers, and changing the address to another zone that recalculates shipping.
- **Terms and conditions** (`PS_CONDITIONS = 1`): the checkbox is mandatory and its link opens the terms CMS page.
- The **total** has to match in the cart, checkout, order (BO) and email: subtotal + shipping + taxes − discounts.

## 8. Payments

- Each gateway in **test/sandbox mode** (Stripe test, Redsys test, PayPal sandbox, Mercado Pago sandbox). Approved, declined, 3-D Secure, going back from the gateway and retrying.
- A gateway in **live mode** on QA is a finding: don't pay with it.
- Native payment modules for testing without a real gateway: **"Bank transfer"** and **"Cash on delivery"** leave the order in a pending-payment status — useful for testing the order flow without charging.
- After paying: **order status**, stock deducted, invoice/receipt, order note and **email** (see §13).

## 9. Products, combinations and stock

- **Combinations** (sizes/colors): each combination changes price, reference, image and **stock**; an out-of-stock or nonexistent combination can't be added.
- **Stock** (`stock_availables`): quantity per product/combination. **"When out of stock"** per product: *deny orders* (can't be bought), *allow orders* (sold without stock → overselling) or *use the store's default behavior* (`PS_ORDER_OUT_OF_STOCK`). Test all three.
- **Specific prices** (quantity discounts, by customer group, by date range, by store): the displayed price and the cart price must respect them; watch out for the strikethrough.
- **Products**: for sale with price 0, without an image, without a reference (SKU), without a tax group, not available for order but visible. `prestashop.py` flags them.

## 10. Taxes, rounding and currency

- **Tax rule groups** per country/state; `PS_TAX` enables or disables the calculation. Prices with and without tax (`price` is tax-excluded).
- **Rounding** (`PS_ROUND_TYPE`: per item, per line, or on the total; `PS_PRICE_ROUND_MODE`: up, down, half): it's the most common cause of totals that are off by a cent. Test with quantities that produce decimals.
- **Multi-currency**: switching currency converts with the rate; verify the rounding and that the charge is in the displayed currency.

## 11. Multistore (multishop)

- With multistore enabled (`PS_MULTISHOP_FEATURE_ACTIVE = 1`), each store (or group) can have its own **catalog, prices, carriers, modules and theme**. You have to test **each store** (switch store in the BO selector and go through its FO via its domain or subfolder).

## 12. Multi-language

- Each active language has its translations (BO → International → Translations) and its multilingual fields (name, description, meta). Review each page in each language with the **`translation-analyst`**: untranslated texts, visible keys, product pages, checkout and emails.

## 13. Transactional emails

- PrestaShop sends emails from **templates** (`mails/<language>/`) with `{variable}` variables. Test with the **`email-verifier`** (Mailpit): order confirmation, payment accepted, processing in progress, shipped, refund and password change.
- Unreplaced variables (`{firstname}` visible), broken links and the desktop and mobile views.
- Configure sending via **SMTP** pointing to Mailpit on staging so you don't email real customers.

## 14. Webservice API (read-only survey)

- The **Webservice** (BO → Advanced Parameters → Webservice) exposes REST resources (XML, or JSON with `?output_format=JSON`). Auth: **HTTP Basic with the key as the user and an empty password**.
- For QA, use a key with **read-only** permission on: `configurations`, `products`, `stock_availables`, `carriers`, `zones`, `currencies`, `languages`, `cart_rules` and `shops`.
- `?display=full` returns all fields; `?limit=N`; `filter[field]=value` (and `[a|b|c]` for OR). Write methods (POST/PUT/DELETE) are never used.
- The PrestaShop **version** isn't exposed through the Webservice (security): it comes from the local installation (`--local`: `app/AppKernel.php` in 1.7/8, `config/settings.inc.php` in 1.6).

## 15. Automating with Playwright (web-mapper)

- Locate by role and accessible name; the `classic` theme has stable classes (`.product-add-to-cart`, `#checkout`), but the IDs Smarty generates change.
- The **BO** lives at `/admin-XXXX` (renamed folder): store it in the `.env`, don't guess it.
- Wait for the cart's AJAX calls (`?controller=cart&action=...` / `/cart`) to respond before reading the total or the counter.
- Dismiss the **cookie banner** (GDPR) and newsletter popups at the start of the scenario.
- **Combinations**: choosing a variant reloads the price and stock via AJAX; wait for that fetch.
- **Captcha** (reCAPTCHA on contact or signup): don't bypass it; ask to disable it on staging or leave those steps as manual.
- **Data that changes on its own** (stock, date-based specific prices): verify relative to the value you read at the start.

## 16. Typical PrestaShop bugs

- PHP errors or a PrestaShop exception visible (developer mode on in production).
- Overridden, outdated `.tpl` files from a module or the theme: broken checkout or product page.
- Two modules overriding the same class and clashing.
- Friendly URLs enabled without a regenerated `.htaccess` → 404 on product and category pages.
- No active carrier, or no carrier for a zone → you can't buy.
- Smarty forcing compilation or CCC off in production → slow store.
- Enabling CCC breaks the theme (CSS/JS that depended on being separate).
- Totals that don't match because of rounding (`PS_ROUND_TYPE` / `PS_PRICE_ROUND_MODE`).
- An out-of-stock combination that can still be bought (or the other way around).
- An email with unreplaced `{...}` variables.
- Demo catalog or demo modules in a real store.
- A change made "for this shop" in multistore that doesn't show in the other one (or vice versa).

## 17. Typical questions for the PO (PrestaShop)

In addition to those in the `ecommerce-testing` skill, when it isn't written down they are `MI-XX`:

- Which PrestaShop version (1.6, 1.7, 8.x) and which theme (child of `classic` or custom)?
- Is guest checkout enabled, or is an account required?
- Which carriers and zones are in scope? Is there free shipping, and under what condition?
- How does an out-of-stock product behave (deny, allow, store default)?
- Which rounding does the store use, and at what level (line or total)?
- Is the store multistore? Which stores are part of the testing?
- Which modules are in scope, and which are third-party ones that aren't tested?
- Does the testing include performance (CCC, cache, Smarty) or only functional?

## 18. Smoke, regression, performance and security (PrestaShop)

The generic part (the five test types) is in `ecommerce-testing`; the **local smoke** is in §1 and **performance** (Smarty, CCC, cache, dev mode, profiling) in §5. Here's the rest specific to PrestaShop.

- **Regression**: PrestaShop breaks because of the **combination of modules, theme and overrides**. After **installing or updating a module or the theme**, or a version upgrade (on staging, with a database and file backup), run the full purchase flow —catalog → product page with combinations → cart → checkout (one page or 5 steps) → payment → order status → email— watching the console and `var/logs/`; delete `cache/class_index.php` and clear the cache; add `pixel-perfect` and `cross-browser` if the theme changed. In multistore, repeat for each store.
- **Security**: the **Webservice key** with least privilege and not exposed; the **back-office folder** (`/admin-XXXX`) renamed and not indexed; **IDOR** on the invoice PDF or the order detail (`?id_order=`, `controller=pdf-invoice`) must not let you see other people's orders; **developer mode off** in production (otherwise it leaks errors and stack traces — the survey detects it); `app/config`, `.env`, `var/logs/` and backups not accessible by URL; SQL in third-party modules; front-office tokens enabled (`PS_TOKEN_ENABLE`); HTTPS across the whole site. Active security testing, with `security-analyst` / `web-pentester`.
