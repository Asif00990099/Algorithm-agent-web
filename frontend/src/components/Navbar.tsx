'use client';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import { setTokens } from '@/lib/api';
import { useAuthed } from '@/lib/hooks';

const LINKS = [
  { href: '/markets', label: 'Markets' },
  { href: '/scanner', label: 'Scanner' },
  { href: '/signals', label: 'AI Signals' },
  { href: '/trading', label: 'Trading' },
  { href: '/backtest', label: 'Backtest' },
  { href: '/portfolio', label: 'Portfolio' },
  { href: '/news', label: 'News' },
  { href: '/calendar', label: 'Calendar' },
];

function ThemeToggle() {
  const [, force] = useState(0);
  const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
  return (
    <button
      aria-label="Toggle theme"
      className="btn-ghost !px-3"
      onClick={() => {
        const next = !document.documentElement.classList.contains('dark');
        document.documentElement.classList.toggle('dark', next);
        localStorage.setItem('qp_theme', next ? 'dark' : 'light');
        force((x) => x + 1);
      }}
    >
      {isDark ? '☀️' : '🌙'}
    </button>
  );
}

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const authed = useAuthed();
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/80 backdrop-blur-lg dark:border-white/10 dark:bg-surface-dark/80">
      <nav className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2 font-extrabold tracking-tight">
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-accent text-white shadow-md shadow-accent/30">
            Q
          </span>
          <span className="hidden sm:block">
            Quant<span className="text-accent">Pulse</span>
          </span>
        </Link>

        <div className="ml-4 hidden items-center gap-1 lg:flex">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                pathname?.startsWith(l.href)
                  ? 'bg-accent/10 text-accent'
                  : 'text-slate-600 hover:text-accent dark:text-slate-300'
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          {authed ? (
            <>
              <Link href="/admin" className="btn-ghost hidden sm:inline-flex">
                Dashboard
              </Link>
              <button
                className="btn-primary"
                onClick={() => {
                  setTokens(null);
                  router.push('/');
                }}
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-ghost hidden sm:inline-flex">
                Sign in
              </Link>
              <Link href="/register" className="btn-primary">
                Get started
              </Link>
            </>
          )}
          <button
            aria-label="Menu"
            className="btn-ghost !px-3 lg:hidden"
            onClick={() => setOpen(!open)}
          >
            ☰
          </button>
        </div>
      </nav>
      {open && (
        <div className="grid grid-cols-2 gap-1 border-t border-slate-200/70 px-4 py-3 dark:border-white/10 lg:hidden">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className="rounded-lg px-3 py-2 text-sm font-medium hover:bg-accent/10"
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
