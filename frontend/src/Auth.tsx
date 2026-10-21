import { useState } from 'react';
import type { FormEvent } from 'react';
import { api, setToken } from './api';
import type { Config, User } from './types';
import { Icon, Notice } from './ui';
import { errorText } from './format';

export default function Auth({config, onLogin}: {config: Config; onLogin: (user: User) => void}) {
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function login(address: string, pass: string) {
    setBusy(true); setError('');
    try {
      const result = await api<{access_token: string; user: User}>(`/auth/${register ? 'register' : 'login'}`, {method:'POST', body:JSON.stringify({email:address,password:pass})});
      setToken(result.access_token); onLogin(result.user);
    } catch(e) {setError(errorText(e));} finally {setBusy(false);}
  }
  function submit(e: FormEvent) {e.preventDefault(); void login(email,password);}
  return <div className="auth-layout">
    <div className="auth-story"><div className="brand"><span className="brand-glyph"><Icon name="markets" size={26}/></span> GROW HIKE</div>
      <div><div className="eyebrow">A little perspective. A smarter next step.</div><h1>Find your footing.<br/><span>Then grow.</span></h1><p>One calm workspace to explore markets, build a virtual portfolio, and understand the numbers behind it.</p><div className="auth-chart"><svg viewBox="0 0 500 150" role="img" aria-label="Decorative illustration of an upward path, not market data"><defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#6ce5b1" stopOpacity=".25"/><stop offset="100%" stopColor="#6ce5b1" stopOpacity="0"/></linearGradient></defs><path d="M0 130 30 120 60 125 100 95 130 100 165 70 190 80 220 50 250 65 280 40 320 55 355 20 395 30 430 5 470 15 500 0V150H0Z" fill="url(#fill)"/><path d="M0 130 30 120 60 125 100 95 130 100 165 70 190 80 220 50 250 65 280 40 320 55 355 20 395 30 430 5 470 15 500 0" fill="none" stroke="#6ce5b1" strokeWidth="2"/></svg></div></div>
      <div className="auth-foot">NSE · BSE · NASDAQ · NYSE <span>Always paper trading.</span></div>
    </div>
    <div className="auth-form-wrap"><form onSubmit={submit} className="auth-form"><span className="eyebrow">YOUR MARKET, IN PERSPECTIVE</span><h2>{register ? 'Make room to grow.' : 'Welcome to your workspace.'}</h2><p className="muted">{register ? 'Start with ₹10,00,000 in virtual cash.' : 'Sign in and pick up where you left off.'}</p>
      {error && <Notice error>{error}</Notice>}
      <label>Email<input required type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)}/></label>
      <label>Password<input required type="password" minLength={12} maxLength={72} autoComplete={register ? 'new-password' : 'current-password'} value={password} onChange={e=>setPassword(e.target.value)}/><small className="muted">12–72 characters; at most 72 UTF-8 bytes.</small></label>
      <button className="primary justify-between" disabled={busy}>{busy ? 'Please wait…' : register ? 'Create account' : 'Sign in'}<Icon name="arrow"/></button>
      {config.google_enabled && <a className="button secondary" href="/api/auth/google/start">Continue with Google</a>}
      <button type="button" className="text-button" disabled={busy} onClick={()=>{setRegister(!register);setError('');}}>{register ? 'Already have an account? Sign in' : 'New here? Create an account'}</button>
      {config.demo_mode && !register && <div className="demo-login"><span>Just looking around?</span><button type="button" className="secondary w-full" disabled={busy} onClick={()=>void login(config.demo_email ?? '', config.demo_password ?? '')}>Explore the seeded demo <Icon name="arrow"/></button><small className="muted">Synthetic prices. Virtual funds. No broker account needed.</small></div>}
    </form></div>
  </div>;
}
