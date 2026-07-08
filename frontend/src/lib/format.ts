/** Number & date formatting helpers. */

export function fmtPrice(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  if (n >= 1000) return n.toLocaleString('en-US', { maximumFractionDigits: 2 });
  if (n >= 1) return n.toFixed(2);
  if (n >= 0.01) return n.toFixed(4);
  return n.toPrecision(4);
}

export function fmtUsd(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `$${fmtPrice(n)}`;
}

export function fmtCompact(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(n);
}

export function fmtPct(n: number | null | undefined, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}%`;
}

export function pctClass(n: number | null | undefined): string {
  if (n === null || n === undefined) return 'text-gray-400';
  return n >= 0 ? 'text-bull' : 'text-bear';
}

/** Parse an API timestamp. Timezone-naive strings (no Z/offset) are treated as
 *  UTC — the backend stores UTC, so without this a viewer in UTC+5 sees fresh
 *  items as "5h ago". */
function parseApiDate(iso: string | number): Date {
  if (typeof iso === 'number') return new Date(iso * 1000);
  const hasTz = /([zZ]|[+-]\d{2}:?\d{2})$/.test(iso);
  return new Date(hasTz ? iso : `${iso}Z`);
}

export function fmtTime(iso: string | number | null | undefined): string {
  if (!iso) return '—';
  const d = parseApiDate(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = parseApiDate(iso).getTime();
  if (Number.isNaN(t)) return '';
  const secs = Math.max(0, (Date.now() - t) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}
