# E-commerce (Shopify, WordPress / WooCommerce, PrestaShop and VTEX)

**Read-only** functional surveys of online stores. They are used by the `shopify-tester`, `wordpress-tester`, `prestashop-tester` and `vtex-tester` agents.

- **`shopify.py`** (`npm run shopify`) — public storefront (key pages, published theme, Liquid errors and missing translations, legal policies, `/products.json`, `/cart.js`, structured data of a product page) and, with a read token for the **Admin API GraphQL**, the store (plan, whether it is a development store, currencies, taxes), themes, products with variants and stock, locations, markets, shipping profiles, discount codes, webhooks and the token's scopes. With `--theme-check` it runs `shopify theme check` on the theme code.
- **`wordpress.py`** (`npm run wordpress`) — public storefront (key pages, PHP errors or the WordPress critical error, `/wp-json` modules, Store API catalog) and, with a read key for the **WooCommerce REST API**, the system status (database pending update, cron, outgoing calls, outdated plugins, old theme templates, WooCommerce pages), gateways and their mode, shipping zones and methods, coupons, webhooks and products. With `--wp-cli`, through WP-CLI: available and automatic updates, overdue cron and failed Action Scheduler actions.
- **`prestashop.py`** (`npm run prestashop`) — public storefront (key pages, visible PHP errors or PrestaShop exceptions, structured data of a product page) and, with a read-only **Webservice API** key, products with stock and combinations, carriers (and whether any is active), zones, currencies, languages, cart rules (vouchers), shops (multistore) and the key QA and web performance settings (maintenance mode, catalog mode, HTTPS, Smarty and compilation, combine-compress-cache CSS/JS, guest checkout, rounding, taxes, terms). With `--local` it reads the version and whether `_PS_MODE_DEV_` was left on.
- **`vtex.py`** (`npm run vtex`) — public storefront (key pages, visible store or VTEX IO errors, structured data of a product page) and the **public Catalog System** (channel catalog with SKUs, price and availability); with a read-only app (`X-VTEX-API-AppKey`/`AppToken`), sales channels (trade policies), shipping policies (SLAs) and promotions. It detects the storefront (Store Framework, FastStore or legacy) and warns if the `master` workspace is being surveyed.
- **`_common.py`** — authorization, read-only HTTP, common storefront checks (key pages, robots, sitemap, 404, visible errors, product JSON-LD), catalog analysis (price 0, no image, overselling, compare-at price, no SKU, no tax) and saving with history.

Each run leaves in `output/<shopify|wordpress|prestashop|vtex>/<story or host>/` the `<platform>.json` and the `<platform>-report.html` (`scripts/generate_ecommerce_report.py`); the previous one moves to `history/` (last 5).

## Usage

```bash
# Shopify: storefront only, or with the Admin API if SHOPIFY_STORE and SHOPIFY_ADMIN_TOKEN are in the .env
npm run shopify -- --store https://my-store.myshopify.com --story US-010 --confirm
npm run shopify -- --store https://my-store.myshopify.com --theme-check --confirm

# WordPress / WooCommerce: with the REST API if WOOCOMMERCE_CONSUMER_KEY/SECRET are in the .env
npm run wordpress -- --site https://staging.mystore.com --confirm
npm run wordpress -- --site https://staging.mystore.com --wp-cli --confirm

# PrestaShop: with the Webservice API if PRESTASHOP_WEBSERVICE_KEY is in the .env
npm run prestashop -- --store https://staging.mystore.com --confirm
npm run prestashop -- --store https://staging.mystore.com --local C:/www/mystore --confirm

# VTEX: public catalog always; with the admin APIs if VTEX_APP_KEY/VTEX_APP_TOKEN are set
npm run vtex -- --store https://www.my-store.com --account myaccount --confirm
npm run vtex -- --store https://www.my-store.com --account myaccount --sc 1 --confirm
```

## Authorization and scope

- **Only URLs in `ECOMMERCE_AUTHORIZED_URLS`** in the `.env` (the host has to match; if the entry has a path, the URL has to start with it).
- **Read-only**: GET to the storefront and the APIs, GraphQL queries without mutations (they are rejected before being sent) and read-only WP-CLI commands. It does not create orders, customers or products and does not change settings.
- Credentials are **read** credentials (`read_*` scopes in Shopify, *Read* permission in WooCommerce) and live in the `.env`.
- **It is not a security tool**: the store's security is reviewed by the `security-analyst` and the `web-pentester`.
- Optional: the Shopify CLI (`npm install --global @shopify/cli`) for Theme Check and [WP-CLI](https://wp-cli.org) for `--wp-cli` (`npm run doctor` warns if they are missing).
