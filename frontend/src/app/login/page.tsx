'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { post, setTokens } from '@/lib/api';
import { ErrorBox } from '@/components/ui';

export default function LoginPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: '', password: '', totp_code: '' });
  const [needTotp, setNeedTotp] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      const tokens = await post<{ access_token: string; refresh_token: string }>('/auth/login', {
        email: form.email,
        password: form.password,
        totp_code: form.totp_code || null,
      });
      setTokens(tokens);
      router.push('/portfolio');
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : 'Login failed';
      if (msg.toLowerCase().includes('2fa')) setNeedTotp(true);
      setErr(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <div className="glass p-8">
        <h1 className="text-2xl font-extrabold">Welcome back</h1>
        <p className="mt-1 text-sm text-slate-500">Sign in to your QuantPulse account.</p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Email</label>
            <input type="email" required autoComplete="email" className="input mt-1"
              value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Password</label>
            <input type="password" required autoComplete="current-password" className="input mt-1"
              value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
          {needTotp && (
            <div>
              <label className="text-xs font-semibold uppercase text-slate-500">2FA code</label>
              <input inputMode="numeric" maxLength={8} className="input mt-1 font-mono"
                value={form.totp_code} onChange={(e) => setForm({ ...form, totp_code: e.target.value })} />
            </div>
          )}
          {err && <ErrorBox message={err} />}
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">
          No account? <Link href="/register" className="font-semibold text-accent">Create one free</Link>
        </p>
      </div>
    </div>
  );
}
