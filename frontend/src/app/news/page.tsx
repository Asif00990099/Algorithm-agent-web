'use client';
import Link from 'next/link';
import { useState } from 'react';
import { usePoll } from '@/lib/hooks';
import { timeAgo } from '@/lib/format';
import { ErrorBox, SectionTitle, Spinner } from '@/components/ui';

interface Article {
  id: string; title: string; slug: string; summary: string;
  featured_image_url: string; sentiment: number | null; symbols: string;
  source_name: string; published_at: string | null; is_auto_generated: boolean;
}
interface NewsPage { items: Article[]; total: number; page: number; page_size: number }
interface Category { id: string; name: string; slug: string }

function SentimentDot({ score }: { score: number | null }) {
  if (score === null) return null;
  const color = score > 0.15 ? 'bg-bull' : score < -0.15 ? 'bg-bear' : 'bg-slate-400';
  const label = score > 0.15 ? 'positive' : score < -0.15 ? 'negative' : 'neutral';
  return (
    <span className="flex items-center gap-1 text-xs text-slate-400">
      <span className={`h-2 w-2 rounded-full ${color}`} /> {label}
    </span>
  );
}

export default function NewsPage() {
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState('');
  const { data, error, loading } = usePoll<NewsPage>(
    `/news?page=${page}&page_size=18${category ? `&category=${category}` : ''}`, 120_000);
  const { data: categories } = usePoll<Category[]>('/news/categories', 0);

  return (
    <div className="space-y-6">
      <SectionTitle
        title="Market news"
        sub="Original articles written by the automated news desk from dozens of live sources"
      />
      <div className="flex flex-wrap gap-1">
        <button onClick={() => setCategory('')}
          className={`rounded-xl px-3 py-1.5 text-sm font-semibold ${!category ? 'bg-accent text-white' : 'bg-slate-100 dark:bg-white/10'}`}>
          All
        </button>
        {(categories ?? []).map((c) => (
          <button key={c.id} onClick={() => { setCategory(c.slug); setPage(1); }}
            className={`rounded-xl px-3 py-1.5 text-sm font-semibold ${category === c.slug ? 'bg-accent text-white' : 'bg-slate-100 dark:bg-white/10'}`}>
            {c.name}
          </button>
        ))}
      </div>

      {loading && <Spinner />}
      {error && <ErrorBox message={error} />}
      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((a) => (
              <Link key={a.id} href={`/news/${a.slug}`} className="glass glass-hover flex flex-col overflow-hidden">
                {a.featured_image_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={a.featured_image_url} alt="" className="aspect-[1200/630] w-full object-cover" loading="lazy" />
                )}
                <div className="flex grow flex-col p-4">
                  <h3 className="line-clamp-2 font-bold leading-snug">{a.title}</h3>
                  <p className="mt-2 line-clamp-3 grow text-sm text-slate-500 dark:text-slate-400">{a.summary}</p>
                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                    <SentimentDot score={a.sentiment} />
                    <span>{a.source_name && `via ${a.source_name} · `}{timeAgo(a.published_at)}</span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
          {data.items.length === 0 && (
            <p className="py-10 text-center text-sm text-slate-400">
              No articles yet — the news worker publishes fresh stories every 10 minutes.
            </p>
          )}
          <div className="flex items-center justify-center gap-3">
            <button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button>
            <span className="text-sm text-slate-500">Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))}</span>
            <button className="btn-ghost" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next →</button>
          </div>
        </>
      )}
    </div>
  );
}
