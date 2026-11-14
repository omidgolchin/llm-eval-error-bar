# Stage 1, round 2 — probe + pilot 2 summary (revised Checkpoint 1)

Omid's Checkpoint 1 choice: probe more serverless models on GSM8K before considering a harder benchmark.

## Phase 1 — catalog probe (2026-11-12)

Fresh model list fetched (`together_api.py list-models`, 270 models). Every chat/language model not already known to work was probed with one short call ("What is 2+2? Give the final answer after '####'.", max_tokens 64, temperature 0.7, seed 0), sequentially, via the runner's client machinery. Full per-model results: `results/probe2_results.json` (script: `results/probe2.py`). No 429 / rate-limit response was hit.

- **Probed: 186** models (chat + language types, excluding the 5 already known to work)
- **Works: 16**
- **Non-serverless (HTTP 400 "Unable to access non-serverless model"): 158**
- **Other errors: 12**, in two classes:
  - Dedicated endpoint not running / no deployments ready (8): `google/gemma-2-9b-it`, `agentica-org/DeepCoder-14B-Preview`, `mistralai/Devstral-Small-2505`, `mistralai/Mixtral-8x22B-Instruct-v0.1`, `MiniMaxAI/MiniMax-M1-40k`, `MiniMaxAI/MiniMax-M1-80k`, `sarvamai/sarvam-m`, `moonshotai/Kimi-K2.6`
  - HTTP 403, third-party data sharing not enabled on the account (4, all Qwen-hosted): `Qwen/Qwen3.8-Flash`, `Qwen/Qwen3.7-Max`, `Qwen/Qwen3.6-Plus`, `Qwen/Qwen3.7-Plus`. These might work if that account setting were enabled — that is Omid's setting to change, not something done here.

**The legacy small models were re-probed under the new key and are all still non-serverless** — Llama-3.2-1B/3B (instruct and base), Meta-Llama-3.1-8B-Instruct-Turbo, Llama-3-8b-chat-hf, Meta-Llama-3.1-8B, Qwen2.5-7B (Turbo / instruct / base), Mistral-7B-Instruct v0.1/v0.3 and Mistral-7B v0.1, Qwen2-1.5B (instruct/base), Qwen2.5-1.5B/3B-Instruct, all Gemma variants (gemma-2-27b-it is non-serverless; gemma-2-9b-it is in the endpoint-not-running class; gemma-3/4 all non-serverless). Access did not change with the new key.

### The 16 newly working models

`deepseek-ai/DeepSeek-V4.1-Flash-1017`, `moonshotai/Kimi-K3.1-Pro`, `meta-models/Muse-Spark-Open-816B-A42B`, `zai-org/GLM-5.3`, `zai-org/GLM-5.3-Flash`, `reflection/Beam-1.0-501B-A23B`, `nvidia/NVIDIA-Nemotron-3.5-Super-VL`, `zai-org/GLM-5.2`, `ricursive-ai/Ripple-65B-Preview`, `deepseek-ai/DeepSeek-V4-Pro-0813`, `meta-models/Muse-Glimmer-30B`, `thinkingmachines/Inkling`, `openai/gpt-oss-120b`, `arize-ai/qwen-2-1.5b-instruct`, `Prism-ML/Ternary-Bonsai-27B`, `elorian-labs/glimpse-1.0`.

Probe-output flag: 9 of the 16 returned **empty text** at the 64-token probe cap with finish_reason "length" (reasoning-style models whose visible answer had not started yet) — flagged in `probe2_results.json`. At the pilot's 512-token cap most of them produced normal text (see pilot table); one, Ternary-Bonsai-27B, stayed empty (see below).

## Phase 2 — pilot 2 design and selection

Pilot set = the 16 newly working models + `moonshotai/Kimi-K3` (known working, not in pilot 1) = 17. That exceeds the 12-model cap, so the set was prioritised: parameter size in the name ≤ ~32B first, then non-frontier / distinct-family releases, dropping near-duplicates of models already characterised.

