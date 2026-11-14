# Stage 1 pilot — Checkpoint 1 summary

Pilot design: 40 GSM8K test questions (sampled once, question_seed 20261112) × 2 seeds [0, 1] × 4 candidate models = 320 calls, temperature 0.7, top_p 1.0, max_tokens 512, fixed zero-shot CoT prompt ending in "Give the final answer after '####'.".

Run outcome: **320 / 320 rows** in `outputs/pilot_runs.jsonl` (12 pre-existing good rows resumed + 308 new calls), **0 error rows**, 0 failed calls, 320 unique run_ids. Runner summary: `{"attempted": 308, "written": 308, "failed": 0, "skipped_existing": 12}`.

Grading: project grader (`src/errorbars/grade.py`) via `src/errorbars/analyze.py:build_correctness` against GSM8K gold answers from `src/errorbars/data.py`. A response with no parseable number counts as a parse failure and grades incorrect.

Costs: pricing taken fresh from the Together models list (`together_api.py list-models`, 270 models, fetched 2026-11-12) — input/output $ per 1M tokens — combined with each model's mean prompt/completion tokens in the pilot. Actual pilot spend at these prices: **$0.0504** for 320 calls.

## Pilot table

| Model | n | Accuracy | Correct | Parse-fail rate | Mean prompt tok | Mean completion tok | finish: stop | finish: length | Cost / call | Projected main run (2,000 calls) | In 45–85% band? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| together/Tev1-4B-experimental | 80 | 0.0% | 0/80 | 97.5% (78/80) | 115.8 | 8.0 | 0 | 80 | $0.0000049 | $0.0097 | No — below band |
| Qwen/Qwen3.5-9B | 80 | 0.0% | 0/80 | 95.0% (76/80) | 113.8 | 512.0 | 0 | 80 | $0.000147 | $0.2947 | No — below band |
| deepseek-ai/DeepSeek-V4.1-Flash | 80 | 90.0% | 72/80 | 8.8% (7/80) | 128.2 | 211.0 | 72 | 8 | $0.000292 | $0.5834 | No — above band |
| MiniMaxAI/MiniMax-M3.1-Flash | 80 | 91.3% | 73/80 | 5.0% (4/80) | 275.3 | 241.2 | 73 | 7 | $0.000186 | $0.3720 | No — above band |

Pricing used (input / output, $ per 1M tokens):
- together/Tev1-4B-experimental: 0.041999999999999996 / 0 — **output price is listed as $0**, so the cost/call for this model is input-only and likely understates the real price.
- Qwen/Qwen3.5-9B: 0.17 / 0.25
- deepseek-ai/DeepSeek-V4.1-Flash: 0.3 / 1.2
- MiniMaxAI/MiniMax-M3.1-Flash: 0.15 / 0.6

## What the numbers mean

- **deepseek-ai/DeepSeek-V4.1-Flash — 90.0% (above band).** Clean behaviour: 90% stop, 10% length, 8.8% parse failures. GSM8K under this prompt is too easy for it; accuracy is at/near ceiling, which the spec excludes.
- **MiniMaxAI/MiniMax-M3.1-Flash — 91.3% (above band).** Clean behaviour: 91.3% stop, 8.8% length, 5.0% parse failures. Same ceiling problem.
- **Qwen/Qwen3.5-9B — 0.0% (below band, output failure, not difficulty).** 100% finish_reason=length, mean completion tokens exactly 512 on every call, 76/80 responses have empty text and the other 4 are cut off mid-solution; 95% parse failures, 0 correct. Under this endpoint/prompt setup it never returns a finished answer within the 512-token cap.
- **together/Tev1-4B-experimental — 0.0% (below band, output failure, not difficulty).** 100% finish_reason=length with exactly 8 completion tokens on every call; every response is a short opening fragment (e.g. "To solve this problem, we need to"); 97.5% parse failures, 0 correct.

## Band verdict and Checkpoint 1 decision needed

**0 of 4 models land in the 45–85% accuracy band** (two above at ~90–91%, two at 0% for output-truncation reasons). Fewer than three models in band means **no valid set of 3 models from 3 families can be proposed from this pilot**, so no model proposal is made here.

Per the spec's fallback for exactly this case, the item for Omid at Checkpoint 1 is a **harder public benchmark (e.g. a MATH-500 subset)** in place of / alongside GSM8K. That choice is Omid's — no new benchmark or replacement models have been selected. Note separately that a harder benchmark addresses the two ceiling models; the Qwen and Tev1 results are truncation/output problems at max_tokens 512, not difficulty problems, so their inclusion in any rerun is a separate decision.

## Projected main-run cost vs the $10 stop threshold

Main run = 400 questions × 5 seeds = 2,000 calls per model; 6,000 calls for 3 models.

- together/Tev1-4B-experimental: $0.0097 per 2,000 calls
- Qwen/Qwen3.5-9B: $0.2947 per 2,000 calls
- deepseek-ai/DeepSeek-V4.1-Flash: $0.5834 per 2,000 calls
- MiniMaxAI/MiniMax-M3.1-Flash: $0.3720 per 2,000 calls

Any 3-model combination projects to **$0.68–$1.25 total** (all four models together: $1.26 for 8,000 calls) — far below the $10 stop threshold in `config.yaml`. **Cost is not a blocker; the accuracy band is.**

Stopped at Checkpoint 1 as instructed: no PLAN.md written, no main run started.
