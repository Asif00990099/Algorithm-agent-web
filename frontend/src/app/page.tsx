'use client';
import Link from 'next/link';
import { usePoll } from '@/lib/hooks';
import { fmtCompact, fmtUsd, fmtPct, pctClass } from '@/lib/format';
import { ErrorBox, PctBadge, Spinner, SectionTitle, StatCard } from '@/components/ui';

interface Overview {
  global: {
    total_market_cap: Record<string, number>;
    total_volume: Record<string, number>;
    market_cap_percentage: Record<string, number>;
    market_cap_change_percentage_24h_usd: number;
    active_cryptocurrencies: number;
  } | null;
  top_coins: Array<{
    id: string; symbol: string; name: string; image: string;
    current_price: number; market_cap_rank: number;
    price_change_percentage_24h: number; total_volume: number; market_cap: number;
  }>;
  fear_greed: { value: string; value_classification: string } | null;
  trending: Array<{ item: { id: string; name: string; symbol: string; thumb: string; market_cap_rank: number } }>;
}

function FearGreedGauge({ value, label }: { value: number; label: string }) {
  const hue = (value / 100) * 120; // 0 red → 120 green
  return (
    <div className="flex items-center gap-4">
      <div
        className="grid h-20 w-20 place-items-center rounded-full text-2xl font-extrabold text-white shadow-lg"
        style={{ background: `conic-gradient(hsl(${hue} 70% 45%) ${value}%, rgba(120,120,140,.25) 0)` }}
      >
        <span className="grid h-14 w-14 place-items-center rounded-full bg-white text-slate-800 dark:bg-surface-dark dark:text-white">
          {value}
        </span>
      </div>
      <div>
        <div className="text-lg font-bold">{label}</div>
        <div className="text-xs text-slate-500">Crypto Fear &amp; Greed Index</div>
      </div>
    </div>
  );
}

export default function Home() {
  const { data, error, loading } = usePoll<Overview>('/market/overview', 60_000);

  return (
    <div className="space-y-10">
      <section className="glass relative overflow-hidden p-8 sm:p-12">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 -left-16 h-64 w-64 rounded-full bg-bull/10 blur-3xl" />
        <h1 className="max-w-2xl text-3xl font-extrabold tracking-tight sm:text-5xl">
          AI-powered trading intelligence,{' '}
          <span className="bg-gradient-to-r from-accent to-bull bg-clip-text text-transparent">
            live 24/7
          </span>
        </h1>
        <p className="mt-4 max-w-xl text-slate-600 dark:text-slate-300">
          QuantPulse monitors crypto, stocks, forex, news and social sentiment around the
          clock — generating explainable AI signals with risk plans, automated trading,
          backtesting and an always-on news desk.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/signals" className="btn-primary">Explore AI signals</Link>
          <Link href="/markets" className="btn-ghost">Live markets</Link>
        </div>
      </section>

      {loading && <Spinner />}
      {error && <ErrorBox message={`Market overview unavailable: ${error}`} />}

      {data && (
        <>
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total market cap"
              value={fmtCompact(data.global?.total_market_cap?.usd)}
              sub={<PctBadge value={data.global?.market_cap_change_percentage_24h_usd} />}
            />
            <StatCard label="24h volume" value={fmtCompact(data.global?.total_volume?.usd)} />
            <StatCard
              label="BTC dominance"
              value={`${data.global?.market_cap_percentage?.btc?.toFixed(1) ?? '—'}%`}
              sub={`${data.global?.active_cryptocurrencies?.toLocaleString() ?? '—'} active assets`}
            />
            <div className="glass p-4">
              {data.fear_greed ? (
                <FearGreedGauge
                  value={Number(data.fear_greed.value)}
                  label={data.fear_greed.value_classification}
                />
              ) : (
                <div className="text-sm text-slate-500">Fear &amp; Greed unavailable</div>
              )}
            </div>
          </section>

          <section>
            <SectionTitle
              title="Top assets"
              sub="Live prices from CoinGecko, refreshed every minute"
              right={<Link className="text-sm font-semibold text-accent" href="/markets">View all →</Link>}
            />
            <div className="glass overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr><th>#</th><th>Asset</th><th>Price</th><th>24h</th><th>Volume</th><th>Market cap</th></tr>
                </thead>
                <tbody>
                  {data.top_coins.slice(0, 10).map((c) => (
                    <tr key={c.id} className="table-row-hover">
                      <td className="text-slate-400">{c.market_cap_rank}</td>
                      <td>
                        <Link href={`/coin/${c.id}`} className="flex items-center gap-2 font-semibold">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={c.image} alt="" className="h-6 w-6 rounded-full" />
                          {c.name}
                          <span className="text-xs uppercase text-slate-400">{c.symbol}</span>
                        </Link>
                      </td>
                      <td className="font-mono">{fmtUsd(c.current_price)}</td>
                      <td className={pctClass(c.price_change_percentage_24h)}>
                        {fmtPct(c.price_change_percentage_24h)}
                      </td>
                      <td className="font-mono">{fmtCompact(c.total_volume)}</td>
                      <td className="font-mono">{fmtCompact(c.market_cap)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {data.trending?.length > 0 && (
            <section>
              <SectionTitle title="Trending searches" sub="What the market is looking at right now" />
              <div className="flex flex-wrap gap-2">
                {data.trending.map(({ item }) => (
                  <Link
                    key={item.id}
                    href={`/coin/${item.id}`}
                    className="glass glass-hover flex items-center gap-2 px-3 py-2 text-sm font-medium"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={item.thumb} alt="" className="h-5 w-5 rounded-full" />
                    {item.name}
                    <span className="text-xs text-slate-400">#{item.market_cap_rank ?? '—'}</span>
                  </Link>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        {[
          ['🤖', 'AI Signal Engine', 'Weighted ensemble of 20+ indicators, social sentiment, funding and fear/greed — with optional LLM review and full risk plans.'],
          ['📰', 'Automated News Desk', 'Aggregates dozens of sources, rewrites every story into original SEO content, and publishes automatically.'],
          ['⚡', 'Automated Trading', 'Demo and live modes with risk-based sizing, stop loss, take profit, trailing stops and 24/7 position monitoring.'],
        ].map(([icon, title, body]) => (
          <div key={title} className="glass glass-hover p-6">
            <div className="text-3xl">{icon}</div>
            <h3 className="mt-3 text-lg font-bold">{title}</h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
