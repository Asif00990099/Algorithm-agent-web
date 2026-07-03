'use client';
import { useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import CandleChart, { Ohlcv } from '@/components/CandleChart';
import { useLiveTopic, usePoll } from '@/lib/hooks';
import { fmtCompact, fmtPct, fmtUsd, pctClass } from '@/lib/format';
import { ErrorBox, PctBadge, SectionTitle, Spinner, StatCard } from '@/components/ui';

const INTERVALS = ['15m', '1h', '4h', '1d'] as const;

interface CoinDetail {
  id: string; symbol: string; name: string;
  image: { large: string };
  market_cap_rank: number;
  market_data: {
    current_price: { usd: number };
    market_cap: { usd: number };
    total_volume: { usd: number };
    high_24h: { usd: number }; low_24h: { usd: number };
    price_change_percentage_24h: number;
    price_change_percentage_7d: number;
    price_change_percentage_30d: number;
    ath: { usd: number }; ath_date: { usd: string };
    atl: { usd: number }; atl_date: { usd: string };
    circulating_supply: number; total_supply: number;
  };
}

interface Indicators {
  price: number; rsi_14: number | null; macd: number | null; macd_signal: number | null;
  macd_hist: number | null; atr_14: number | null; adx_14: number | null;
  stoch_rsi_k: number | null; stoch_rsi_d: number | null;
  ema_9: number | null; ema_21: number | null; ema_50: number | null;
  sma_20: number | null; sma_50: number | null; sma_200: number | null;
  vwap: number | null; bb_upper: number | null; bb_middle: number | null; bb_lower: number | null;
  supertrend: number | null; supertrend_dir: number | null;
  ichimoku_tenkan: number | null; ichimoku_kijun: number | null;
  support: number[]; resistance: number[]; fibonacci: Record<string, number>;
  trend_strength: number; momentum: number;
  year_high: number | null; year_low: number | null;
}

interface Derivatives {
  funding: { lastFundingRate: string; markPrice: string } | null;
  open_interest: { openInterest: string } | null;
}

function IndicatorRow({ name, value, hint }: { name: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 py-1.5 text-sm last:border-0 dark:border-white/5">
      <span className="text-slate-500 dark:text-slate-400">{name}</span>
      <span className="font-mono font-semibold">{value}{hint && <span className="ml-1 text-xs font-normal text-slate-400">{hint}</span>}</span>
    </div>
  );
}

export default function CoinPage() {
  const params = useParams<{ symbol: string }>();
  const coinId = params.symbol;
  const [interval, setInterval_] = useState<(typeof INTERVALS)[number]>('1h');
  const [livePrice, setLivePrice] = useState<number | null>(null);

  const { data: coin, error: coinErr, loading } = usePoll<CoinDetail>(`/market/coins/${coinId}`, 120_000);
  const pair = coin ? `${coin.symbol.toUpperCase()}USDT` : null;

  const { data: ohlcv } = usePoll<Ohlcv>(pair ? `/market/klines/${pair}?interval=${interval}&limit=300` : null, 60_000);
  const { data: ind } = usePoll<Indicators>(pair ? `/market/indicators/${pair}?interval=${interval}` : null, 60_000);
  const { data: deriv } = usePoll<Derivatives>(pair ? `/market/derivatives/${pair}` : null, 60_000);

  useLiveTopic<{ price: string }>(
    pair ? [`prices:${pair}`] : [],
    (_topic, data) => setLivePrice(parseFloat(data.price)),
  );

  const md = coin?.market_data;
  const price = livePrice ?? md?.current_price.usd;

  const macdState = useMemo(() => {
    if (!ind?.macd_hist) return null;
    return ind.macd_hist > 0 ? 'Bullish' : 'Bearish';
  }, [ind]);

  if (loading) return <Spinner />;
  if (coinErr) return <ErrorBox message={`Coin unavailable: ${coinErr}`} />;
  if (!coin || !md) return null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center gap-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={coin.image.large} alt="" className="h-12 w-12 rounded-full" />
        <div>
          <h1 className="text-2xl font-extrabold">
            {coin.name} <span className="text-base uppercase text-slate-400">{coin.symbol}</span>
            <span className="badge ml-2 bg-accent/10 text-accent">Rank #{coin.market_cap_rank}</span>
          </h1>
          <div className="mt-1 flex items-center gap-3">
            <span className="font-mono text-3xl font-bold">{fmtUsd(price)}</span>
            <PctBadge value={md.price_change_percentage_24h} />
            {livePrice && <span className="badge animate-pulse-soft bg-bull/10 text-bull">● LIVE</span>}
          </div>
        </div>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Market cap" value={fmtCompact(md.market_cap.usd)} />
        <StatCard label="24h volume" value={fmtCompact(md.total_volume.usd)} />
        <StatCard
          label="ATH / ATL"
          value={<span className="text-base">{fmtUsd(md.ath.usd)} / {fmtUsd(md.atl.usd)}</span>}
          sub={`ATH ${new Date(md.ath_date.usd).toLocaleDateString()}`}
        />
        <StatCard
          label="Supply"
          value={fmtCompact(md.circulating_supply)}
          sub={md.total_supply ? `of ${fmtCompact(md.total_supply)} total` : 'no max supply'}
        />
      </section>

      <section className="glass p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold">Candlestick chart {pair && <span className="text-sm font-normal text-slate-400">({pair} · Binance)</span>}</h2>
          <div className="flex gap-1">
            {INTERVALS.map((iv) => (
              <button
                key={iv}
                onClick={() => setInterval_(iv)}
                className={`rounded-lg px-3 py-1 text-xs font-semibold transition ${
                  interval === iv ? 'bg-accent text-white' : 'bg-slate-100 dark:bg-white/10'
                }`}
              >
                {iv}
              </button>
            ))}
          </div>
        </div>
        {ohlcv ? <CandleChart data={ohlcv} /> : <Spinner label="Loading candles…" />}
      </section>

      <div className="grid gap-4 lg:grid-cols-3">
        <section className="glass p-4">
          <h3 className="mb-2 font-bold">Momentum</h3>
          <IndicatorRow name="RSI (14)" value={ind?.rsi_14?.toFixed(1) ?? '—'}
            hint={ind?.rsi_14 ? (ind.rsi_14 > 70 ? 'overbought' : ind.rsi_14 < 30 ? 'oversold' : '') : ''} />
          <IndicatorRow name="MACD" value={ind?.macd?.toFixed(4) ?? '—'} hint={macdState ?? ''} />
          <IndicatorRow name="MACD signal" value={ind?.macd_signal?.toFixed(4) ?? '—'} />
          <IndicatorRow name="Stoch RSI %K/%D" value={`${ind?.stoch_rsi_k?.toFixed(1) ?? '—'} / ${ind?.stoch_rsi_d?.toFixed(1) ?? '—'}`} />
          <IndicatorRow name="ADX (14)" value={ind?.adx_14?.toFixed(1) ?? '—'} />
          <IndicatorRow name="ATR (14)" value={ind?.atr_14?.toFixed(4) ?? '—'} />
          <IndicatorRow
            name="Trend strength"
            value={<span className={ (ind?.trend_strength ?? 0) > 50 ? 'text-bull' : ''}>{ind?.trend_strength?.toFixed(0) ?? '—'}/100</span>}
          />
          <IndicatorRow
            name="Momentum"
            value={<span className={pctClass(ind?.momentum)}>{ind?.momentum?.toFixed(0) ?? '—'}</span>}
          />
        </section>

        <section className="glass p-4">
          <h3 className="mb-2 font-bold">Moving averages &amp; bands</h3>
          <IndicatorRow name="EMA 9 / 21 / 50" value={`${fmtUsd(ind?.ema_9)} / ${fmtUsd(ind?.ema_21)} / ${fmtUsd(ind?.ema_50)}`} />
          <IndicatorRow name="SMA 20 / 50 / 200" value={`${fmtUsd(ind?.sma_20)} / ${fmtUsd(ind?.sma_50)} / ${fmtUsd(ind?.sma_200)}`} />
          <IndicatorRow name="VWAP" value={fmtUsd(ind?.vwap)} />
          <IndicatorRow name="Bollinger upper" value={fmtUsd(ind?.bb_upper)} />
          <IndicatorRow name="Bollinger lower" value={fmtUsd(ind?.bb_lower)} />
          <IndicatorRow
            name="SuperTrend"
            value={
              <span className={ind?.supertrend_dir === 1 ? 'text-bull' : 'text-bear'}>
                {fmtUsd(ind?.supertrend)} {ind?.supertrend_dir === 1 ? '▲' : '▼'}
              </span>
            }
          />
          <IndicatorRow name="Ichimoku tenkan/kijun" value={`${fmtUsd(ind?.ichimoku_tenkan)} / ${fmtUsd(ind?.ichimoku_kijun)}`} />
        </section>

        <section className="glass p-4">
          <h3 className="mb-2 font-bold">Levels &amp; derivatives</h3>
          <IndicatorRow name="Resistance" value={ind?.resistance?.slice(0, 3).map(fmtUsd).join(' · ') || '—'} />
          <IndicatorRow name="Support" value={ind?.support?.slice(0, 3).map(fmtUsd).join(' · ') || '—'} />
          <IndicatorRow name="Fib 0.382 / 0.618" value={`${fmtUsd(ind?.fibonacci?.['0.382'])} / ${fmtUsd(ind?.fibonacci?.['0.618'])}`} />
          <IndicatorRow
            name="Funding rate"
            value={
              deriv?.funding
                ? <span className={pctClass(parseFloat(deriv.funding.lastFundingRate))}>{(parseFloat(deriv.funding.lastFundingRate) * 100).toFixed(4)}%</span>
                : '—'
            }
          />
          <IndicatorRow name="Open interest" value={deriv?.open_interest ? fmtCompact(parseFloat(deriv.open_interest.openInterest)) : '—'} />
          <IndicatorRow name="24h range" value={`${fmtUsd(md.low_24h.usd)} – ${fmtUsd(md.high_24h.usd)}`} />
          <IndicatorRow name="52-week range" value={`${fmtUsd(ind?.year_low)} – ${fmtUsd(ind?.year_high)}`} />
          <IndicatorRow name="7d / 30d" value={
            <>
              <span className={pctClass(md.price_change_percentage_7d)}>{fmtPct(md.price_change_percentage_7d)}</span>
              {' / '}
              <span className={pctClass(md.price_change_percentage_30d)}>{fmtPct(md.price_change_percentage_30d)}</span>
            </>
          } />
        </section>
      </div>
    </div>
  );
}
