# Spend

All spend is Together AI serverless calls, costed on the basis frozen
in PLAN.md sec.4: pilot-time Together catalog prices × the tokens
logged for each call. Analysis compute (Stages 4–5) ran locally and
cost $0. There is no separate program cap for this project; the frozen
plan's guard was that the main run would not start if the projected
cost exceeded $10.

| step | calls | cost |
|---|---|---|
| pilot 1 (Stage 1: first model probe + pilot, 40 questions × 2 seeds) | — | $0.05 |
| pilot 2 (Stage 1: wider probe + pilot 2, same design) | 960 | $0.71 |
| main run (Stage 3: 400 questions × 5 seeds × 3 models) | 6,000 | $3.91 |
| **total** | | **$4.67** |

Pilot figures are the exact amounts recorded in PLAN.md sec.4
($0.0504 + $0.71 = $0.76); detail is in `results/pilot_summary.md` and
`results/pilot2_summary.md`. Main-run detail is in
`results/summary.md`.

Main run by model (2,000 calls each):

| model | prompt tokens | completion tokens | cost |
|---|---|---|---|
| Qwen-2-1.5B-Instruct (`arize-ai/qwen-2-1.5b-instruct`) | 232,099 | 415,126 | $0.06 |
| Muse-Glimmer-30B (`meta-models/Muse-Glimmer-30B`) | 299,291 | 813,999 | $1.33 |
| Inkling (`thinkingmachines/Inkling`) | 216,664 | 568,137 | $2.52 |

The main run came in at $3.91 against a $4.01 projection (PLAN.md
sec.4) and the $10 guard. Prices used, per 1M tokens (input, output):
Qwen-2-1.5B-Instruct ($0.10, $0.10); Muse-Glimmer-30B ($0.35, $1.50);
Inkling ($1.00, $4.05). The 5 failed calls (API timeouts, graded
incorrect per PLAN.md sec.6) returned no usage and are counted as $0.
