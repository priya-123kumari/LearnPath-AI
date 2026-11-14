import { useCallback, useEffect, useState } from "react";

/** The frontend's only data source: the backend REST API (proxied at /api by Vite). */
export async function api(path, options = {}) {
  const r = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(body.message ?? `HTTP ${r.status}`);
    err.code = body.error ?? `HTTP_${r.status}`;
    err.status = r.status;
    throw err;
  }
  return body;
}

/** useApi("/overview") -> { data, error, loading, reload } */
export function useApi(path) {
  const [state, setState] = useState({ loading: true });
  const load = useCallback(() => {
    if (!path) { setState({ loading: false }); return; }
    setState((s) => ({ ...s, loading: true, error: null }));
    api(path).then((data) => setState({ data, loading: false })).catch((error) => setState({ error, loading: false }));
  }, [path]);
  useEffect(() => { load(); }, [load]);
  return { ...state, reload: load };
}
