---
name: token-testing
description: How to test authentication and authorization tokens (JWT, OAuth 2.0 / OIDC, session and API tokens, API keys) and the tokenization of payment methods (card tokens, PCI-DSS) — lifecycle (issuance, expiration, refresh, revocation, rotation), signature and claim validation, the typical attacks (alg none, weak signature, tampered claims, replay, fixed token, scope escalation), secure handling (where they are stored, how they travel, what gets logged) and what NOT to do with real data. Used by the wallet-tester, the web-pentester and the salesforce-tester, and anyone who tests login, sessions, authenticated APIs or payments.
---

# Token testing

"Token" covers different things that are tested differently: **authentication/authorization tokens** (JWT, OAuth, session, API key) and **payment tokens** (the tokenization of a card). This skill covers both, always on **your own or authorized** environments and **without real data**.

Cross-cutting rule: **a token is a secret**. Don't paste it whole into reports, screenshots, logs or the chat; show at most the first characters (`eyJ…`) and recommend rotating any that appear exposed. Test tokens go in the `.env` (gitignored), never committed.

## 1. JWT (JSON Web Token)

A JWT has three parts `header.payload.signature` in base64url. The header and the payload **are readable without the key** (they are not encrypted, only signed): never put sensitive data in the payload.

What to verify:
- **Signature**: the server **rejects** a token with a changed or missing signature. Change a byte of the signature and expect 401.
- **`alg: none`**: take a valid token, set `"alg":"none"` in the header, delete the signature and test: if it accepts it, it is critical (full bypass).
- **Algorithm confusion** (RS256 → HS256): if the server uses RSA (known public key), try signing an HS256 token using the public key as the secret; if it validates, it is critical.
- **Weak signature (HS256)**: if the secret is short or common, it is offline brute force. Don't run it except in an authorized pentest; do flag the risk if the secret looks weak or is in the repo.
- **Claims**:
  - `exp` (expiration): an expired token is rejected; test just after `exp`. Is there an exaggerated clock skew tolerance?
  - `nbf` / `iat`: a token from the future, a token without `iat`.
  - `iss` / `aud`: does it validate issuer and audience? A token from another client/tenant shouldn't work.
  - `sub` / `roles` / `scope`: change the `sub` to another user or add a role/scope: if it doesn't re-validate against the signature, it is escalation (IDOR by claim).
- **`kid`**: injection through the `kid` (path traversal, SQL) so that it validates with a key you control; `jku`/`x5u` pointing to your own JWKS.
- **Expiration and refresh**: the access token is short-lived; the refresh token rotates on use (rotation) and the **previous one is invalidated**. Reusing an already-redeemed refresh must fail and, ideally, revoke the family (theft detection).
- **Logout and revocation**: after logging out, the old access token shouldn't work until its `exp` (if the server keeps a revocation list) — if it doesn't keep one, record the risk.

## 2. OAuth 2.0 / OIDC

- **Flow**: for apps and SPAs, **Authorization Code + PKCE**; *implicit* and *password grant* are discouraged. Flag it if they are used.
- **`state`**: present, random and verified on the way back (login anti-CSRF). Without `state`, it is vulnerable.
- **`redirect_uri`**: **exact** validation (not by prefix or wildcard). Test an unregistered `redirect_uri`, one with `@`, with `#`, with an extra subdomain or path: they must be rejected (open redirect / code theft).
- **PKCE**: `code_verifier` required; a code without a verifier or with the wrong verifier is rejected. The `code` is single-use and expires quickly; reusing it fails.
- **Scopes**: request an extra scope and verify the token doesn't receive it; try using a token for a resource outside its scope (it must give 403).
- **Tokens**: where they end up (see section 4), expiration, refresh with rotation (section 1). For server-to-server, **Client Credentials** or **JWT bearer**.

## 3. Session tokens and API keys

