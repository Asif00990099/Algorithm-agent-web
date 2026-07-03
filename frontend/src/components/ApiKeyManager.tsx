'use client';
/** Admin "API Management" panel — add/update/remove external API keys.
    Keys are sent to the backend, stored encrypted, and applied live. */
import { useState } from 'react';
import { del, api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { Spinner } from '@/components/ui';

interface ProviderStatus {
  provider: string;
  label: string;
  category: string;
  signup_url: string;
  configured: boolean;
  masked: string;
  source: string; // database | environment | none
}

function Row({ p, onSaved }: { p: ProviderStatus; onSaved: () => void }) {
  const [value, setValue] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');

  const save = async () => {
    if (!value.trim()) return;
    setBusy(true);
    setNote('');
    try {
      await api(`/admin/api-keys/${p.provider}`, {
        method: 'PUT',
        body: JSON.stringify({ value: value.trim() }),
        auth: true,
      });
      setValue('');
      setNote('saved ✓');
      onSaved();
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'failed');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await del(`/admin/api-keys/${p.provider}`);
      onSaved();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 py-2.5 dark:border-white/5">
      <div className="min-w-44">
        <div className="flex items-center gap-2 font-semibold">
          {p.label}
          <span className={`h-2 w-2 rounded-full ${p.configured ? 'bg-bull' : 'bg-slate-300 dark:bg-white/20'}`} />
        </div>
        <a href={p.signup_url} target="_blank" rel="noopener"
          className="text-xs text-accent hover:underline">get key ↗</a>
      </div>
      <div className="min-w-24 text-xs">
        <span className="badge bg-slate-100 dark:bg-white/10">{p.category}</span>
      </div>
      <div className="min-w-28 font-mono text-xs text-slate-500">
        {p.configured ? p.masked : <span className="italic text-slate-400">not set</span>}
        <div className="text-[10px] uppercase tracking-wide text-slate-400">{p.source}</div>
      </div>
      <input
        type="password"
        className="input max-w-56 flex-1 font-mono"
        placeholder={p.configured ? 'replace key…' : 'paste key…'}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && save()}
      />
      <button className="btn-primary !py-1.5 text-xs" onClick={save} disabled={busy || !value.trim()}>
        {busy ? '…' : 'Save'}
      </button>
      {p.source === 'database' && (
        <button className="btn-ghost !py-1.5 text-xs" onClick={remove} disabled={busy}>Remove</button>
      )}
      {note && <span className="text-xs text-slate-400">{note}</span>}
    </div>
  );
}

export default function ApiKeyManager() {
  const { data, loading, reload } = usePoll<ProviderStatus[]>('/admin/api-keys', 0, true);

  return (
    <section className="glass p-4">
      <h3 className="font-bold">🔑 API Management</h3>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
        Add your API keys here — they are encrypted, stored in the database, and applied
        immediately (no redeploy). DB keys override environment variables.
      </p>
      {loading && <Spinner label="Loading providers…" />}
      <div className="divide-y divide-transparent">
        {(data ?? []).map((p) => (
          <Row key={p.provider} p={p} onSaved={reload} />
        ))}
      </div>
    </section>
  );
}
