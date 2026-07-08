'use client';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { API_BASE, mediaUrl } from '@/lib/api';
import { fmtTime } from '@/lib/format';
import { Spinner } from '@/components/ui';

interface Article {
  title: string; summary: string; content: string; featured_image_url: string;
  source_name: string; source_url: string; published_at: string | null;
  sentiment: number | null; symbols: string; view_count: number;
  seo_description: string; is_auto_generated: boolean;
  tags?: { name: string; slug: string }[];
}

/** Minimal safe markdown renderer for headings / bold / links / paragraphs. */
function renderMarkdown(md: string | null | undefined): string {
  if (!md || typeof md !== 'string') return '';
  const escape = (s: string) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return escape(md)
    .replace(/^## (.+)$/gm, '<h2 class="mt-6 mb-2 text-xl font-bold">$1</h2>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener nofollow" class="text-accent underline">$1</a>')
    .split(/\n{2,}/)
    .map((p) => (p.startsWith('<h2') ? p : `<p class="my-3 leading-relaxed">${p.replace(/\n/g, '<br/>')}</p>`))
    .join('');
}

export default function ArticlePage() {
  const { slug } = useParams<{ slug: string }>();
  const url = slug ? `${API_BASE}/api/v1/news/${slug}` : '';
  const [a, setA] = useState<Article | null>(null);
  const [diag, setDiag] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!url) return;
    setLoading(true);
    try {
      const r = await fetch(url);
      const text = await r.text();
      if (!r.ok) {
        setA(null);
        setDiag(`HTTP ${r.status} · ${text.slice(0, 240) || '(empty body)'}`);
      } else if (!text.trim()) {
        setA(null);
        setDiag(`HTTP ${r.status} · empty body`);
      } else {
        try {
          setA(JSON.parse(text) as Article);
          setDiag('');
        } catch {
          setA(null);
          setDiag(`HTTP ${r.status} · non-JSON body: ${text.slice(0, 200)}`);
        }
      }
    } catch (e) {
      setA(null);
      setDiag(`Network/CORS error: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <Spinner />;
  if (!a) {
    return (
      <div className="mx-auto max-w-3xl py-12 text-center">
        <h1 className="text-2xl font-bold">This article couldn’t be loaded</h1>
        <p className="mt-2 break-all text-xs text-slate-400">Tried: {url}</p>
        <p className="mt-1 break-all text-sm text-slate-500">{diag}</p>
        <div className="mt-5 flex justify-center gap-3">
          <button onClick={load} className="btn-ghost">Retry</button>
          <Link href="/news" className="btn-ghost">← Back to news</Link>
        </div>
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-3xl">
      <h1 className="text-3xl font-extrabold leading-tight">{a.title}</h1>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-400">
        <span>{fmtTime(a.published_at)}</span>
        <span>· {a.view_count} views</span>
        {a.is_auto_generated && <span className="badge bg-accent/10 text-accent">AI news desk</span>}
        {(a.symbols ?? '').split(',').filter(Boolean).map((s) => (
          <span key={s} className="badge bg-slate-100 uppercase dark:bg-white/10">{s}</span>
        ))}
      </div>
      {a.featured_image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(a.featured_image_url)} alt="" className="mt-6 w-full rounded-2xl" />
      )}
      {a.summary && (
        <p className="mt-6 text-lg font-medium text-slate-600 dark:text-slate-300">{a.summary}</p>
      )}
      <div className="prose-custom mt-4 text-slate-700 dark:text-slate-200"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(a.content) || `<p>${a.summary || ''}</p>` }} />
      {a.source_url && (
        <p className="mt-8 border-t border-slate-200 pt-4 text-sm text-slate-400 dark:border-white/10">
          Original reporting:{' '}
          <a href={a.source_url} target="_blank" rel="noopener nofollow" className="text-accent underline">
            {a.source_name || a.source_url}
          </a>
        </p>
      )}
      {a.tags && a.tags.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {a.tags.map((t) => <span key={t.slug} className="badge bg-slate-100 dark:bg-white/10">#{t.name}</span>)}
        </div>
      )}
    </article>
  );
}
