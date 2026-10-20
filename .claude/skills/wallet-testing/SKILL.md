---
name: wallet-testing
description: How to test digital wallets and payment methods (wallets, fintech, e-money) — balance and ledger (double-entry ledger), transactions (top-up, cash-out, P2P, payment, reversal, chargeback), idempotency and retries, double spending and concurrency, amount consistency (rounding, currency, decimals), limits and caps, a transaction's statuses, reconciliation against the payment provider, KYC/AML and antifraud, signed webhooks, 3-D Secure/SCA and the typical money bugs. Uses the token-testing skill for token and payment security. Used by the wallet-tester and the case generators when the app handles money.
---

# Digital wallet and payment testing

When an app handles **money**, a bug is not an annoyance: it is money that appears or disappears. The mother rule is **money is neither created nor destroyed**: every operation preserves the system's total. Everything about tokens and card tokenization is in the `token-testing` skill.

**Always in a test / sandbox environment, with test money and test cards. Never real movements or real personal data.**

## 1. Balance and ledger

A serious wallet doesn't store "a balance number" that is added and subtracted: it keeps a **double-entry ledger** (each movement is an entry with a debit and a credit that sum to zero) and the balance is the **sum of the entries**. What to verify:

- **Conservation invariant**: before and after any operation between accounts, the sum of all the system's balances (including the internal accounts: gateway, fees, suspense) is the same. A P2P from A to B: A goes down by X, B goes up by X, total unchanged.
- **Balance = sum of the ledger**: the balance the app shows matches the sum of the movements. If there is a "cached" balance field, that it doesn't get out of sync (verify it with the `data-verifier` by read-only SQL).
- **No negative balances** unless the product allows it (credit line): trying to spend more than available is rejected.
- **Funds in transit / holds**: an authorized but not captured payment holds balance; the available goes down even if the ledger balance doesn't. Test available vs. ledger.
- **Precision**: money is stored in **integers of the minimum unit** (cents) or exact decimal, **never in float** (0.1 + 0.2 ≠ 0.3). Test amounts that expose rounding: dividing, fee percentages, currency conversion. Rounding has a defined rule (in whose favor) and is always applied the same way.

## 2. Transactions and their statuses

Typical operations: **top-up** (money comes in), **cash-out/withdrawal**, **P2P** (between users), **payment** to a merchant, **reversal/refund**, **chargeback**.

- **State machine**: `pending → authorized → captured/completed`, with branches `declined`, `expired`, `reversed`, `in dispute`. Test each valid transition and, above all, the **invalid** ones: capturing something already reversed, reversing something pending, paying for the same order twice. A final state doesn't change.
- **Authorization vs. capture**: an authorization can be captured partially or expire without capture (releasing the hold). Test partial capture, double capture and capture after expiring.
- **Reversal/refund**: full and partial; you don't refund more than what was charged; the refund goes back to the same method; a refund of an already-refunded payment fails.
- **Fees and taxes**: they are calculated on the correct amount, posted to the correct account and reflected in what each party receives.

## 3. Idempotency and retries

In payments, the network fails: the client retries and must not charge twice.

- **Idempotency key**: the charge/transfer operation accepts an `Idempotency-Key`; repeating the **same** request with the same key returns the **same** result without executing again (a single entry). Test: send the same request 2-3 times with the same key → a single movement; with different keys → each one is processed.
- **Timeout and lost response**: simulate the response getting lost after executing (the `resilience-tester` helps); the retry must not duplicate.
- **Webhooks**: the provider retries the webhook; processing it twice must not credit twice (idempotency by event ID). Verify the webhook signature (see `token-testing`).

## 4. Concurrency and double spending

- **Double spending**: with balance for **one** operation, fire **two in parallel** (two withdrawals, a withdrawal and a payment) → only one succeeds, the other is rejected for funds; never both. It is the star test: it is done with concurrent requests (not sequential).
- **Race conditions**: applying the same coupon twice, redeeming a voucher twice, using the same single-use code; recording two operations against the same hold.
- **Locks**: the system serializes per account (optimistic/pessimistic lock); a deadlock or a `lock timeout` under load is a finding. The real load is built by the `performance-mapper`; here, bounded concurrency to detect double spending.
- **Eventual consistency**: if the crediting is asynchronous (queue), define the expected window and verify it balances in the end; that a failure midway doesn't leave money in limbo (saga/compensation).

