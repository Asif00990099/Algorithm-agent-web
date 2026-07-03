'use client';
/** Small shared UI primitives. */
import { pctClass, fmtPct } from '@/lib/format';

export function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  accent?: 'bull' | 'bear' | 'default';
}) {
  const ring =
    accent === 'bull' ? 'ring-bull/30' : accent === 'bear' ? 'ring-bear/30' : 'ring-accent/20';
  return (
    <div className={`glass animate-slide-up p-4 ring-1 ${ring}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{sub}</div>}
    </div>
  );
}

export function PctBadge({ value }: { value: number | null | undefined }) {
  return <span className={`font-semibold ${pctClass(value)}`}>{fmtPct(value)}</span>;
}

export function ActionBadge({ action }: { action: string }) {
  const styles: Record<string, string> = {
    buy: 'bg-bull/15 text-bull',
    sell: 'bg-bear/15 text-bear',
    hold: 'bg-slate-400/15 text-slate-500 dark:text-slate-300',
    long: 'bg-bull/15 text-bull',
    short: 'bg-bear/15 text-bear',
  };
  return (
    <span className={`badge uppercase ${styles[action] ?? styles.hold}`}>{action}</span>
  );
}

export function Spinner({ label = 'Loading live data…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-14 justify-center text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
      {label}
    </div>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="glass border-bear/40 p-4 text-sm text-bear" role="alert">
      {message}
    </div>
  );
}

export function SectionTitle({
  title,
  sub,
  right,
}: {
  title: string;
  sub?: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
      <div>
        <h2 className="text-xl font-bold tracking-tight">{title}</h2>
        {sub && <p className="text-sm text-slate-500 dark:text-slate-400">{sub}</p>}
      </div>
      {right}
    </div>
  );
}

export function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const color = pct > 66 ? 'bg-bull' : pct > 33 ? 'bg-amber-400' : 'bg-bear';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200 dark:bg-white/10">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-semibold">{pct.toFixed(0)}</span>
    </div>
  );
}
