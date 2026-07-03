'use client';
import Link from 'next/link';
import { useState } from 'react';
import { usePoll } from '@/lib/hooks';
import { fmtCompact, fmtPct, fmtUsd, pctClass } from '@/lib/format';
import { ErrorBox, SectionTitle, Spinner } from '@/components/ui';

interface Coin {
  id: string; symbol: string; name: string; image: string;
  current_price: number; market_cap: number; market_cap_rank: number;
  total_volume: number; price_change_percentage_24h: number;
  price_change_percentage_7d_in_currency?: number;
  price_change_percentage_30d_in_currency?: number;
  ath: number; atl: number;
  sparkline_in_7d?: { price: number[] };
}

function Sparkline({ points }: { points?: number[] }) {
  if (!points?.length) return null;
  const w = 110, h = 32;
  const min = Math.min(...points), max = Math.max(...points);
  const range = max - min || 1;
  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'}${((i / (points.length - 1)) * w).toFixed(1)},${(h - ((p - min) / range) * h).toFixed(1)}`)
    .join(' ');
  const up = points[points.length - 1] >= points[0];
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={path} fill="none" strokeWidth="1.5" stroke={up ? '#10b981' : '#ef4444'} />
    </svg>
  );
}

export default function MarketsPage() {
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const { data, error, loading } = usePoll<Coin[]>(`/market/coins?page=${page}&per_page=100`, 60_000);

  const filtered = (data ?? []).filter(
    (c) =>
      !query ||
      c.name.toLowerCase().includes(query.toLowerCase()) ||
      c.symbol.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div>
      <SectionTitle
        title="Crypto markets"
        sub="Rank, price, volume, market cap and multi-horizon performance — live"
        right={
          <input
            className="input max-w-56"
            placeholder="Filter assets…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        }
      />
      {loading && <Spinner />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <div className="glass overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th>#</th><th>Asset</th><th>Price</th><th>24h</th><th>7d</th><th>30d</th>
                  <th>Volume</th><th>Market cap</th><th>7d chart</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.id} className="table-row-hover">
                    <td className="text-slate-400">{c.market_cap_rank}</td>
                    <td>
                      <Link href={`/coin/${c.id}`} className="flex items-center gap-2 font-semibold">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={c.image} alt="" className="h-6 w-6 rounded-full" />
                        <span className="max-w-40 truncate">{c.name}</span>
                        <span className="text-xs uppercase text-slate-400">{c.symbol}</span>
                      </Link>
                    </td>
                    <td className="font-mono">{fmtUsd(c.current_price)}</td>
                    <td className={pctClass(c.price_change_percentage_24h)}>{fmtPct(c.price_change_percentage_24h)}</td>
                    <td className={pctClass(c.price_change_percentage_7d_in_currency)}>{fmtPct(c.price_change_percentage_7d_in_currency)}</td>
                    <td className={pctClass(c.price_change_percentage_30d_in_currency)}>{fmtPct(c.price_change_percentage_30d_in_currency)}</td>
                    <td className="font-mono">{fmtCompact(c.total_volume)}</td>
                    <td className="font-mono">{fmtCompact(c.market_cap)}</td>
                    <td><Sparkline points={c.sparkline_in_7d?.price?.filter((_, i) => i % 4 === 0)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-4 flex items-center justify-center gap-3">
            <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
            <span className="text-sm text-slate-500">Page {page}</span>
            <button className="btn-ghost" onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        </>
      )}
    </div>
  );
}