## 5. Limits, caps and business rules

- **Limits**: per operation, daily, monthly, by the wallet's maximum balance (many e-money products have a regulatory cap), by number of operations. Test right at the limit, one above and accumulating over the period.
- **Minimums**: minimum top-up/withdrawal amount; zero and negatives rejected.
- **Unverified accounts**: a wallet without complete KYC usually has lower limits or can't withdraw. Test what each verification level can do.
- **Fund / promotion expiration**: promotional balance that expires or can't be withdrawn, separate from the real balance.

## 6. KYC / AML and antifraud

- **KYC (onboarding)**: signup with a document, identity validation, statuses (pending, approved, rejected, requires review); what each status enables. Test data, never real documents.
- **AML**: operations that should be **flagged** (high amounts, structuring, risky destinations, unusual velocity) generate an alert or a hold; verify that the rule fires and that the operation stays held, not completed.
- **Antifraud**: a new device, an IP from another country, many attempts, a card tried on several accounts (card testing) → friction (OTP, block). Don't generate real fraud patterns against third parties; test against the sandbox.
- **Lists and sanctions**: a beneficiary on a list must be blocked (if the product handles it).

## 7. Reconciliation

- **Against the payment provider**: what the wallet records has to match what the gateway reports (Stripe, Mercado Pago, Adyen…). Take the sandbox report/settlement and compare it with the wallet's movements: amounts, fees, dates, statuses; look for differences, duplicates and missing items.
- **Suspense accounts**: money in intermediate states (authorized, in dispute, pending settlement) must be in a suspense account and get resolved; nothing is left orphaned.
- **Chargebacks**: a sandbox chargeback debits the merchant, changes the status and reconciles.

## 8. Money in the interface

- **Format**: thousands and decimal separators according to the locale; correct currency symbol; clear debit/credit sign; the `translation-analyst` helps with formats per language.
- **Consistency**: the same amount looks the same in the list, the detail, the receipt, the email (`email-verifier`) and the PDF. The receipt can't be altered.
- **Statuses in sight**: the person understands whether a payment is pending, completed or rejected; a pending payment isn't shown as completed.
- **Resilience**: if the gateway goes down or lags, the interface doesn't leave the person not knowing whether they paid (double-clicking "Pay" doesn't charge twice → front-side idempotency too). The `resilience-tester` covers it.

## 9. Typical money bugs (to look for on purpose)

- Rounding that "wins" cents on each operation (salami).
- Double crediting from a retry or a repeated webhook (missing idempotency).
- Negative balance or spending above the available due to a race condition.
- An amount or currency that changes between screens or between front and back.
- A refund larger than the charge, or a double refund.
- A fee calculated on the wrong amount or posted to the wrong account.
- A transaction that stays "pending" forever (no timeout or compensation).
- A limit that can be exceeded with parallel operations.
- CVV or PAN stored/logged (see `token-testing`).

## 10. Tools in k0lmenIA

- Cases for the payments/wallet API: `api-case-generator` (positive, negative, authorization, idempotency). Run them: `api-runner` (Newman); automate them and run the concurrent part: `api-mapper` / k0lmena. Load and stress: `performance-mapper`.
- Verify balances and entries in the database: `data-verifier` (**read-only** SQL; never adjust balances by hand to "fix" a test).
- Resilience (gateway down, lost response, double click): `resilience-tester`. Emails and receipts: `email-verifier`. Token and webhook security: the `token-testing` skill and, for the authorized active part, `web-pentester`.

## 11. Rules

- **Sandbox only**, with **test money and test cards** from the provider; never real movements or data.
- **Don't "fix" data**: don't edit balances or statuses in the database to make a test pass; that hides the bug.
- What is expected (limits, fees, rounding, what each KYC level enables) comes from the story, the business rules or the applicable regulation: if it isn't defined, it is `Missing information`, not an assumption.
- **No personal data or secrets** in reports and screenshots; amounts and cards, always test ones.
