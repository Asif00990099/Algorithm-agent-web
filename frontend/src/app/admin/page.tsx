'use client';
import { useState } from 'react';
import { get, patch } from '@/lib/api';
import { useAuthed, usePoll } from '@/lib/hooks';
import { fmtTime } from '@/lib/format';
import { ErrorBox, SectionTitle, Spinner, StatCard } from '@/components/ui';

interface Stats {
  users: number; trades: number; trades_24h: number; signals: number;
  signals_24h: number; articles: number; strategies: number;
  redis_healthy: boolean; server_time: string;
}
interface AdminUser {
  id: string; email: string; username: string; role: string;
  is_active: boolean; demo_balance: number; created_at: string;
}
interface Audit {
  id: string; created_at: string; action: string; user_id: string | null;
  detail: string | null; ip_address: string | null;
}
interface Prompt { id: string; key: string; content: string; description: string; is_active: boolean }

export default function AdminPage() {
  const authed = useAuthed();
  const { data: stats, error } = usePoll<Stats>(authed ? '/admin/stats' : null, 60_000, true);
  const { data: users, reload: reloadUsers } = usePoll<AdminUser[]>(authed ? '/admin/users' : null, 0, true);
  const { data: logs } = usePoll<Audit[]>(authed ? '/admin/audit-logs?limit=50' : null, 60_000, true);
  const { data: prompts } = usePoll<Prompt[]>(authed ? '/admin/prompts' : null, 0, true);
  const [msg, setMsg] = useState('');

  if (!authed) {
    return (
      <div className="glass mx-auto max-w-lg p-8 text-center">
        <h1 className="text-xl font-bold">Admin dashboard</h1>
        <p className="mt-2 text-sm text-slate-500">Sign in with an admin account to continue.</p>
        <a href="/login" className="btn-primary mt-4">Sign in</a>
      </div>
    );
  }
  if (error) {
    return <ErrorBox message={`Admin access required: ${error}`} />;
  }
  if (!stats) return <Spinner />;

  const setRole = async (u: AdminUser, role: string) => {
    try {
      await patch(`/admin/users/${u.id}`, { role });
      reloadUsers();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Update failed');
    }
  };

  return (
    <div className="space-y-8">
      <SectionTitle title="Admin dashboard" sub={`Server time ${fmtTime(stats.server_time)} · Redis ${stats.redis_healthy ? '🟢 healthy' : '🔴 down'}`} />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Users" value={stats.users} />
        <StatCard label="Trades" value={stats.trades} sub={`${stats.trades_24h} in 24h`} />
        <StatCard label="AI signals" value={stats.signals} sub={`${stats.signals_24h} in 24h`} />
        <StatCard label="Articles" value={stats.articles} sub={`${stats.strategies} strategies`} />
      </section>

      {msg && <ErrorBox message={msg} />}

      <section>
        <SectionTitle title="Users" sub="Role management and account control" />
        <div className="glass overflow-x-auto">
          <table className="table-base">
            <thead><tr><th>User</th><th>Email</th><th>Role</th><th>Active</th><th>Demo balance</th><th>Joined</th></tr></thead>
            <tbody>
              {(users ?? []).map((u) => (
                <tr key={u.id} className="table-row-hover">
                  <td className="font-semibold">{u.username}</td>
                  <td>{u.email}</td>
                  <td>
                    <select className="input !w-auto !py-1 text-xs" value={u.role}
                      onChange={(e) => setRole(u, e.target.value)}>
                      {['admin', 'editor', 'trader', 'viewer'].map((r) => <option key={r}>{r}</option>)}
                    </select>
                  </td>
                  <td>
                    <button
                      className={`badge ${u.is_active ? 'bg-bull/15 text-bull' : 'bg-bear/15 text-bear'}`}
                      onClick={async () => { await patch(`/admin/users/${u.id}`, { is_active: !u.is_active }); reloadUsers(); }}>
                      {u.is_active ? 'active' : 'disabled'}
                    </button>
                  </td>
                  <td className="font-mono">${u.demo_balance.toLocaleString()}</td>
                  <td className="text-xs text-slate-400">{fmtTime(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="glass p-4">
          <h3 className="mb-3 font-bold">🧾 Audit log</h3>
          <div className="max-h-96 space-y-1.5 overflow-y-auto pr-1 font-mono text-xs">
            {(logs ?? []).map((l) => (
              <div key={l.id} className="rounded-lg bg-slate-50 px-3 py-1.5 dark:bg-white/[0.04]">
                <span className="text-slate-400">{fmtTime(l.created_at)}</span>{' '}
                <span className="font-bold text-accent">{l.action}</span>{' '}
                <span className="text-slate-500">{l.detail} {l.ip_address && `(${l.ip_address})`}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="glass p-4">
          <h3 className="mb-3 font-bold">🧠 AI prompt templates</h3>
          <div className="space-y-3">
            {(prompts ?? []).map((p) => (
              <details key={p.id} className="rounded-xl bg-slate-50 p-3 dark:bg-white/[0.04]">
                <summary className="cursor-pointer text-sm font-semibold">{p.key}
                  <span className="ml-2 text-xs font-normal text-slate-400">{p.description}</span>
                </summary>
                <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-500">{p.content}</pre>
              </details>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
