import texts from '../i18n/en.json';

export const MAX_COUPONS_PER_PURCHASE = 1;

export function applyCoupon(cart: { coupons: string[] }, code: string): string | null {
  if (cart.coupons.length >= MAX_COUPONS_PER_PURCHASE) return texts.couponAlreadyApplied;
  cart.coupons.push(code);
  return null;
}
