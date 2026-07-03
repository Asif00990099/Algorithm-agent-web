'use client';
import { useState } from 'react';
import { usePoll } from '@/lib/hooks';
import { fmtCompact, fmtPct, fmtTime, fmtUsd, pctClass } from '@/lib/format';
import { ActionBadge, ErrorBox, SectionTitle, Spinner } from '@/components/ui';

interface Row {
  symbol: string; price: number; change_pct: number; volume_usd: number;
  volatility_pct: number; trades: number; range_position: number;
}
interface Whale {
  symbol: string; price: number; quantity: number; notional_usd: number;
  side: string; time: number;
}
interface Scan {
  gainers: Row[]; losers: Row[]; most_active: Row[]; highest_volume: Row[];
  highest_volatility: Row[]; breakouts: Row[]; breakdowns: Row[];
  whale_trades: Whale[]; new_listings: { id: string; symbol: string; name: string }[];
  pairs_scanned: number;
}

const TABS = [
  ['gainers', 'Top gainers'], ['losers', 'Top losers'], ['most_active', 'Most active'],
  ['highest_volume', 'Highest volume'], ['highest_volatility', 'Most volatile'],
  ['breakouts', 'Breakouts'], ['breakdowns', 'Breakdowns'],
] as const;

export default function ScannerPage() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('gainers');
  const { data, error, loading } = usePoll<Scan>('/market/scanner', 60_000);
  const rows: Row[] = data ? (data[tab] as Row[]) : [];

  return (
    <div className="space-y-8">
      <SectionTitle
        title="Market scanner"
        sub={data ? `Scanning ${data.pairs_scanned} liquid USDT pairs every minute` : 'Full-market sweep every minute'}
      />
      {loading && <Spinner />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <div className="flex flex-wrap gap-1">
            {TABS.map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`rounded-xl px-3 py-1.5 text-sm font-semibold transition ${
                  tab === key ? 'bg-accent text-white shadow-md shadow-accent/25' : 'bg-slate-100 hover:bg-slate-200 dark:bg-white/10'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="glass overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr><th>Pair</th><th>Price</th><th>24h change</th><th>Volume</th><th>Volatility</th><th>Trades</th><th>Range pos.</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol} className="table-row-hover">
                    <td className="font-semibold">{r.symbol}</td>
                    <td className="font-mono">{fmtUsd(r.price)}</td>
                    <td className={pctClass(r.change_pct)}>{fmtPct(r.change_pct)}</td>
                    <td className="font-mono">{fmtCompact(r.volume_usd)}</td>
                    <td className="font-mono">{r.volatility_pct.toFixed(1)}%</td>
                    <td className="font-mono">{fmtCompact(r.trades)}</td>
                    <td>
                      <div className="h-1.5 w-16 rounded-full bg-slate-200 dark:bg-white/10">
                        <div className="h-full rounded-full bg-accent" style={{ width: `${r.range_position * 100}%` }} />
                      </div>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={7} className="py-8 text-center text-slate-400">No matches this cycle</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="glass p-4">
              <h3 className="mb-3 font-bold">🐋 Whale prints (≥ $250k)</h3>
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {data.whale_trades.map((w, i) => (
                  <div key={i} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm dark:bg-white/[0.04]">
                    <div className="flex items-center gap-2">
                      <ActionBadge action={w.side} />
                      <span className="font-semibold">{w.symbol}</span>
                    </div>
                    <div className="text-right">
                      <div className="font-mono font-bold">{fmtCompact(w.notional_usd)}</div>
                      <div className="text-xs text-slate-400">{fmtUsd(w.price)} · {fmtTime(w.time / 1000)}</div>
                    </div>
                  </div>
                ))}
                {data.whale_trades.length === 0 && <p className="text-sm text-slate-400">No whale-sized prints in the last cycle.</p>}
              </div>
            </section>

            <section className="glass p-4">
              <h3 className="mb-3 font-bold">🆕 New listings (CoinGecko)</h3>
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {data.new_listings.map((l) => (
                  <div key={l.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm dark:bg-white/[0.04]">
                    <span className="font-semibold">{l.name}</span>
                    <span className="badge bg-accent/10 uppercase text-accent">{l.symbol}</span>
                  </div>
                ))}
                {data.new_listings.length === 0 && <p className="text-sm text-slate-400">No new listings reported.</p>}
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
