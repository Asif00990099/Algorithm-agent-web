'use client';
import { useState } from 'react';
import { usePoll } from '@/lib/hooks';
import { fmtTime } from '@/lib/format';
import { ErrorBox, SectionTitle, Spinner } from '@/components/ui';

interface Event {
  id: string; title: string; country: string; category: string; importance: number;
  event_time: string | null; actual: string | null; forecast: string | null;
  previous: string | null; source: string; url: string;
}

const FLAGS: Record<string, string> = { US: '🇺🇸', EU: '🇪🇺', GB: '🇬🇧', JP: '🇯🇵' };

export default function CalendarPage() {
  const [importance, setImportance] = useState(1);
  const { data, error, loading } = usePoll<Event[]>(`/intel/calendar?importance=${importance}`, 300_000);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Economic calendar"
        sub="FOMC, CPI, PPI, NFP, GDP, rates and central-bank announcements (Fed · ECB · BoE · BoJ)"
        right={
          <div className="flex gap-1">
            {[1, 2, 3].map((lvl) => (
              <button key={lvl} onClick={() => setImportance(lvl)}
                className={`rounded-xl px-3 py-1.5 text-sm font-semibold ${importance === lvl ? 'bg-accent text-white' : 'bg-slate-100 dark:bg-white/10'}`}>
                {'★'.repeat(lvl)}+
              </button>
            ))}
          </div>
        }
      />
      {loading && <Spinner />}
      {error && <ErrorBox message={error} />}
      {data && (
        <div className="space-y-2">
          {data.map((e) => (
            <a key={e.id} href={e.url || undefined} target="_blank" rel="noopener"
              className="glass glass-hover flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="text-xl">{FLAGS[e.country] ?? '🌐'}</span>
              <span className={`badge ${e.importance === 3 ? 'bg-bear/15 text-bear' : e.importance === 2 ? 'bg-amber-400/15 text-amber-500' : 'bg-slate-100 text-slate-500 dark:bg-white/10'}`}>
                {'★'.repeat(e.importance)}
              </span>
              <span className="badge bg-accent/10 text-accent">{e.category}</span>
              <span className="grow font-medium">{e.title}</span>
              <span className="text-xs text-slate-400">
                {e.event_time ? fmtTime(e.event_time) : e.source}
                {e.actual && ` · actual ${e.actual}`}
                {e.forecast && ` · fcst ${e.forecast}`}
              </span>
            </a>
          ))}
          {data.length === 0 && (
            <p className="py-10 text-center text-sm text-slate-400">
              No events stored yet. The calendar worker syncs hourly (FRED_API_KEY enables US release
              schedules; central-bank feeds work without keys).
            </p>
          )}
        </div>
      )}
    </div>
  );
}
