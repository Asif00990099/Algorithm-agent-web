'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { post, setTokens } from '@/lib/api';
import { ErrorBox } from '@/components/ui';

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({ email: '', username: '', password: '' });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr('');
    try {
      await post('/auth/register', form);
      const tokens = await post<{ access_token: string; refresh_token: string }>('/auth/login', {
        email: form.email, password: form.password,
      });
      setTokens(tokens);
      router.push('/portfolio');
    } catch (ex) {
      setErr(ex instanceof Error ? ex.message : 'Registration failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-md">
      <div className="glass p-8">
        <h1 className="text-2xl font-extrabold">Create your account</h1>
        <p className="mt-1 text-sm text-slate-500">
          Start with a <b>$100,000 demo balance</b> filled at live market prices.
        </p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Email</label>
            <input type="email" required autoComplete="email" className="input mt-1"
              value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Username</label>
            <input required minLength={3} maxLength={32} pattern="[a-zA-Z0-9_\-]+" className="input mt-1"
              value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-semibold uppercase text-slate-500">Password</label>
            <input type="password" required minLength={10} autoComplete="new-password" className="input mt-1"
              value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <p className="mt-1 text-xs text-slate-400">At least 10 characters with letters and digits.</p>
          </div>
          {err && <ErrorBox message={err} />}
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? 'Creating account…' : 'Create account'}
          </button>
        </form>
        <p className="mt-4 text-center text-sm text-slate-500">
          Already registered? <Link href="/login" className="font-semibold text-accent">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
