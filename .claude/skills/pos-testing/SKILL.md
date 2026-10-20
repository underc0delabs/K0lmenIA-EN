---
name: pos-testing
description: How to test point-of-sale (POS) systems and peripheral hardware — the sales flow (opening/closing the register and cash count, product scanning, quantities and weights, discounts and promotions, taxes, returns and voids, multiple payment methods and split payment, change, suspend/resume a sale), payment methods and payment hardware (card reader/EMV chip and contactless, pinpad, QR/wallets, approved/declined/no signal, tips, installments, EMV fallback), peripherals (receipt printer and kitchen printer, cash drawer, 1D/2D barcode scanner, scale, customer display, fingerprint reader), fiscal integration (fiscal printer/controller, e-invoicing, rounding, fiscal voids depending on the country), offline mode and sync (selling without internet, transaction queue, reconciliation on reconnect, no duplicates), inventory (stock deduction, multi-branch), cashier/supervisor roles and authorizations (void, manual discount), cash reconciliation and closing reports (Z/X), resilience (power outage mid-sale, printer out of paper, disconnected peripheral), and how to test (on real hardware or the manufacturer's simulators/SDK); typical bugs and questions for the business. Used by the pos-tester.
---

# Point-of-sale (POS) and hardware testing

A POS mixes **software + hardware + money + fiscal**, often **offline**. What hurts the most: **the register not balancing**, **charging incorrectly**, or a sale being **lost or duplicated** because of an outage. You test the full flow, the peripherals and the failure modes. For money reconciliation and payment gateways, it relies on `wallet-tester`.

## 1. Sales flow

- **Opening/closing the register** with an opening float and a final **cash count** (counted = expected).
- Product **scanning** (barcode), **quantities**, **products sold by weight** (scale), items without a code (search/manual).
- **Discounts and promotions** (per item, on the total, buy one get one), **taxes**, **rounding**.
- **Returns and voids** (with authorization), **suspend/resume** a sale, cancel before charging.
- **The numbers have to add up**: subtotal − discounts + taxes = total, and total = amount charged; correct **change**.

## 2. Payment methods

- **Cash** (change, no change available), **card** (EMV chip, contactless, magstripe/fallback), **QR/wallets**, **split payment** (part cash, part card).
- Outcomes: **approved, declined, no signal, timeout, canceled** on the pinpad; **tip**, **installments**.
- The pinpad and the POS stay **consistent**: if the charge is approved but the POS doesn't record it (or vice versa), that's a serious bug. Idempotency on retries (see `wallet-tester`).

## 3. Peripherals / hardware

- **Receipt printer** and **kitchen printer**: prints the right thing, handles **out of paper**.
- **Cash drawer**: opens when it should (and only then).
- 1D/2D **barcode scanner**; **scale** (weight and tare); **customer display**; cashier fingerprint/ID reader.
- A peripheral **disconnected** mid-operation: clear message, no crash.

## 4. Fiscal

- **Fiscal printer/controller** or **e-invoicing**: the receipt is issued with the correct data (taxes, tax ID, receipt type), depending on the country.
- **Fiscal voids** and credit notes; fiscal **rounding**; fiscal closing (Z).

## 5. Offline and sync

- **Selling without internet**: the sale is recorded locally, the transaction is queued and **synced** on reconnect; **it isn't lost or duplicated**.
- **Reconciliation**: what was sold offline shows up exactly once in the backend; stock and register balance after syncing.

## 6. Inventory and multi-branch

- The sale **deducts stock**; returns restore it; stock per **branch**; transfers.

## 7. Roles and authorizations

- **Cashier vs. supervisor**: voids, manual discounts, opening the drawer and reprints require **authorization**; the cashier can't do what they shouldn't.

## 8. Reconciliation and reports

- **Register closing** (X/Z): counted cash vs. system, per payment method; differences flagged. Shift sales reports.

## 9. Resilience (failure modes)

- **Power outage / abrupt shutdown** in the middle of a sale: on restart, the sale is consistent (complete or canceled, never half-done with the charge made and the sale lost).
- Printer out of paper, network down, pinpad disconnected: clear messages and recovery.

## 10. How to test

- On **real hardware** (ideal for pinpad, printer, scale, drawer) or with the manufacturer's and acquirer's **simulators/SDK** (gateway test mode, test cards). Much of it is **assisted manual**; automate the software logic (prices, discounts, closing) and offline sync.

## 11. Typical POS bugs

- **The register doesn't balance** at closing (rounding, a payment method added up wrong).
- Charge approved on the pinpad but sale not recorded (or duplicated) → imbalance and complaint.
- An offline sale that gets lost or duplicated when syncing.
- Change or tax miscalculated; a promotion that doesn't apply or applies twice.
- A fiscal receipt with wrong data or that isn't issued.
- A disconnected peripheral that crashes the POS instead of warning.
- A void/discount without asking for supervisor authorization.
- Stock that isn't deducted, or is deducted from the wrong branch.

## 12. Typical questions for the business

When it isn't written down, they are `MI-XX`:

- Which hardware (pinpad/acquirer, printer, scale, drawer), and are there simulators/SDKs?
- Which payment methods and which gateway (test mode)?
- Does it work offline? How should it sync and reconcile?
- Which fiscal integration, and for which country (receipts, rounding, voids)?
- Which actions require supervisor authorization?
- What does the expected cash count and closing (X/Z) look like?
