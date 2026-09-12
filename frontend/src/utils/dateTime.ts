/** API timestamps without an offset are UTC, including reports imported before v3. */
export function localDateTime(value: string): string {
  const qualified = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  const date = new Date(qualified);
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : date.toLocaleString();
}
