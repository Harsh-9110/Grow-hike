"""Insert measured results into the README only after a real k6 run."""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text())
metrics = summary['metrics']
values = metrics['http_req_duration{endpoint:quote}']['values']
requests = metrics['http_reqs']['values']['count']
failed = metrics['http_req_failed']['values']['rate']
checks = metrics['checks']['values']['rate']
result = '\n'.join([
    f"Measured at {datetime.now(timezone.utc).isoformat()} (20 VUs, 15s, warm AAPL cache, demo mode).",
    '', '| Metric | Measured result |', '| --- | ---: |',
    f'| HTTP requests (including setup/teardown) | {requests} |',
    f"| Quote p50 | {values['med']:.2f} ms |", f"| Quote p95 | {values['p(95)']:.2f} ms |",
    f'| Failed HTTP requests | {failed*100:.2f}% |', f'| Passed assertions | {checks*100:.2f}% |',
    '', 'This workload measures cached HTTP reads. It does not measure upstream provider throughput, order throughput, or public deployment capacity.',
])
readme = Path(__file__).resolve().parents[1]/'README.md'
text = readme.read_text()
start, end = '<!-- LOAD_RESULTS_START -->', '<!-- LOAD_RESULTS_END -->'
a,b = text.index(start)+len(start),text.index(end)
readme.write_text(text[:a]+'\n'+result+'\n'+text[b:])
print(result)
