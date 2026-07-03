'use client';
import { useState } from 'react';
import { post } from '@/lib/api';
import { useAuthed, usePoll } from '@/lib/hooks';
import { fmtUsd, pctClass } from '@/lib/format';
import { ErrorBox, SectionTitle, Spinner, StatCard } from '@/components/ui';

interface Strategy { id: string; name: string; timeframe: string }
interface BtResult {
  metrics: Record<string, number>;
  monthly_returns: Record<string, number>;
  equity_curve: { time: number; equity: number }[];
  trades: { side: string; entry_price: number; exit_price: number; pnl: number; pnl_pct: number; reason: string }[];
}

function EquityCurve({ points }: { points: { time: number; equity: number }[] }) {
  if (!points.length) return null;
  const w = 800, h = 220;
  const values = points.map((p) => p.equity);
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const path = values
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${((i / (values.length - 1)) * w).toFixed(1)},${(h - ((v - min) / range) * (h - 10) - 5).toFixed(1)}`)
    .join(' ');
  const up = values[values.length - 1] >= values[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      <path d={`${path} L${w},${h} L0,${h} Z`} fill={up ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)'} stroke="none" />
      <path d={path} fill="none" strokeWidth="2" stroke={up ? '#10b981' : '#ef4444'} />
    </svg>
  );
}

export default function BacktestPage() {
  const authed = useAuthed();
  const { data: strategies } = usePoll<Strategy[]>('/strategies', 0);
  const [form, setForm] = useState({ symbol: 'BTCUSDT', timeframe: '1h', initial_balance: 10000, strategy_id: '' });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [result, setResult] = useState<BtResult | null>(null);

  const run = async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      setResult(await post<BtResult>('/backtest/run', {
        symbol: form.symbol, timeframe: form.timeframe, limit: 1000,
        initial_balance: Number(form.initial_balance),
        strategy_id: form.strategy_id || null, params: {},
      }, true));
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Backtest failed');
    } finally {
      setBusy(false);
    }
  };

  const m = result?.metrics;

  return (
    <div className="space-y-8">
      <SectionTitle
        title="Strategy backtesting"
        sub="Replays up to 1000 live-history candles through the signal engine — fills at next-bar open, fees included, no lookahead"
      />

      <section className="glass grid gap-3 p-5 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Symbol</label>
          <input className="input mt-1 font-mono uppercase" value={form.symbol}
            onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Timeframe</label>
          <select className="input mt-1" value={form.timeframe} onChange={(e) => setForm({ ...form, timeframe: e.target.value })}>
            {['15m', '30m', '1h', '4h', '1d'].map((tf) => <option key={tf}>{tf}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Initial balance</label>
          <input type="number" className="input mt-1" value={form.initial_balance}
            onChange={(e) => setForm({ ...form, initial_balance: Number(e.target.value) })} />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Strategy</label>
          <select className="input mt-1" value={form.strategy_id} onChange={(e) => setForm({ ...form, strategy_id: e.target.value })}>
            <option value="">Default ensemble</option>
            {(strategies ?? []).map((s) => <option key={s.id} value={s.id}>{s.name} ({s.timeframe})</option>)}
          </select>
        </div>
        <div className="flex items-end">
          <button className="btn-primary w-full" onClick={run} disabled={busy || !authed}>
            {busy ? 'Backtesting…' : '▶ Run backtest'}
          </button>
        </div>
        {!authed && <p className="text-xs text-slate-400 sm:col-span-2 lg:col-span-5">Sign in to run backtests.</p>}
      </section>

      {busy && <Spinner label="Crunching historical candles…" />}
      {err && <ErrorBox message={err} />}

      {m && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total return" accent={m.total_return_pct >= 0 ? 'bull' : 'bear'}
              value={<span className={pctClass(m.total_return_pct)}>{m.total_return_pct}%</span>}
              sub={`${fmtUsd(m.initial_balance)} → ${fmtUsd(m.final_balance)}`} />
            <StatCard label="Win rate" value={`${m.win_rate}%`} sub={`${m.wins}W / ${m.losses}L of ${m.total_trades}`} />
            <StatCard label="Profit factor" value={m.profit_factor} sub={`Sharpe ${m.sharpe_ratio}`} />
            <StatCard label="Max drawdown" accent="bear" value={`${m.max_drawdown_pct}%`}
              sub={`avg trade ${m.avg_trade_pnl}`} />
          </section>

          <section className="glass p-4">
            <h3 className="mb-2 font-bold">Equity curve</h3>
            <EquityCurve points={result!.equity_curve} />
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            <section className="glass p-4">
              <h3 className="mb-3 font-bold">Monthly returns</h3>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {Object.entries(result!.monthly_returns).map(([month, ret]) => (
                  <div key={month} className={`rounded-xl p-2 text-center text-sm font-semibold ${ret >= 0 ? 'bg-bull/10 text-bull' : 'bg-bear/10 text-bear'}`}>
                    <div className="text-xs font-normal opacity-70">{month}</div>
                    {ret >= 0 ? '+' : ''}{ret}%
                  </div>
                ))}
              </div>
            </section>
            <section className="glass p-4">
              <h3 className="mb-3 font-bold">Trades ({result!.trades.length})</h3>
              <div className="max-h-72 overflow-y-auto">
                <table className="table-base">
                  <thead><tr><th>Side</th><th>Entry</th><th>Exit</th><th>PnL %</th><th>Exit reason</th></tr></thead>
                  <tbody>
                    {result!.trades.slice().reverse().map((t, i) => (
                      <tr key={i}>
                        <td className="uppercase">{t.side}</td>
                        <td className="font-mono">{fmtUsd(t.entry_price)}</td>
                        <td className="font-mono">{fmtUsd(t.exit_price)}</td>
                        <td className={pctClass(t.pnl_pct)}>{t.pnl_pct.toFixed(2)}%</td>
                        <td><span className="badge bg-slate-100 dark:bg-white/10">{t.reason}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
