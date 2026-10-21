import type { User } from './types';

let accessToken = '';
let accessExpiry = 0;
let refreshFlight: Promise<User | null> | null = null;
export const csrf = () => document.cookie.split('; ').find(s => s.startsWith('gh_csrf='))?.split('=')[1] ?? '';
export const setToken = (token: string) => {
  accessToken = token;
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const payload: {exp: number} = JSON.parse(atob(part.padEnd(Math.ceil(part.length / 4) * 4, '=')));
    accessExpiry = payload.exp * 1000;
  } catch { accessExpiry = 0; }
};
export class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }

async function responseError(response: Response): Promise<ApiError> {
  const data: { detail?: string | {msg: string}[] } = await response.json().catch(() => ({}));
  const message = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(x => x.msg).join('; ') : 'Request failed. Please try again.';
  return new ApiError(response.status, message);
}

export async function refresh(): Promise<User | null> {
  if (!csrf()) return null;
  if (refreshFlight) return refreshFlight;
  const rotate = async (): Promise<User | null> => {
    const response = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include', headers: {'X-CSRF-Token': csrf()} });
    if (!response.ok) { setToken(''); return null; }
    const body: {access_token: string; user: User} = await response.json();
    setToken(body.access_token);
    return body.user;
  };
  // Serialize refreshes across browser tabs where Web Locks are supported.
  const crossTabRotate = async (): Promise<User | null> => await navigator.locks.request('gh-refresh', rotate);
  refreshFlight = (navigator.locks ? crossTabRotate() : rotate()).finally(() => { refreshFlight = null; });
  return refreshFlight;
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  if (accessToken && accessExpiry < Date.now() + 30000 && !path.startsWith('/auth/')) await refresh();
  const headers = new Headers(options.headers);
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'include' });
  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    const user = await refresh();
    if (user) return api<T>(path, options, false);
    window.dispatchEvent(new Event('gh:session-ended'));
  }
  if (!response.ok) throw await responseError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function openStream(symbols: string[], onQuotes: (data: unknown) => void, signal: AbortSignal): Promise<void> {
  if (accessToken && accessExpiry < Date.now() + 30000) await refresh();
  let response = await fetch(`/api/stream?symbols=${encodeURIComponent(symbols.join(','))}`, {headers: {Authorization: `Bearer ${accessToken}`}, credentials: 'include', signal});
  if (response.status === 401 && await refresh()) {
    response = await fetch(`/api/stream?symbols=${encodeURIComponent(symbols.join(','))}`, {headers: {Authorization: `Bearer ${accessToken}`}, credentials: 'include', signal});
  }
  if (!response.ok || !response.body) throw await responseError(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (!signal.aborted) {
    const {done, value} = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, {stream: true});
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const event = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (event.startsWith('event: quotes')) {
        const line = event.split('\n').find(l => l.startsWith('data: '));
        if (line) onQuotes(JSON.parse(line.slice(6)) as unknown);
      }
      if (event.startsWith('event: expired')) return;
      boundary = buffer.indexOf('\n\n');
    }
  }
}
