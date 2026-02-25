import type { TimeRange } from './api';

export const TIME_RANGE_OPTIONS: TimeRange[] = ['24h', '7d', '30d'];

export function normalizeRange(value: string | null | undefined): TimeRange {
  if (value === '7d' || value === '30d') {
    return value;
  }
  return '24h';
}

export function rangeStartEpoch(range: TimeRange, nowMs: number = Date.now()): number {
  const nowSeconds = Math.floor(nowMs / 1000);
  switch (range) {
    case '7d':
      return nowSeconds - 7 * 24 * 3600;
    case '30d':
      return nowSeconds - 30 * 24 * 3600;
    case '24h':
    default:
      return nowSeconds - 24 * 3600;
  }
}

export function shortId(value: string, head = 8): string {
  if (!value) return '-';
  if (value.length <= head) return value;
  return `${value.slice(0, head)}…`;
}

export async function copyToClipboard(text?: string): Promise<boolean> {
  if (!text) return false;
  if (!navigator.clipboard) return false;
  await navigator.clipboard.writeText(text);
  return true;
}
