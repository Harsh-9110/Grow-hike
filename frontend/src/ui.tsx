import type { ReactNode } from 'react';

export function Icon({name, size = 20}: {name: string; size?: number}) {
  const paths: Record<string, ReactNode> = {
    overview: <><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>,
    markets: <><path d="M3 20h18M5 16l4-6 4 3 6-9"/><path d="M14 4h5v5"/></>,
    trade: <><path d="M4 7h16l-4-4M20 17H4l4 4"/></>,
    watchlist: <path d="m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z"/>,
    import: <><path d="M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6"/></>,
    ai: <><path d="m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3zM20 3v4m-2-2h4"/></>,
    ipo: <><path d="M12 21V3m-7 7 7-7 7 7M4 21h16"/></>,
    metrics: <><path d="M3 12h4l3-8 4 16 3-8h4"/></>,
    sun: <><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/></>,
    moon: <path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10z"/>,
    logout: <><path d="M9 3H3v18h6m4-15 6 6-6 6m-6-6h12"/></>,
    arrow: <><path d="M5 12h14m-5-5 5 5-5 5"/></>,
    search: <><circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/></>,
    check: <path d="m4 12 5 5L20 6"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.markets}</svg>;
}
export function Notice({children, error = false}: {children: ReactNode; error?: boolean}) { return <div className={`notice ${error ? 'error' : ''}`} role={error ? 'alert' : 'status'}>{children}</div>; }
export function Stat({label, value, detail, positive}: {label: string; value: string; detail?: string; positive?: boolean}) { return <div className="stat"><span className="muted text-xs uppercase tracking-widest">{label}</span><strong className={positive === undefined ? '' : positive ? 'positive' : 'negative'}>{value}</strong>{detail && <small className="muted">{detail}</small>}</div>; }
export function Badge({children}: {children: ReactNode}) {return <span className="badge">{children}</span>;}
