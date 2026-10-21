# Demonstration and screenshot capture

No browser images or video were captured in the authoring environment. To create real evidence, start the local stack, then run the README browser commands. The script captures the actual application, checks console/page/API failures, and records a WebM video. Review it before sharing.

Suggested 90–120-second narrated walkthrough:

1. Enter the seeded demo and explain synthetic prices and virtual money.
2. Show INR portfolio value, native/INR holdings, FIFO realized/unrealized P&L and allocation dimensions.
3. Toggle benchmark view, explain the daily observation time and show available risk metrics.
4. Open Markets and the supported catalogue. Enable the SSE toggle.
5. Buy one share, retry the unchanged order, and point to the single ledger fill and replay message.
6. Upload the sample CSV, review the preview, confirm, and show the new read-only portfolio.
7. Show the AI source fallback and untrained-model state; explain how a trained model would be evaluated against the naive baseline.
8. Calculate the manual IPO/GMP scenario and finish on shared cache/provider metrics.

For a portfolio presentation, show an actual passing PostgreSQL concurrency test and k6 report alongside the demo. A UI recording alone cannot prove transactional safety or model accuracy.
