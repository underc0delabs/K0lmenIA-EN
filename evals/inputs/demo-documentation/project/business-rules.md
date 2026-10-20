---
title: Business rules
type: project
sources: github demo/store@main (a1b2c3d), PROJ-40
updated: 2026-10-10
---

# Business rules

## Signup

- **Username**: between 4 and 20 characters; only letters, numbers and underscore. Source: `src/signup/validations.ts:12` (observed in the code).
- **Name**: between 2 and 50 characters; accepts accents, ñ and apostrophes. Source: `src/signup/validations.ts:8`.
- **Minimum age**: story US-901 says 18 years in the description and 16 in AC4. The code validates 18 (`src/signup/validations.ts:20`). Unresolved contradiction.

## Cart and coupons

- **Only one coupon per purchase**: `MAX_COUPONS_PER_PURCHASE = 1` (`src/payments/coupons.ts:3`). Decision confirmed by the PO in PROJ-40 (comment by Ana Pérez, 2026-08-10).
- **Free shipping** from $50 (`src/payments/shipping.ts:5`).

## Payments

- Accepted methods: credit card, debit card and bank transfer (`src/payments/methods.ts:2`).
