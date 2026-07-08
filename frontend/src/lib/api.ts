/** Typed API client with JWT handling and automatic token refresh. */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, '') || 'http://localhost:8000';
export const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ||
  API_BASE.replace(/^http/, 'ws') + '/api/v1/ws/stream';

const V1 = `${API_BASE}/api/v1`;

/** Resolve a media URL that may be backend-relative (e.g. the self-hosted
 *  og-image endpoint "/api/v1/media/og-image…"). Relative paths must point at
 *  the API host, not the frontend origin, or they 404 on Vercel. */
export function mediaUrl(u: string | null | undefined): string {
  if (!u) return '';
  if (/^https?:\/\//i.test(u) || u.startsWith('data:')) return u;
  return `${API_BASE}${u.startsWith('/') ? '' : '/'}${u}`;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getTokens() {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem('qp_tokens');
  return raw ? (JSON.parse(raw) as { access_token: string; refresh_token: string }) : null;
}

export function setTokens(tokens: { access_token: string; refresh_token: string } | null) {
  if (typeof window === 'undefined') return;
  if (tokens) localStorage.setItem('qp_tokens', JSON.stringify(tokens));
  else localStorage.removeItem('qp_tokens');
  window.dispatchEvent(new Event('qp-auth-changed'));
}

async function refreshTokens(): Promise<boolean> {
  const tokens = getTokens();
  if (!tokens) return false;
  try {
    const resp = await fetch(`${V1}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    });
    if (!resp.ok) return false;
    setTokens(await resp.json());
    return true;
  } catch {
    return false;
  }
}

export async function api<T = unknown>(
  path: string,
  options: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const { auth = false, ...init } = options;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  };
  if (auth) {
    const tokens = getTokens();
    if (tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
  }
  let resp = await fetch(`${V1}${path}`, { ...init, headers });
  if (resp.status === 401 && auth && (await refreshTokens())) {
    const tokens = getTokens();
    if (tokens) headers.Authorization = `Bearer ${tokens.access_token}`;
    resp = await fetch(`${V1}${path}`, { ...init, headers });
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export const get = <T>(path: string, auth = false) => api<T>(path, { auth });
export const post = <T>(path: string, body?: unknown, auth = false) =>
  api<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined, auth });
export const patch = <T>(path: string, body: unknown, auth = true) =>
  api<T>(path, { method: 'PATCH', body: JSON.stringify(body), auth });
export const del = <T>(path: string, auth = true) => api<T>(path, { method: 'DELETE', auth });
