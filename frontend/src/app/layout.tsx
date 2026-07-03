import type { Metadata, Viewport } from 'next';
import Navbar from '@/components/Navbar';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'QuantPulse — AI Automated Trading Platform',
    template: '%s | QuantPulse',
  },
  description:
    'Enterprise-grade AI trading platform: real-time crypto, stock and forex monitoring, ' +
    'AI trading signals, automated news, portfolio management and strategy backtesting.',
  keywords: ['AI trading', 'crypto signals', 'backtesting', 'market scanner', 'trading bot'],
  openGraph: {
    title: 'QuantPulse — AI Automated Trading Platform',
    description: 'Real-time markets, AI signals, automated trading and news — 24/7.',
    type: 'website',
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#0b1020' },
    { media: '(prefers-color-scheme: light)', color: '#f6f7fb' },
  ],
};

const themeInit = `
try {
  const stored = localStorage.getItem('qp_theme');
  const dark = stored ? stored === 'dark'
    : window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (dark) document.documentElement.classList.add('dark');
} catch (e) {}
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="min-h-screen">
        <Navbar />
        <main className="mx-auto w-full max-w-7xl px-4 pb-16 pt-6 sm:px-6">{children}</main>
        <footer className="border-t border-slate-200 py-8 text-center text-xs text-slate-500 dark:border-white/10">
          QuantPulse — AI market intelligence. Market data is informational only and not
          financial advice. Trading involves substantial risk.
        </footer>
      </body>
    </html>
  );
}
