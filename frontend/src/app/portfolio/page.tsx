'use client';
import { useState } from 'react';
import { del, post } from '@/lib/api';
import { useAuthed, usePoll } from '@/lib/hooks';
import { fmtUsd, pctClass } from '@/lib/format';
import { ErrorBox, ActionBadge, SectionTitle, Spinner, StatCard } from '@/components/ui';

interface Portfolio {
  demo_balance: number; equity: number; unrealized_pnl: number; realized_pnl: number;
  exposure: number; closed_trades: number; win_rate: number;
  open_positions: {
    id: string; symbol: string; side: string; mode: string; quantity: number;
    entry_price: number; current_price: number | null; unrealized_pnl: number | null;
  }[];
}
interface WatchItem { id: string; symbol: string; asset_type: string; is_favorite: boolean }
interface Alert { id: string; symbol: string; condition: string; target_price: number; is_triggered: boolean }
interface Notif { id: string; title: string; body: string; kind: string; is_read: boolean; created_at: string }

export default function PortfolioPage() {
  const authed = useAuthed();
  const { data: pf, error, loading, reload } = usePoll<Portfolio>(authed ? '/users/me/portfolio' : null, 30_000, true);
  const { data: watchlist, reload: reloadWatch } = usePoll<WatchItem[]>(authed ? '/users/me/watchlist' : null, 0, true);
  const { data: alerts, reload: reloadAlerts } = usePoll<Alert[]>(authed ? '/users/me/alerts' : null, 60_000, true);
  const { data: notifs } = usePoll<Notif[]>(authed ? '/users/me/notifications' : null, 60_000, true);
  const [watchSymbol, setWatchSymbol] = useState('');
  const [alertForm, setAlertForm] = useState({ symbol: '', condition: 'above', target_price: '' });

  if (!authed) {
    return (
      <div className="glass mx-auto max-w-lg p-8 text-center">
        <h1 className="text-xl font-bold">Portfolio</h1>
        <p className="mt-2 text-sm text-slate-500">Sign in to view balances, positions, watchlist and alerts.</p>
        <a href="/login" className="btn-primary mt-4">Sign in</a>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <SectionTitle title="Portfolio" sub="Balances, open exposure and performance — marked to live prices" />
      {loading && <Spinner />}
      {error && <ErrorBox message={error} />}
      {pf && (
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Equity" value={fmtUsd(pf.equity)} sub={`cash ${fmtUsd(pf.demo_balance)}`} />
          <StatCard label="Unrealized PnL" accent={pf.unrealized_pnl >= 0 ? 'bull' : 'bear'}
            value={<span className={pctClass(pf.unrealized_pnl)}>{fmtUsd(pf.unrealized_pnl)}</span>}
            sub={`exposure ${fmtUsd(pf.exposure)}`} />
          <StatCard label="Realized PnL" accent={pf.realized_pnl >= 0 ? 'bull' : 'bear'}
            value={<span className={pctClass(pf.realized_pnl)}>{fmtUsd(pf.realized_pnl)}</span>}
            sub={`${pf.closed_trades} closed trades`} />
          <StatCard label="Win rate" value={`${pf.win_rate}%`} />
        </section>
      )}

      {pf && (
        <section className="glass overflow-x-auto">
          <table className="table-base">
            <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Now</th><th>Unrealized</th></tr></thead>
            <tbody>
              {pf.open_positions.map((p) => (
                <tr key={p.id} className="table-row-hover">
                  <td className="font-semibold">{p.symbol}</td>
                  <td><ActionBadge action={p.side} /></td>
                  <td className="font-mono">{p.quantity.toFixed(6)}</td>
                  <td className="font-mono">{fmtUsd(p.entry_price)}</td>
                  <td className="font-mono">{fmtUsd(p.current_price)}</td>
                  <td className={`font-mono font-bold ${pctClass(p.unrealized_pnl)}`}>
                    {p.unrealized_pnl != null ? fmtUsd(p.unrealized_pnl) : '—'}
                  </td>
                </tr>
              ))}
              {pf.open_positions.length === 0 && <tr><td colSpan={6} className="py-8 text-center text-slate-400">No open positions</td></tr>}
            </tbody>
          </table>
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="glass p-4">
          <h3 className="mb-3 font-bold">⭐ Watchlist</h3>
          <div className="flex gap-2">
            <input className="input font-mono uppercase" placeholder="BTCUSDT" value={watchSymbol}
              onChange={(e) => setWatchSymbol(e.target.value.toUpperCase())} />
            <button className="btn-primary" onClick={async () => {
              if (!watchSymbol) return;
              await post('/users/me/watchlist', { symbol: watchSymbol, asset_type: 'crypto' }, true);
              setWatchSymbol(''); reloadWatch();
            }}>Add</button>
          </div>
          <ul className="mt-3 space-y-2">
            {(watchlist ?? []).map((w) => (
              <li key={w.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm dark:bg-white/[0.04]">
                <span className="font-semibold">{w.symbol}</span>
                <button className="text-xs text-bear hover:underline" onClick={async () => { await del(`/users/me/watchlist/${w.id}`); reloadWatch(); }}>remove</button>
              </li>
            ))}
          </ul>
        </section>

        <section className="glass p-4">
          <h3 className="mb-3 font-bold">🔔 Price alerts</h3>
          <div className="grid grid-cols-3 gap-2">
            <input className="input font-mono uppercase" placeholder="Symbol" value={alertForm.symbol}
              onChange={(e) => setAlertForm({ ...alertForm, symbol: e.target.value.toUpperCase() })} />
            <select className="input" value={alertForm.condition}
              onChange={(e) => setAlertForm({ ...alertForm, condition: e.target.value })}>
              <option value="above">above</option><option value="below">below</option>
            </select>
            <input className="input font-mono" placeholder="Price" value={alertForm.target_price}
              onChange={(e) => setAlertForm({ ...alertForm, target_price: e.target.value })} />
          </div>
          <button className="btn-primary mt-2 w-full" onClick={async () => {
            if (!alertForm.symbol || !alertForm.target_price) return;
            await post('/users/me/alerts', { ...alertForm, target_price: Number(alertForm.target_price) }, true);
            setAlertForm({ symbol: '', condition: 'above', target_price: '' });
            reloadAlerts();
          }}>Create alert</button>
          <ul className="mt-3 space-y-2">
            {(alerts ?? []).map((a) => (
              <li key={a.id} className="flex items-center justify-between rounded-xl bg-slate-50 px-3 py-2 text-sm dark:bg-white/[0.04]">
                <span>{a.symbol} {a.condition} <b className="font-mono">{fmtUsd(a.target_price)}</b></span>
                <span className={`badge ${a.is_triggered ? 'bg-bull/15 text-bull' : 'bg-slate-200 text-slate-500 dark:bg-white/10'}`}>
                  {a.is_triggered ? 'triggered' : 'armed'}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="glass p-4">
          <h3 className="mb-3 font-bold">📬 Notifications</h3>
          <ul className="max-h-80 space-y-2 overflow-y-auto pr-1">
            {(notifs ?? []).map((n) => (
              <li key={n.id} className={`rounded-xl px-3 py-2 text-sm ${n.is_read ? 'bg-slate-50 dark:bg-white/[0.03]' : 'bg-accent/10'}`}>
                <div className="font-semibold">{n.title}</div>
                <div className="text-xs text-slate-500">{n.body}</div>
              </li>
            ))}
            {notifs?.length === 0 && <p className="text-sm text-slate-400">Nothing yet.</p>}
          </ul>
        </section>
      </div>
    </div>
  );
}
