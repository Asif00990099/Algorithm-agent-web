'use client';
/** Data hooks: polling fetch, WebSocket streams, auth state. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { get, getTokens, WS_URL } from './api';

export function usePoll<T>(path: string | null, intervalMs = 30_000, auth = false) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!path) return;
    try {
      setData(await get<T>(path, auth));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [path, auth]);

  useEffect(() => {
    setLoading(true);
    load();
    if (!intervalMs) return;
    const id = setInterval(load, intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs]);

  return { data, error, loading, reload: load };
}

/** Subscribe to live topics over the platform WebSocket. */
export function useLiveTopic<T>(topics: string[], onMessage: (topic: string, data: T) => void) {
  const cbRef = useRef(onMessage);
  cbRef.current = onMessage;
  const key = topics.join(',');

  useEffect(() => {
    if (!key) return;
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 1000;

    const connect = () => {
      ws = new WebSocket(WS_URL);
      ws.onopen = () => {
        retry = 1000;
        ws?.send(JSON.stringify({ op: 'subscribe', topics: key.split(',') }));
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.topic) cbRef.current(msg.topic, msg.data);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (!closed) {
          setTimeout(connect, retry);
          retry = Math.min(retry * 2, 15_000);
        }
      };
    };
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [key]);
}

export function useAuthed() {
  const [authed, setAuthed] = useState(false);
  useEffect(() => {
    const update = () => setAuthed(!!getTokens());
    update();
    window.addEventListener('qp-auth-changed', update);
    window.addEventListener('storage', update);
    return () => {
      window.removeEventListener('qp-auth-changed', update);
      window.removeEventListener('storage', update);
    };
  }, []);
  return authed;
}
