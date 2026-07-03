'use client';
/** Admin "Settings" panel — grouped, schema-driven settings that persist to
    the database via the admin API. */
import { useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { usePoll } from '@/lib/hooks';
import { Spinner } from '@/components/ui';

interface Setting {
  key: string;
  group: string;
  type: 'text' | 'textarea' | 'bool' | 'number' | 'select' | 'color';
  label: string;
  default: string | number | boolean;
  value: string | number | boolean;
  options?: string[];
}

function Field({
  s,
  value,
  onChange,
}: {
  s: Setting;
  value: string | number | boolean;
  onChange: (v: string | number | boolean) => void;
}) {
  if (s.type === 'bool') {
    return (
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative h-6 w-11 rounded-full transition ${value ? 'bg-accent' : 'bg-slate-300 dark:bg-white/20'}`}
        aria-pressed={!!value}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${value ? 'left-[22px]' : 'left-0.5'}`} />
      </button>
    );
  }
  if (s.type === 'textarea') {
    return (
      <textarea className="input min-h-[70px]" value={String(value)}
        onChange={(e) => onChange(e.target.value)} />
    );
  }
  if (s.type === 'select') {
    return (
      <select className="input" value={String(value)} onChange={(e) => onChange(e.target.value)}>
        {(s.options ?? []).map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  if (s.type === 'color') {
    return (
      <div className="flex items-center gap-2">
        <input type="color" value={String(value)} onChange={(e) => onChange(e.target.value)}
          className="h-9 w-12 rounded border border-slate-300 dark:border-white/15" />
        <span className="font-mono text-xs">{String(value)}</span>
      </div>
    );
  }
  return (
    <input type={s.type === 'number' ? 'number' : 'text'} className="input"
      value={String(value)} onChange={(e) => onChange(e.target.value)} />
  );
}

export default function AdminSettings() {
  const { data, loading, reload } = usePoll<Setting[]>('/admin/settings', 0, true);
  const [draft, setDraft] = useState<Record<string, string | number | boolean>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');

  useEffect(() => {
    if (data) {
      setDraft(Object.fromEntries(data.map((s) => [s.key, s.value])));
    }
  }, [data]);

  const groups = useMemo(() => {
    const g: Record<string, Setting[]> = {};
    (data ?? []).forEach((s) => { (g[s.group] ??= []).push(s); });
    return g;
  }, [data]);

  const dirty = useMemo(() => {
    if (!data) return false;
    return data.some((s) => draft[s.key] !== s.value);
  }, [data, draft]);

  const save = async () => {
    if (!data) return;
    setBusy(true);
    setNote('');
    try {
      const changed: Record<string, string | number | boolean> = {};
      data.forEach((s) => { if (draft[s.key] !== s.value) changed[s.key] = draft[s.key]; });
      await api('/admin/settings', { method: 'PUT', body: JSON.stringify({ values: changed }), auth: true });
      setNote('Settings saved ✓');
      reload();
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="glass p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-bold">⚙️ Settings</h3>
        <div className="flex items-center gap-3">
          {note && <span className="text-xs text-slate-400">{note}</span>}
          <button className="btn-primary" onClick={save} disabled={busy || !dirty}>
            {busy ? 'Saving…' : dirty ? 'Save changes' : 'Saved'}
          </button>
        </div>
      </div>
      {loading && <Spinner label="Loading settings…" />}
      <div className="grid gap-6 lg:grid-cols-2">
        {Object.entries(groups).map(([group, items]) => (
          <div key={group} className="rounded-xl border border-slate-100 p-3 dark:border-white/5">
            <h4 className="mb-2 text-xs font-bold uppercase tracking-wide text-accent">{group}</h4>
            <div className="space-y-2.5">
              {items.map((s) => (
                <div key={s.key} className="flex items-center justify-between gap-3">
                  <label className="text-sm">{s.label}</label>
                  <div className="min-w-[45%] max-w-[55%]">
                    <Field s={s} value={draft[s.key] ?? s.value}
                      onChange={(v) => setDraft((d) => ({ ...d, [s.key]: v }))} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
