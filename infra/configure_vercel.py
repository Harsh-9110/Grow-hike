"""Generate an exact same-origin API proxy after you know your real backend URL."""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

if len(sys.argv) != 2:
    raise SystemExit('Usage: python3 infra/configure_vercel.py https://your-actual-api-host')
url = sys.argv[1].rstrip('/')
p = urlparse(url)
if p.scheme != 'https' or not p.netloc or p.path or p.username or p.query:
    raise SystemExit('Provide an HTTPS origin without credentials, paths, or query parameters')
config = {
    'framework':'vite', 'buildCommand':'npm run build', 'outputDirectory':'dist',
    'rewrites':[{'source':'/api/:path*','destination':url+'/api/:path*'}, {'source':'/health','destination':url+'/health'}, {'source':'/ready','destination':url+'/ready'}, {'source':'/:path*','destination':'/index.html'}],
    'headers':[{'source':'/:path*','headers':[{'key':'X-Content-Type-Options','value':'nosniff'},{'key':'Referrer-Policy','value':'no-referrer'}]}],
}
target = Path(__file__).resolve().parents[1]/'frontend'/'vercel.json'
target.write_text(json.dumps(config,indent=2)+'\n')
print('Created frontend/vercel.json. Deploy the frontend folder in Vercel.')
