'use client';
import { useState } from 'react';
import { post } from '@/lib/api';
import { useAuthed, usePoll } from '@/lib/hooks';
import { fmtTime, fmtUsd, pctClass } from '@/lib/format';
import { ActionBadge, ErrorBox, SectionTitle, Spinner } from '@/components/ui';

interface Trade {
  id: string; mode: string; status: string; symbol: string; side: string;
  quantity: number; entry_price: number; exit_price: number | null;
  stop_loss: number | null; take_profit: number | null;
  realized_pnl: number | null; realized_pnl_pct: number | null;
  close_reason: string | null; opened_at: string; closed_at: string | null;
}

export default function TradingPage() {
  const authed = useAuthed();
  const [form, setForm] = useState({
    symbol: 'BTCUSDT', side: 'long', mode: 'demo', risk_pct: 1,
    stop_loss: '', take_profit: '', trailing_stop_pct: '',
  });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const { data: trades, error, loading, reload } = usePoll<Trade[]>(authed ? '/trading/trades?limit=100' : null, 30_000, true);

  const submit = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const body: Record<string, unknown> = {
        symbol: form.symbol, side: form.side, mode: form.mode, risk_pct: Number(form.risk_pct),
      };
      if (form.stop_loss) body.stop_loss = Number(form.stop_loss);
      if (form.take_profit) body.take_profit = Number(form.take_profit);
      if (form.trailing_stop_pct) body.trailing_stop_pct = Number(form.trailing_stop_pct);
      await post('/trading/trades', body, true);
      setMsg({ kind: 'ok', text: `${form.side.toUpperCase()} ${form.symbol} opened at live market price` });
      reload();
    } catch (e) {
      setMsg({ kind: 'err', text: e instanceof Error ? e.message : 'Order failed' });
    } finally {
      setBusy(false);
    }
  };

  const close = async (id: string) => {
    try {
      await post(`/trading/trades/${id}/close`, undefined, true);
      reload();
    } catch (e) {
      setMsg({ kind: 'err', text: e instanceof Error ? e.message : 'Close failed' });
    }
  };

  if (!authed) {
    return (
      <div className="glass mx-auto max-w-lg p-8 text-center">
        <h1 className="text-xl font-bold">Trading terminal</h1>
        <p className="mt-2 text-sm text-slate-500">
          Sign in to trade. New accounts start with a $100,000 demo balance filled at live
          market prices; live trading connects to your own Binance API keys.
        </p>
        <a href="/login" className="btn-primary mt-4">Sign in</a>
      </div>
    );
  }

  const open = (trades ?? []).filter((t) => t.status === 'open');
  const closed = (trades ?? []).filter((t) => t.status !== 'open');

  return (
    <div className="space-y-8">
      <SectionTitle title="Trading terminal" sub="Demo fills at live prices · risk-based position sizing · automated SL/TP/trailing" />

      <section className="glass grid gap-3 p-5 md:grid-cols-4 lg:grid-cols-8">
        <div className="md:col-span-2">
          <label className="text-xs font-semibold uppercase text-slate-500">Symbol</label>
          <input className="input mt-1 font-mono uppercase" value={form.symbol}
            onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Side</label>
          <select className="input mt-1" value={form.side} onChange={(e) => setForm({ ...form, side: e.target.value })}>
            <option value="long">Long</option><option value="short">Short</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Mode</label>
          <select className="input mt-1" value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
            <option value="demo">Demo</option><option value="live">Live</option>
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Risk %</label>
          <input type="number" min={0.1} max={10} step={0.1} className="input mt-1" value={form.risk_pct}
            onChange={(e) => setForm({ ...form, risk_pct: Number(e.target.value) })} />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Stop loss</label>
          <input className="input mt-1 font-mono" placeholder="optional" value={form.stop_loss}
            onChange={(e) => setForm({ ...form, stop_loss: e.target.value })} />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Take profit</label>
          <input className="input mt-1 font-mono" placeholder="optional" value={form.take_profit}
            onChange={(e) => setForm({ ...form, take_profit: e.target.value })} />
        </div>
        <div>
          <label className="text-xs font-semibold uppercase text-slate-500">Trail %</label>
          <input className="input mt-1 font-mono" placeholder="optional" value={form.trailing_stop_pct}
            onChange={(e) => setForm({ ...form, trailing_stop_pct: e.target.value })} />
        </div>
        <div className="flex items-end md:col-span-4 lg:col-span-8">
          <button className={`btn-primary w-full ${form.side === 'short' ? '!bg-bear' : '!bg-bull'}`} disabled={busy} onClick={submit}>
            {busy ? 'Placing order…' : `${form.side === 'long' ? '▲ Buy / Long' : '▼ Sell / Short'} ${form.symbol} (${form.mode})`}
          </button>
        </div>
      </section>
      {msg && (
        msg.kind === 'err'
          ? <ErrorBox message={msg.text} />
          : <div className="glass border-bull/40 p-3 text-sm text-bull">{msg.text}</div>
      )}

      <section>
        <SectionTitle title={`Open positions (${open.length})`} sub="Monitored every 30s by the trade engine" />
        {loading && <Spinner />}
        {error && <ErrorBox message={error} />}
        <div className="glass overflow-x-auto">
          <table className="table-base">
            <thead><tr><th>Symbol</th><th>Side</th><th>Mode</th><th>Qty</th><th>Entry</th><th>SL</th><th>TP</th><th>Opened</th><th /></tr></thead>
            <tbody>
              {open.map((t) => (
                <tr key={t.id} className="table-row-hover">
                  <td className="font-semibold">{t.symbol}</td>
                  <td><ActionBadge action={t.side} /></td>
                  <td><span className="badge bg-slate-100 uppercase dark:bg-white/10">{t.mode}</span></td>
                  <td className="font-mono">{t.quantity.toFixed(6)}</td>
                  <td className="font-mono">{fmtUsd(t.entry_price)}</td>
                  <td className="font-mono text-bear">{fmtUsd(t.stop_loss)}</td>
                  <td className="font-mono text-bull">{fmtUsd(t.take_profit)}</td>
                  <td className="text-xs text-slate-400">{fmtTime(t.opened_at)}</td>
                  <td><button className="btn-ghost !py-1 text-xs" onClick={() => close(t.id)}>Close</button></td>
                </tr>
              ))}
              {open.length === 0 && <tr><td colSpan={9} className="py-8 text-center text-slate-400">No open positions</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <SectionTitle title="Trade history" />
        <div className="glass overflow-x-auto">
          <table className="table-base">
            <thead><tr><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th><th>PnL</th><th>PnL %</th><th>Reason</th><th>Closed</th></tr></thead>
            <tbody>
              {closed.map((t) => (
                <tr key={t.id} className="table-row-hover">
                  <td className="font-semibold">{t.symbol}</td>
                  <td><ActionBadge action={t.side} /></td>
                  <td className="font-mono">{fmtUsd(t.entry_price)}</td>
                  <td className="font-mono">{fmtUsd(t.exit_price)}</td>
                  <td className={`font-mono font-bold ${pctClass(t.realized_pnl)}`}>
                    {t.realized_pnl != null ? `${t.realized_pnl >= 0 ? '+' : ''}${t.realized_pnl.toFixed(2)}` : '—'}
                  </td>
                  <td className={pctClass(t.realized_pnl_pct)}>{t.realized_pnl_pct?.toFixed(2)}%</td>
                  <td><span className="badge bg-slate-100 dark:bg-white/10">{t.close_reason}</span></td>
                  <td className="text-xs text-slate-400">{fmtTime(t.closed_at)}</td>
                </tr>
              ))}
              {closed.length === 0 && <tr><td colSpan={8} className="py-8 text-center text-slate-400">No closed trades yet</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
