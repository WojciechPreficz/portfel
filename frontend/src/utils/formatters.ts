const numberFormat = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 2 });
const priceFormat = new Intl.NumberFormat('pl-PL', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const currencyFormat = new Intl.NumberFormat('pl-PL', {
  style: 'currency',
  currency: 'PLN',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});
const percentFormat = new Intl.NumberFormat('pl-PL', {
  maximumFractionDigits: 2,
  signDisplay: 'always',
});

export const formatCurrency = (value: number | null | undefined) =>
  value == null ? '--' : currencyFormat.format(value);
export const formatNumber = (value: number | null | undefined) =>
  value == null ? '--' : numberFormat.format(value);
export const formatPrice = (value: number | null | undefined) =>
  value == null ? '--' : priceFormat.format(value);
export const formatPercent = (value: number | null | undefined) =>
  value == null ? '--' : `${percentFormat.format(value)}%`;
export const isPositive = (value: number | null | undefined) => (value ?? 0) >= 0;
