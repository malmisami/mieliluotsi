/** Shared HTTP helpers (previously in loop/api.ts). Empty VITE_API_BASE = same origin (Vite proxy in dev, the backend in the single-port demo). */
export const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
    });
  } catch {
    throw new Error('Yhteys palvelimeen epäonnistui.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Pyyntö epäonnistui.');
  }
  return data as T;
}

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const put = <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) });
