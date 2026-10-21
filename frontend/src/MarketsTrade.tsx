import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import Decimal from 'decimal.js-light';
import { api, openStream } from './api';
import type { Entry, History, Portfolio, Quote, Stock } from './types';
import { Badge, Icon, Notice } from './ui';
import { errorText, money, number } from './format';

export default function MarketsTrade({portfolio, stocks, trade, onTraded}: {portfolio: Portfolio; stocks: Stock[]; trade: boolean; onTraded: () => void}) {
  const [search,setSearch]=useState('');
  const [symbol,setSymbol]=useState('RELIANCE.NS');
  const [q,setQ]=useState<Quote | null>(null);
  const [h,setH]=useState<History | null>(null);
  const [error,setError]=useState('');
  const [message,setMessage]=useState('');
  const [qty,setQty]=useState('1');
  const [side,setSide]=useState('BUY');
  const [busy,setBusy]=useState(false);
  const [streaming,setStreaming]=useState(false);
  const [entries,setEntries]=useState<Entry[]>([]);
  const orderKey=useRef('');
  const submitLock=useRef(false);
  const selected=stocks.find(s=>s.symbol===symbol);
  useEffect(()=>{let active=true;setQ(null);setH(null);setError('');void Promise.all([api<Quote>(`/stocks/${encodeURIComponent(symbol)}/quote`),api<History>(`/stocks/${encodeURIComponent(symbol)}/history`)]).then(([quote,history])=>{if(active){setQ(quote);setH(history);}}).catch(e=>{if(active)setError(errorText(e));});return()=>{active=false;};},[symbol]);
  useEffect(()=>{let active=true;void api<Entry[]>(`/portfolios/${portfolio.id}/ledger`).then(e=>{if(active)setEntries(e);}).catch(e=>{if(active)setError(errorText(e));});return()=>{active=false;};},[portfolio.id,message]);
  useEffect(()=>{
    if(!streaming)return;
    const controller=new AbortController();
    let retryTimer: ReturnType<typeof setTimeout>;
    async function connect(){
      try{await openStream([symbol],data=>{const quotes=data as Quote[];if(quotes[0])setQ(quotes[0]);},controller.signal);}catch(e){if(!controller.signal.aborted)setError(errorText(e));}
      if(!controller.signal.aborted)retryTimer=setTimeout(()=>{void connect();},65000);
    }
    void connect();
    return()=>{controller.abort();clearTimeout(retryTimer);};
  },[streaming,symbol]);
  function changeOrder(){orderKey.current='';setMessage('');}
  async function submit(e: FormEvent){
    e.preventDefault();if(submitLock.current)return;submitLock.current=true;setBusy(true);setError('');setMessage('');
    orderKey.current ||= crypto.randomUUID();
    try{
      const result=await api<{replayed:boolean}>(`/portfolios/${portfolio.id}/orders`,{method:'POST',headers:{'Idempotency-Key':orderKey.current},body:JSON.stringify({symbol,side,quantity:qty})});
      setMessage(result.replayed?'Your earlier order was already recorded. No duplicate trade was made.':'Paper trade recorded in your immutable ledger.');
      onTraded(); // Keep the key until the user changes the order. A second click safely replays it.
    }catch(err){setError(errorText(err));}finally{setBusy(false);submitLock.current=false;}
  }
  async function watch(){try{await api('/watchlist',{method:'POST',body:JSON.stringify({symbol})});setMessage('Added to your watchlist.');}catch(e){setError(errorText(e));}}
  const filtered=stocks.filter(s=>`${s.name} ${s.symbol} ${s.market}`.toLowerCase().includes(search.toLowerCase()));
  return <><div className="market-layout"><div className="panel stock-picker"><label className="search-label"><Icon name="search"/><input aria-label="Find a supported stock" placeholder="Find a stock…" value={search} onChange={e=>setSearch(e.target.value)}/></label><p className="caption px-4">Supported catalogue · {stocks.length} stocks</p><div className="stock-list">{filtered.map(s=><button key={s.symbol} className={s.symbol===symbol?'selected':''} onClick={()=>{setSymbol(s.symbol);changeOrder();}}><span className="ticker-avatar">{s.symbol.slice(0,2)}</span><span><strong>{s.symbol}</strong><small>{s.name}</small></span><span className="stock-market">{s.market}</span></button>)}{!filtered.length&&<p className="empty">No match in the supported catalogue.</p>}</div></div>
    <div className="space-y-5">{error&&<Notice error>{error}</Notice>}{message&&<Notice>{message}</Notice>}<div className="panel stock-detail"><div className="section-title"><div><span className="eyebrow">{selected?.market} · {selected?.sector}</span><h2 className="stock-name">{selected?.name ?? symbol}</h2></div><button className="secondary" onClick={()=>void watch()}><Icon name="watchlist"/>Watch</button></div>{q?<><div className="quote-price">{money(q.price,q.currency)}<Badge>{q.stale?'Stale':q.demo?'Demo price':q.provider}</Badge></div><div className="muted text-sm">As of {new Date(q.as_of).toLocaleString()} · {q.currency}</div></>:<p className="muted">Loading price…</p>}
      {h&&<><div className="chart stock-chart"><ResponsiveContainer><AreaChart data={h.points.map(p=>({...p,close:Number(p.close)}))}><defs><linearGradient id="stockFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#64d9ac" stopOpacity={.2}/><stop offset="100%" stopColor="#64d9ac" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} stroke="var(--border)"/><XAxis dataKey="date" minTickGap={60} tick={{fill:'var(--muted)',fontSize:11}}/><YAxis domain={['auto','auto']} tick={{fill:'var(--muted)',fontSize:11}} width={55}/><Tooltip formatter={v=>money(String(v),selected?.currency)} contentStyle={{background:'var(--panel)',border:'1px solid var(--border)'}}/><Area dataKey="close" type="monotone" stroke="#64d9ac" fill="url(#stockFill)" dot={false}/></AreaChart></ResponsiveContainer></div><p className="caption">{h.demo?'Synthetic demo series.':'Daily unadjusted closing prices.'} {h.stale?'History is stale.':''}</p></>}
      <label className="toggle-row"><input type="checkbox" checked={streaming} onChange={e=>setStreaming(e.target.checked)}/>Live cached updates <small className="muted">SSE · about every 60 seconds</small></label>
    </div>
    {trade&&<form className="panel order-form" onSubmit={e=>void submit(e)}><div className="section-title"><h2>Make a paper trade</h2><Badge>Virtual funds only</Badge></div>{portfolio.kind==='import'?<Notice>Imported portfolios are read-only. Select your paper portfolio to trade.</Notice>:<><div className="order-controls"><label>Side<select value={side} onChange={e=>{setSide(e.target.value);changeOrder();}}><option value="BUY">Buy</option><option value="SELL">Sell · FIFO</option></select></label><label>Quantity<input required inputMode="decimal" pattern="[0-9]+([.][0-9]{1,8})?" value={qty} onChange={e=>{setQty(e.target.value);changeOrder();}}/></label><div><small className="muted">Indicative native value</small><strong>{q&&/^\d+(\.\d+)?$/.test(qty)?money(new Decimal(qty).mul(q.price).toString(),q.currency):'—'}</strong></div><button className="primary" disabled={busy||!q||q.stale}>{busy?'Recording…':`${side==='BUY'?'Buy':'Sell'} ${symbol}`}</button></div><p className="caption">Orders use the server's cached price and FX at execution. No fees, shorting, leverage or real broker orders. Change the quantity or side to start a new order.</p></>}</form>}
    </div></div>{trade&&<div className="panel"><div className="section-title"><h2>Transaction ledger</h2><Badge>Append only</Badge></div><div className="table-scroll"><table><thead><tr><th># / Date</th><th>Action</th><th>Symbol</th><th>Quantity</th><th>Native price</th><th>Cash movement · INR</th></tr></thead><tbody>{[...entries].reverse().map(e=><tr key={e.id}><td>{e.sequence}<small>{new Date(e.created_at).toLocaleDateString()}</small></td><td><Badge>{e.kind}</Badge></td><td>{e.symbol??'Virtual funds'}</td><td>{number(e.quantity,8)}</td><td>{money(e.price,stocks.find(s=>s.symbol===e.symbol)?.currency??'INR')}</td><td>{money(e.cash_delta_inr)}</td></tr>)}</tbody></table></div></div>}</>;
}