- **Session (cookie)**: the session cookie carries `HttpOnly`, `Secure` and an appropriate `SameSite`; the ID is long and random (not sequential or predictable). **It is renewed on login** (anti session-fixation: a previous ID shouldn't stay valid as authenticated). It expires by inactivity and by absolute time; logout invalidates it **on the server** (not just deleting the cookie). Two logins shouldn't share the same token.
- **API keys**: they travel in a header (`Authorization`), never in the URL (they end up in logs and history); they can be **rotated and revoked**; they have a narrow scope/permissions; there is a rate limit. A revoked key stops working instantly.
- **Fixation and replay**: a captured token shouldn't work from another IP/session if there is binding; test reusing it. For sensitive operations, additionally, idempotency (see the `wallet-testing` skill).

## 4. Secure handling (where it is stored and how it travels)

- **Transport**: always HTTPS; the token never in the **URL** or in query parameters; in the `Authorization: Bearer` header or in a secure cookie.
- **Client-side storage**: `localStorage` is accessible by JavaScript (exposed to XSS); for web, an `HttpOnly` cookie is safer for the session. Flag long tokens in `localStorage`.
- **Logs and errors**: the token must not appear in server logs, APM, error messages or analytics. Check error responses and `log-analyst`.
- **Cache**: responses with a token are non-cacheable (`Cache-Control: no-store`).
- **Exposure**: look for tokens or secrets in the repo, in the frontend bundle, in `.env.example` with real values, in committed Postman files.

## 5. Tokenization of payment methods (PCI-DSS)

Tokenizing = replacing the **PAN** (card number) with a **token** that is useless outside its context, so you don't store or transmit the real card.

- **Never use real cards.** Use the **provider's test cards** (Stripe, Mercado Pago, Adyen, PayPal, Braintree, etc.; each one publishes its test numbers and its sandbox environment). If a real PAN appears in data or logs, it is an incident: report it without copying it.
- **The PAN must not touch your backend**: with the provider's SDK/iframe (Stripe Elements, Checkout, hosted fields), the card goes from the browser to the provider and a token comes back. Verify that your server receives **the token, not the PAN/CVV**.
- **The token is not the card**: it can't be "de-tokenized" on the merchant side; it is tied to a single provider and, sometimes, to a single merchant or use.
- **What to test**: tokenize a test card and charge with the token; invalid/expired token; reuse of a single-use token; a token from another merchant (it must not work); limit amounts; currency; 3-D Secure (SCA) when applicable; the masked PAN is shown as `**** 4242` and never in full; the CVV **is not stored** (PCI forbids it).
- **Data that is never stored**: CVV/CVC, the full PAN except encrypted and within PCI scope, the magnetic stripe/chip. If the app stores or logs them, it is a critical finding.
- **Payment webhooks**: the real confirmation arrives through a **signed webhook** from the provider; verify the signature (don't trust the `return_url`), idempotency (the provider retries) and that a forged webhook is rejected.

## 6. Tools in k0lmenIA

- Design the cases: `api-case-generator` (includes authorization and token cases). Run against the API: `api-runner` (Newman) with the token and the URL from the `.env`. Automate: `api-mapper`.
- Decode a JWT to inspect its claims: do it **offline** (the header and the payload are base64url); don't send the token to an online decoder (it leaks).
- The active part (forging tokens, `alg:none`, brute force) belongs to an **authorized pentest**: it goes with the `web-pentester`, only with `PENTEST_AUTHORIZED=yes` and on your own site or one with written permission. Without that authorization, the analysis stays passive: reviewing the configuration, the claims, the transport and the storage.

## 7. Rules

- **Only your own or authorized environments.** Forging or attacking the tokens of a third-party system without permission is not done.
- **No real data**: provider test cards, test users, sandbox environment.
- **Tokens are secrets**: from the `.env`, never in the chat or the report; any that appear, recommend rotating them and show them truncated.
- What is expected comes from the story, the standard (RFC 7519 for JWT, OAuth 2.1, OWASP ASVS chapter 3 on sessions) or the provider's documentation: if it isn't defined, it is `Missing information`, not an assumption.