**Piloted (12, all distinct families):** `arize-ai/qwen-2-1.5b-instruct` (1.5B), `Prism-ML/Ternary-Bonsai-27B` (27B), `meta-models/Muse-Glimmer-30B` (30B), `ricursive-ai/Ripple-65B-Preview` (65B), `openai/gpt-oss-120b` (120B), `reflection/Beam-1.0-501B-A23B`, `elorian-labs/glimpse-1.0`, `thinkingmachines/Inkling`, `nvidia/NVIDIA-Nemotron-3.5-Super-VL`, `zai-org/GLM-5.3-Flash`, `deepseek-ai/DeepSeek-V4-Pro-0813`, `moonshotai/Kimi-K3`.

**Working but not piloted (5):** `deepseek-ai/DeepSeek-V4.1-Flash-1017` (near-duplicate of pilot 1's DeepSeek-V4.1-Flash), `moonshotai/Kimi-K3.1-Pro` (newer variant of Kimi-K3), `zai-org/GLM-5.2` and `zai-org/GLM-5.3` (same family as the piloted GLM-5.3-Flash; the Flash tier was kept as likelier to land in band), `meta-models/Muse-Spark-Open-816B-A42B` (816B flagship of the family whose 30B model was piloted).

Design identical to pilot 1: 40 GSM8K test questions (question_seed 20261112) × 2 seeds [0, 1] × 12 models = **960 calls**, temperature 0.7, top_p 1.0, max_tokens 512, same fixed prompt. Output: `outputs/pilot2_runs.jsonl` (pilot 1's `outputs/pilot_runs.jsonl` untouched, still 320 rows). Run outcome: **960 / 960 rows, 0 error rows, 0 failed calls.** Actual pilot-2 spend at catalog prices: **$0.71**.

Grading: project grader (`src/errorbars/grade.py`) via `src/errorbars/analyze.py:build_correctness` against GSM8K gold answers. Costs: fresh list-models pricing × each model's mean prompt/completion tokens. Raw computed table: `results/pilot2_table.json` (script: `results/analyze_pilot2.py`).

## Pilot 2 table

| Model | n | Accuracy | Correct | Parse-fail rate | Mean prompt tok | Mean completion tok | finish: stop | finish: length | Cost / call | Projected main run (2,000 calls) | In 45–85% band? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| moonshotai/Kimi-K3 | 80 | 96.3% | 77/80 | 2.5% (2/80) | 183.0 | 219.8 | 78 | 2 | $0.003846 | $7.69 | No — above band |
| zai-org/GLM-5.3-Flash | 80 | 95.0% | 76/80 | 2.5% (2/80) | 111.6 | 213.4 | 77 | 3 | $0.000123 | $0.25 | No — above band |
| deepseek-ai/DeepSeek-V4-Pro-0813 | 80 | 90.0% | 72/80 | 8.8% (7/80) | 102.2 | 229.3 | 72 | 8 | $0.001043 | $2.09 | No — above band |
| openai/gpt-oss-120b | 80 | 90.0% | 72/80 | 2.5% (2/80) | 166.7 | 297.6 | 73 | 7 | $0.000204 | $0.41 | No — above band |
| elorian-labs/glimpse-1.0 | 80 | 88.7% | 71/80 | 7.5% (6/80) | 155.8 | 275.7 | 71 | 9 | $0.000920 | $1.84 | No — above band |
| reflection/Beam-1.0-501B-A23B | 80 | 86.3% | 69/80 | 11.3% (9/80) | 148.1 | 241.3 | 71 | 9 | $0.000349 | $0.70 | No — above band |
| ricursive-ai/Ripple-65B-Preview | 80 | 86.3% | 69/80 | 8.8% (7/80) | 107.6 | 260.7 | 69 | 11 | $0.000178 | $0.36 | No — above band |
| thinkingmachines/Inkling | 80 | 78.8% | 63/80 | 7.5% (6/80) | 112.7 | 293.8 | 64 | 16 | $0.001303 | $2.61 | **Yes** |
| meta-models/Muse-Glimmer-30B | 80 | 71.3% | 57/80 | 26.2% (21/80) | 154.2 | 408.1 | 56 | 24 | $0.000666 | $1.33 | **Yes** |
| nvidia/NVIDIA-Nemotron-3.5-Super-VL | 80 | 55.0% | 44/80 | 33.8% (27/80) | 119.2 | 399.9 | 43 | 37 | $0.000218 | $0.44 | **Yes** |
| arize-ai/qwen-2-1.5b-instruct | 80 | 52.5% | 42/80 | 0.0% (0/80) | 121.0 | 206.1 | 80 | 0 | $0.000033 | $0.07 | **Yes** |
| Prism-ML/Ternary-Bonsai-27B | 80 | 0.0% | 0/80 | 98.8% (79/80) | 113.8 | 512.0 | 0 | 80 | $0.000000 | $0.00 | No — below band |

Pricing used (input / output, $ per 1M tokens): Kimi-K3 3.0/15.0; GLM-5.3-Flash 0.15/0.5; DeepSeek-V4-Pro-0813 1.32/3.96; gpt-oss-120b 0.15/0.6; glimpse-1.0 0.6/3.0; Beam-1.0 0.4/1.2; Ripple-65B 0.2/0.6; Inkling 1.0/4.05; Muse-Glimmer-30B 0.35/1.5; Nemotron-3.5-Super-VL 0.15/0.5; qwen-2-1.5b-instruct 0.1/0.1; Ternary-Bonsai-27B 0/0 — **both prices listed as $0 in the catalog**, so its cost figures are $0 by construction and almost certainly not the real billing price.

## What the numbers mean

- **Four models land in the 45–85% band, from four different families** — the thing pilot 1 could not produce:
  - **arize-ai/qwen-2-1.5b-instruct — 52.5%.** The cleanest behaviour in either pilot: 100% finish "stop", **0% parse failures**, every answer surfaced. A genuine small model (1.5B) doing GSM8K at a coin-flip-plus level — exactly the size class the spec aimed for.
  - **thinkingmachines/Inkling — 78.8%.** Clean-ish: 80% stop, 7.5% parse failures. Top of the in-band range, useful spread against the 1.5B model.
  - **meta-models/Muse-Glimmer-30B — 71.3%.** In band, but with caveats: 26.2% parse failures, 30% length finishes, 21/80 empty texts. Part of its "difficulty" is output behaviour, not reasoning.
  - **nvidia/NVIDIA-Nemotron-3.5-Super-VL — 55.0%.** In band, with stronger caveats: 33.8% parse failures, 46% length finishes, 27/80 empty texts. Its accuracy is substantially a truncation story (it is also a vision-language model being run text-only).
- **Seven models above band (86.3–96.3%)**, all behaving cleanly — GSM8K is simply too easy for current frontier/serverless models, Kimi-K3 included (96.3%, and by far the most expensive: $7.69 per 2,000-call main run on its own).
- **Prism-ML/Ternary-Bonsai-27B — 0.0%, an output failure, not difficulty.** Identical signature to pilot 1's Qwen3.5-9B: 100% finish "length" at exactly 512 completion tokens, 79/80 empty texts, 98.8% parse failures.

## Revised Checkpoint 1 proposal

Across pilots 1 + 2 there are now **4 in-band models from 4 families**, so a valid 3-model set exists on GSM8K — no benchmark switch is required to satisfy the band.

**Proposed main-run set (3 models, 3 families):**

1. **arize-ai/qwen-2-1.5b-instruct** — 52.5%, 0% parse-fail, projected main run $0.07
2. **thinkingmachines/Inkling** — 78.8%, 7.5% parse-fail, projected main run $2.61
3. **meta-models/Muse-Glimmer-30B** — 71.3%, 26.2% parse-fail, projected main run $1.33

Projected total for the 6,000-call main run: **≈ $4.01** — under the $10 stop threshold in `config.yaml`.

**Alternate:** swap Muse-Glimmer-30B for **nvidia/NVIDIA-Nemotron-3.5-Super-VL** (55.0%, projected $0.44, total ≈ $3.12) if a lower-accuracy third model is preferred — but its parse-failure rate (33.8%) is worse than Glimmer's (26.2%), and both models' in-band status partly reflects truncated/empty outputs rather than question difficulty. Omid should know that whichever of the two is chosen, one leg of the study will have a large parse-failure component, which the analysis already reports separately.

Stopped at revised Checkpoint 1 as instructed: no PLAN.md written, no main run started.
