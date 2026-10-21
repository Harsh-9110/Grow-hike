import { lazy, Suspense, useEffect, useState } from 'react';
import { api, csrf, refresh, setToken } from './api';
import Auth from './Auth';
const Overview = lazy(() => import('./Overview'));
const MarketsTrade = lazy(() => import('./MarketsTrade'));
const AIPage = lazy(() => import('./Tools').then(m => ({default: m.AIPage})));
const ImportPage = lazy(() => import('./Tools').then(m => ({default: m.ImportPage})));
const IPOPage = lazy(() => import('./Tools').then(m => ({default: m.IPOPage})));
const MetricsPage = lazy(() => import('./Tools').then(m => ({default: m.MetricsPage})));
const WatchlistPage = lazy(() => import('./Tools').then(m => ({default: m.WatchlistPage})));
import type { Config, Portfolio, Stock, User } from './types';
import { Badge, Icon, Notice } from './ui';
import { errorText } from './format';

const pages = [
  {id:'overview',label:'Overview',description:'The bigger picture, at a glance.'},
  {id:'markets',label:'Markets',description:'Explore a world of possibilities.'},
  {id:'trade',label:'Paper trading',description:'Build conviction. Practice with virtual funds.'},
  {id:'watchlist',label:'Watchlist & alerts',description:'Keep the right signals in sight.'},
  {id:'import',label:'Import portfolio',description:'Bring your holdings into perspective.'},
  {id:'ai',label:'AI lab',description:'Evidence, experiments, and honest limitations.'},
  {id:'ipo',label:'IPO & GMP',description:'Explore the numbers before the listing.'},
  {id:'metrics',label:'System metrics',description:'A transparent view of the engineering.'},
];
export default function App() {
  const [user,setUser]=useState<User | null>(null);
  const [config,setConfig]=useState<Config | null>(null);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [portfolios,setPortfolios]=useState<Portfolio[]>([]);
  const [selected,setSelected]=useState('');
  const [stocks,setStocks]=useState<Stock[]>([]);
  const [version,setVersion]=useState(0);
  const [page,setPage]=useState(new URLSearchParams(window.location.search).get('page')??'overview');
  const [dark,setDark]=useState(localStorage.getItem('gh_theme')!=='light');
  useEffect(()=>{document.documentElement.dataset.theme=dark?'dark':'light';localStorage.setItem('gh_theme',dark?'dark':'light');},[dark]);
  useEffect(()=>{let active=true;void Promise.all([api<Config>('/config'),refresh()]).then(([c,u])=>{if(active){setConfig(c);setUser(u);}}).catch(e=>{if(active)setError(errorText(e));}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[]);
  useEffect(()=>{function end(){setUser(null);setPortfolios([]);setSelected('');setToken('');setError('Your session ended. Please sign in again.');}window.addEventListener('gh:session-ended',end);return()=>window.removeEventListener('gh:session-ended',end);},[]);
  useEffect(()=>{if(!user)return;let active=true;void Promise.all([api<Portfolio[]>('/portfolios'),api<Stock[]>('/stocks')]).then(([p,s])=>{if(active){setPortfolios(p);setStocks(s);setSelected(old=>p.some(item=>item.id===old)?old:p[0]?.id??'');}}).catch(e=>{if(active)setError(errorText(e));});return()=>{active=false;};},[user,version]);
  async function logout(){try{await api('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf()}});setUser(null);setSelected('');setPortfolios([]);setToken('');}catch(e){setError(errorText(e));}}
  function navigate(id:string){setPage(id);window.history.replaceState({},'',`/?page=${id}`);}
  function imported(id:string){setSelected(id);setVersion(v=>v+1);navigate('overview');}
  if(loading)return <div className="startup"><span className="brand-glyph"><Icon name="markets" size={32}/></span><p>Opening your workspace…</p></div>;
  if(!config)return <div className="startup"><Notice error>{error||'Backend unavailable. Start the application services, then reload.'}</Notice><button className="secondary" onClick={()=>window.location.reload()}>Reload</button></div>;
  if(!user)return <>{error&&<div className="auth-error"><Notice error>{error}</Notice></div>}<Auth config={config} onLogin={u=>{setUser(u);setError('');}}/></>;
  const current=pages.find(p=>p.id===page)??pages[0];
  const portfolio=portfolios.find(p=>p.id===selected);
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-glyph"><Icon name="markets" size={23}/></span><span>GROW HIKE<span className="brand-sub">A little higher, every day.</span></span></div><div className="nav-label">WORKSPACE</div><nav aria-label="Main navigation">{pages.map(p=><button key={p.id} className={current.id===p.id?'active':''} aria-current={current.id===p.id?'page':undefined} onClick={()=>navigate(p.id)}><Icon name={p.id}/><span>{p.label}</span>{current.id===p.id&&<span className="nav-dot"/>}</button>)}</nav><div className="sidebar-bottom"><div className="practice-card"><span className="live-dot"/> A space to practice<p>Virtual capital.<br/>Real curiosity.</p></div><div className="user-row"><span className="avatar">{user.email.slice(0,1).toUpperCase()}</span><span><strong>{config.demo_mode&&user.email===config.demo_email?'Demo explorer':'Your workspace'}</strong><small title={user.email}>{user.email}</small></span><button aria-label="Sign out" className="icon-button" onClick={()=>void logout()}><Icon name="logout" size={17}/></button></div></div></aside><div className="main-wrap"><header className="topbar"><span className="breadcrumb">Workspace <span>/</span> {current.label}</span><div className="flex items-center gap-4"><span className="market-status"><span className="live-dot"/>{config.demo_mode?'Demo market data':'Provider market data'}</span><button className="icon-button" aria-label={`Switch to ${dark?'light':'dark'} mode`} onClick={()=>setDark(!dark)}><Icon name={dark?'sun':'moon'}/></button><button className="icon-button md:hidden" aria-label="Sign out" onClick={()=>void logout()}><Icon name="logout"/></button></div></header><main><div className="page-heading"><div><span className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</span><h1>{current.label==='Overview'?'Room to grow.':current.label}</h1><p>{current.description}</p></div><label className="portfolio-select">Portfolio<select value={selected} onChange={e=>setSelected(e.target.value)}>{portfolios.map(p=><option key={p.id} value={p.id}>{p.name} {p.kind==='import'?'· read-only':''}</option>)}</select></label></div>{config.demo_mode&&<div className="demo-banner"><Badge>DEMO</Badge><span>Synthetic prices and illustrative history. Every trade uses virtual money.</span></div>}{error&&<Notice error>{error}</Notice>}
    {portfolio?<Suspense fallback={<div className="panel loading">Opening page…</div>}>
      {current.id==='overview'&&<Overview key={selected} id={selected} version={version} goTrade={()=>navigate('trade')}/>}
      {(current.id==='markets'||current.id==='trade')&&<MarketsTrade key={current.id+selected} portfolio={portfolio} stocks={stocks} trade={current.id==='trade'} onTraded={()=>setVersion(v=>v+1)}/>}
      {current.id==='watchlist'&&<WatchlistPage stocks={stocks}/>}
      {current.id==='import'&&<ImportPage config={config} onImported={imported}/>}
      {current.id==='ai'&&<AIPage stocks={stocks}/>}
      {current.id==='ipo'&&<IPOPage/>}
      {current.id==='metrics'&&<MetricsPage/>}
    </Suspense>:<div className="panel loading">Loading portfolios…</div>}
    <footer><span>GROW HIKE <span className="muted">· Learn with perspective.</span></span><span>Paper trading only · Not financial advice</span></footer></main></div></div>;
}
