---
source: Performance results update
source_date: 2026-09-09
ingested: 2026-09-09
---

# NeoAgent V2 Benchmark Package

Mike Chen approved this comparison for the Exec Review:

| Measure | NeoAgent V1 | NeoAgent V2 | V2 change versus V1 |
| --- | --- | --- | --- |
| Task success | 80% (160/200) | 92% (184/200) | +12 percentage points |
| Median completion time, normalized | 100 | 70 | 30% lower |
| Model tokens per completed task, normalized | 100 | 75 | 25% fewer |

Both versions use the same underlying model, the same 200 internal document, email, and scheduling workflows, and the same execution environment. These are fictional internal demo figures, not measurements of a real product.

Task success means the expected end state was reached without an incorrect write. Completion time is compared on tasks completed by both versions. Token usage counts model input and output tokens, including retries, per completed task. Time and token indices set NeoAgent V1 to 100. The success change is 12 percentage points, not 12%.

Keep the NeoAgent V1 baseline, metric definitions, and internal evaluation scope with the figures. Approval covers leadership review only. Final external copy needs a separate Legal review. Slide 4 and dependent campaign copy still need updating.
