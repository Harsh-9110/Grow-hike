# k6 workload

Start the application in demo mode and use the commands in the root README. `k6.js` logs in once, warms one AAPL quote, then runs 20 users for 15 seconds, with a 0.2-second think time per iteration. Every iteration checks HTTP success and that `price` is a decimal string.

Success thresholds are targets: failure rate below 1%, quote p95 below 500 ms, over 100 successful quotes. `handleSummary` writes actual output to `load/results/summary.json`. The summarizer copies measured results into the root README. Teardown prints cache-hit deltas and provider-call counters.

This is a warm cached-read workload. It does not benchmark trade locking, upstream quota capacity, cold cache behavior or production infrastructure. The PostgreSQL race tests cover the competing-spend and same-key behaviors separately. For a release test, also run a cold-cache workload and a mixed multi-symbol workload within the upstream plan's real quota.

No load test was executed in the authoring environment, so there are no measured latency or throughput numbers in this archive.
