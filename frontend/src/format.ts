import Decimal from 'decimal.js-light';

Decimal.set({precision: 80});

export function money(value: string | number, currency = 'INR'): string {
  const amount = new Decimal(value);
  const [whole, fraction] = amount.abs().toFixed(2).split('.');
  const grouped = new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {maximumFractionDigits: 0}).format(BigInt(whole));
  const symbol = currency === 'INR' ? '₹' : currency === 'USD' ? '$' : `${currency} `;
  return `${amount.lt(0) ? '-' : ''}${symbol}${grouped}.${fraction}`;
}
export const number = (v: string | number, places = 2) => new Decimal(v).toDecimalPlaces(places).toString();
export const isPositive = (v: string) => new Decimal(v).gte(0);
export const errorText = (e: unknown) => e instanceof Error ? e.message : 'Something went wrong. Try again.';

