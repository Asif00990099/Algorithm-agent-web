'use client';
import Link from 'next/link';

/** Route-level error boundary: a render/runtime error here shows a message and
 *  a recovery path instead of a blank page. */
export default function ArticleError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-3xl py-12 text-center">
      <h1 className="text-2xl font-bold">Something went wrong loading this article</h1>
      <p className="mt-2 text-sm text-slate-400">{error?.message || 'Unexpected error.'}</p>
      <div className="mt-5 flex justify-center gap-3">
        <button onClick={reset} className="btn-ghost">Try again</button>
        <Link href="/news" className="btn-ghost">← Back to news</Link>
      </div>
    </div>
  );
}
