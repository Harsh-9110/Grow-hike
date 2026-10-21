import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

const successes = new Counter('quote_successes');
const BASE = __ENV.BASE_URL || 'http://backend:8000';
export const options = {
  vus: 20,
  duration: '15s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{endpoint:quote}': ['p(95)<500'],
    quote_successes: ['count>100'],
  },
};
export function setup() {
  const login = http.post(`${BASE}/api/auth/login`, JSON.stringify({email: __ENV.DEMO_EMAIL || 'demo@growhike.dev', password: __ENV.DEMO_PASSWORD || 'GrowHike-Demo-2026!'}), {headers:{'Content-Type':'application/json'}});
  if(login.status !== 200) throw new Error('Use a development demo instance with valid load-test credentials');
  const headers = {Authorization:`Bearer ${login.json('access_token')}`};
  const warm = http.get(`${BASE}/api/stocks/AAPL/quote`,{headers});
  if(warm.status !== 200) throw new Error('Warm-up quote failed');
  const before = http.get(`${BASE}/api/metrics`,{headers}).json();
  return {headers,before};
}
export default function(data) {
  const response = http.get(`${BASE}/api/stocks/AAPL/quote`,{headers:data.headers,tags:{endpoint:'quote'}});
  const ok = check(response,{'quote succeeds':r=>r.status===200,'price is a decimal string':r=>r.status===200 && typeof r.json('price')==='string'});
  if(ok)successes.add(1);
  sleep(0.2);
}
export function teardown(data) {
  const after = http.get(`${BASE}/api/metrics`,{headers:data.headers}).json();
  console.log(JSON.stringify({cache_hits_delta:(after.counters.cache_hits||0)-(data.before.counters.cache_hits||0),provider_calls_after:Object.fromEntries(Object.entries(after.counters).filter(([k])=>k.startsWith('provider_calls:')))}));
}
export function handleSummary(data) {
  return {'/results/summary.json':JSON.stringify(data,null,2),stdout:JSON.stringify({status:'completed',http_requests:data.metrics.http_reqs?.values?.count,quote_duration:data.metrics['http_req_duration{endpoint:quote}']?.values},null,2)+'\n'};
}
