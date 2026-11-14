# Results summary — main run (Stage 4)

Question: when an LLM is evaluated on N questions x K repeated runs, which interval methods actually cover the true (reference) accuracy at their nominal 95% level, and how should a fixed budget be split between questions and seeds? Design, methods and decision rules are as frozen in PLAN.md. Coverage is measured against each model's full-pool reference accuracy (400 questions x 5 seeds); see PLAN.md sec.7 for the finite-pool caveat.

## Run validation and spend

- Rows in outputs/raw_runs.jsonl: 6000 (6,000 planned); unique run_ids, no duplicates, no dry-run rows; the question set is exactly the frozen 400-question pool; every model has 400 questions x 5 seeds with no missing cells.
- Failed calls (finish_reason = "error", all API timeouts, graded incorrect per PLAN.md sec.6): 5 total — Qwen-2-1.5B-Instruct: 2, Muse-Glimmer-30B: 1, Inkling: 2.
- Finish reasons overall: stop: 5027, length: 968, error: 5.

Model spend (pilot-time Together catalog prices x logged tokens, the basis of PLAN.md sec.4):

| model | calls | prompt tokens | completion tokens | cost |
|---|---|---|---|---|
| arize-ai/qwen-2-1.5b-instruct | 2000 | 232,099 | 415,126 | $0.06 |
| meta-models/Muse-Glimmer-30B | 2000 | 299,291 | 813,999 | $1.33 |
| thinkingmachines/Inkling | 2000 | 216,664 | 568,137 | $2.52 |
| **total main run** | | | | **$3.91** |

Main-run total $3.91 vs the $4.01 projection in PLAN.md sec.4 (guard: $10). Pilot spend, reported separately as required: pilot 1 $0.05 + pilot 2 $0.71 = $0.76.

## Qwen-2-1.5B-Instruct (`arize-ai/qwen-2-1.5b-instruct`)

Reference accuracy (400x5 pool): 0.494. Parse-failure rate: 0.6%. Failed calls: 2.
Variance components: sigma2_q = 0.1046 (between questions), sigma2_w = 0.1458 (within question / across seeds).

Coverage at the default design (N=50, K=5), B=2,000 subsamples (bayes: B=200):

| method | coverage | MC 95% interval | median width | verdict (sec.9) |
|---|---|---|---|---|
| naive | 0.796 | [0.778, 0.813] | 0.123 | UNDER-COVERS |
| question_means | 0.962 | [0.953, 0.970] | 0.208 | ok |
| cluster | 0.962 | [0.953, 0.970] | 0.208 | ok |
| bootstrap | 0.970 | [0.962, 0.977] | 0.216 | ok |
| seed_only (different estimand) | 0.608 | [0.586, 0.629] | 0.085 | UNDER-COVERS |
| bayes | 0.965 | [0.930, 0.983] | 0.190 | ok |

Exploratory (not in PLAN.md): against its *own* fixed-question estimand, seed_only's coverage at the default design is 1.000 [0.998, 1.000] — it covers the question it actually answers.

Under-coverage verdicts (sec.9: coverage < 0.93 with MC interval excluding 0.95), all designs:

| method | N | K | coverage | MC interval |
|---|---|---|---|---|
| naive | 25 | 2 | 0.908 | [0.895, 0.920] |
| naive | 25 | 3 | 0.876 | [0.861, 0.890] |
| naive | 25 | 5 | 0.783 | [0.765, 0.801] |
| naive | 50 | 2 | 0.915 | [0.902, 0.927] |
| naive | 50 | 3 | 0.875 | [0.860, 0.889] |
| naive | 50 | 5 | 0.796 | [0.778, 0.813] |
| naive | 100 | 3 | 0.888 | [0.873, 0.901] |
| naive | 100 | 5 | 0.829 | [0.812, 0.845] |
| naive | 200 | 5 | 0.903 | [0.890, 0.916] |

## Inkling (`thinkingmachines/Inkling`)

Reference accuracy (400x5 pool): 0.862. Parse-failure rate: 9.7%. Failed calls: 2.
Variance components: sigma2_q = 0.0966 (between questions), sigma2_w = 0.0230 (within question / across seeds).

Coverage at the default design (N=50, K=5), B=2,000 subsamples (bayes: B=200):

| method | coverage | MC 95% interval | median width | verdict (sec.9) |
|---|---|---|---|---|
| naive | 0.704 | [0.683, 0.723] | 0.085 | UNDER-COVERS |
| question_means | 0.943 | [0.931, 0.952] | 0.181 | ok |
| cluster | 0.943 | [0.931, 0.952] | 0.181 | ok |
| bootstrap | 0.951 | [0.941, 0.960] | 0.176 | ok |
| seed_only (different estimand) | 0.288 | [0.269, 0.308] | 0.033 | UNDER-COVERS |
| bayes | 0.825 | [0.766, 0.871] | 0.165 | UNDER-COVERS |

Exploratory (not in PLAN.md): against its *own* fixed-question estimand, seed_only's coverage at the default design is 1.000 [0.998, 1.000] — it covers the question it actually answers.

Under-coverage verdicts (sec.9: coverage < 0.93 with MC interval excluding 0.95), all designs:

| method | N | K | coverage | MC interval |
|---|---|---|---|---|
| bayes | 25 | 2 | 0.865 | [0.811, 0.906] |
| bayes | 25 | 3 | 0.790 | [0.728, 0.841] |
| bayes | 25 | 5 | 0.805 | [0.745, 0.854] |
| bayes | 50 | 2 | 0.870 | [0.816, 0.910] |
| bayes | 50 | 3 | 0.915 | [0.868, 0.946] |
| bayes | 50 | 5 | 0.825 | [0.766, 0.871] |
| bayes | 100 | 2 | 0.905 | [0.856, 0.938] |
| bayes | 100 | 3 | 0.885 | [0.833, 0.922] |
| bayes | 100 | 5 | 0.890 | [0.839, 0.926] |
| bootstrap | 25 | 1 | 0.865 | [0.849, 0.879] |
| bootstrap | 25 | 2 | 0.911 | [0.898, 0.923] |
| bootstrap | 25 | 5 | 0.912 | [0.899, 0.924] |
| cluster | 25 | 1 | 0.874 | [0.858, 0.887] |
| cluster | 25 | 2 | 0.914 | [0.901, 0.926] |
| cluster | 25 | 5 | 0.906 | [0.892, 0.918] |
| naive | 25 | 1 | 0.929 | [0.917, 0.939] |
| naive | 25 | 2 | 0.840 | [0.823, 0.855] |
| naive | 25 | 3 | 0.804 | [0.787, 0.821] |
| naive | 25 | 5 | 0.661 | [0.640, 0.681] |
| naive | 50 | 2 | 0.857 | [0.840, 0.871] |
| naive | 50 | 3 | 0.808 | [0.791, 0.825] |
| naive | 50 | 5 | 0.704 | [0.683, 0.723] |
| naive | 100 | 2 | 0.902 | [0.888, 0.914] |
| naive | 100 | 3 | 0.825 | [0.808, 0.841] |
| naive | 100 | 5 | 0.706 | [0.686, 0.726] |
| naive | 200 | 3 | 0.906 | [0.892, 0.918] |
| naive | 200 | 5 | 0.799 | [0.781, 0.816] |
| question_means | 25 | 1 | 0.874 | [0.858, 0.887] |
| question_means | 25 | 2 | 0.914 | [0.901, 0.926] |
| question_means | 25 | 5 | 0.906 | [0.892, 0.918] |

## Muse-Glimmer-30B (`meta-models/Muse-Glimmer-30B`)

Reference accuracy (400x5 pool): 0.648. Parse-failure rate: 31.6%. Failed calls: 1.
Variance components: sigma2_q = 0.1798 (between questions), sigma2_w = 0.0488 (within question / across seeds).

Coverage at the default design (N=50, K=5), B=2,000 subsamples (bayes: B=200):

| method | coverage | MC 95% interval | median width | verdict (sec.9) |
|---|---|---|---|---|
| naive | 0.689 | [0.668, 0.709] | 0.117 | UNDER-COVERS |
| question_means | 0.957 | [0.947, 0.965] | 0.249 | ok |
| cluster | 0.957 | [0.947, 0.965] | 0.249 | ok |
| bootstrap | 0.963 | [0.953, 0.970] | 0.244 | ok |
| seed_only (different estimand) | 0.334 | [0.313, 0.354] | 0.049 | UNDER-COVERS |
| bayes | 0.940 | [0.898, 0.965] | 0.206 | ok |

Exploratory (not in PLAN.md): against its *own* fixed-question estimand, seed_only's coverage at the default design is 1.000 [0.998, 1.000] — it covers the question it actually answers.

Under-coverage verdicts (sec.9: coverage < 0.93 with MC interval excluding 0.95), all designs:

| method | N | K | coverage | MC interval |
|---|---|---|---|---|
| naive | 25 | 2 | 0.885 | [0.871, 0.899] |
| naive | 25 | 3 | 0.776 | [0.758, 0.794] |
| naive | 25 | 5 | 0.664 | [0.644, 0.685] |
| naive | 50 | 2 | 0.882 | [0.867, 0.895] |
| naive | 50 | 3 | 0.810 | [0.793, 0.827] |
| naive | 50 | 5 | 0.689 | [0.668, 0.709] |
| naive | 100 | 2 | 0.913 | [0.900, 0.925] |
| naive | 100 | 3 | 0.841 | [0.824, 0.856] |
| naive | 100 | 5 | 0.712 | [0.692, 0.731] |
| naive | 200 | 3 | 0.907 | [0.893, 0.919] |
| naive | 200 | 5 | 0.829 | [0.812, 0.845] |

## Paired model differences

Full-pool paired intervals on the matched 400 x 5 grid (difference = first model minus second):

| pair | method | estimate | 95% interval | width |
|---|---|---|---|---|
| Qwen-2-1.5B-Instruct - Muse-Glimmer-30B | naive | -0.154 | [-0.184, -0.123] | 0.061 |
| Qwen-2-1.5B-Instruct - Muse-Glimmer-30B | paired_cluster | -0.153 | [-0.195, -0.112] | 0.083 |
| Qwen-2-1.5B-Instruct - Muse-Glimmer-30B | paired_bootstrap | -0.153 | [-0.197, -0.107] | 0.090 |
| Qwen-2-1.5B-Instruct - Inkling | naive | -0.367 | [-0.394, -0.340] | 0.053 |
| Qwen-2-1.5B-Instruct - Inkling | paired_cluster | -0.367 | [-0.405, -0.329] | 0.077 |
| Qwen-2-1.5B-Instruct - Inkling | paired_bootstrap | -0.367 | [-0.406, -0.324] | 0.082 |
| Muse-Glimmer-30B - Inkling | naive | -0.214 | [-0.239, -0.188] | 0.052 |
| Muse-Glimmer-30B - Inkling | paired_cluster | -0.213 | [-0.248, -0.179] | 0.070 |
| Muse-Glimmer-30B - Inkling | paired_bootstrap | -0.213 | [-0.249, -0.177] | 0.072 |

Paired coverage at the default design (N=50, K=5), B=2,000:

| pair | method | coverage | MC interval | median width |
|---|---|---|---|---|
| Qwen-2-1.5B-Instruct - Muse-Glimmer-30B | naive | 0.881 | [0.866, 0.894] | 0.171 |
| Qwen-2-1.5B-Instruct - Muse-Glimmer-30B | paired_cluster | 0.966 | [0.957, 0.973] | 0.238 |
| Qwen-2-1.5B-Instruct - Muse-Glimmer-30B | paired_bootstrap | 0.975 | [0.967, 0.981] | 0.248 |
| Qwen-2-1.5B-Instruct - Inkling | naive | 0.852 | [0.835, 0.866] | 0.151 |
| Qwen-2-1.5B-Instruct - Inkling | paired_cluster | 0.959 | [0.949, 0.967] | 0.219 |
| Qwen-2-1.5B-Instruct - Inkling | paired_bootstrap | 0.967 | [0.958, 0.974] | 0.232 |
| Muse-Glimmer-30B - Inkling | naive | 0.866 | [0.850, 0.880] | 0.146 |
| Muse-Glimmer-30B - Inkling | paired_cluster | 0.952 | [0.941, 0.960] | 0.201 |
| Muse-Glimmer-30B - Inkling | paired_bootstrap | 0.957 | [0.947, 0.965] | 0.204 |

Coverage and widths for all paired designs (N in {25, 50, 100, 200} x K in {1, 5}) are in results/paired_coverage.csv.

## Budget analysis (fixed budget: 250 calls)

Empirical median interval widths from dedicated subsamples (B=2,000) at each split, with the width predicted from the variance components (2 x 1.96 x predicted SE). Best split = narrowest cluster-method width.

### Qwen-2-1.5B-Instruct

| split (NxK) | predicted width | naive | question_means | cluster | bootstrap | seed_only |
|---|---|---|---|---|---|---|
| 250x1 | 0.124 | 0.123 | 0.125 | 0.125 | 0.124 | 0.000 |
| 125x2 | 0.148 | 0.123 | 0.149 | 0.149 | 0.160 | 0.067 |
| 83x3 | 0.168 | 0.123 | 0.171 | 0.171 | 0.185 | 0.077 |
| 50x5 | 0.203 | 0.123 | 0.207 | 0.207 | 0.216 | 0.085 |

Best split for Qwen-2-1.5B-Instruct: 250 questions x 1 seed(s) (cluster median width 0.125, vs 0.207 at 50x5).

### Muse-Glimmer-30B

| split (NxK) | predicted width | naive | question_means | cluster | bootstrap | seed_only |
|---|---|---|---|---|---|---|
| 250x1 | 0.119 | 0.118 | 0.119 | 0.119 | 0.120 | 0.000 |
| 125x2 | 0.158 | 0.118 | 0.160 | 0.160 | 0.164 | 0.038 |
| 83x3 | 0.191 | 0.118 | 0.194 | 0.194 | 0.193 | 0.045 |
| 50x5 | 0.241 | 0.118 | 0.249 | 0.249 | 0.244 | 0.049 |

Best split for Muse-Glimmer-30B: 250 questions x 1 seed(s) (cluster median width 0.119, vs 0.249 at 50x5).

### Inkling

| split (NxK) | predicted width | naive | question_means | cluster | bootstrap | seed_only |
|---|---|---|---|---|---|---|
| 250x1 | 0.086 | 0.086 | 0.087 | 0.087 | 0.084 | 0.000 |
| 125x2 | 0.115 | 0.085 | 0.116 | 0.116 | 0.116 | 0.027 |
| 83x3 | 0.139 | 0.085 | 0.142 | 0.142 | 0.141 | 0.031 |
| 50x5 | 0.176 | 0.085 | 0.181 | 0.181 | 0.176 | 0.033 |

Best split for Inkling: 250 questions x 1 seed(s) (cluster median width 0.087, vs 0.181 at 50x5).

## Implementation notes (Stage 4)

- analyze.py was extended to implement PLAN.md secs.7, 10 and 11 in full (paired study, budget analysis, empirical SEs, full figure set, colour-blind-safe palette), as anticipated by PLAN.md sec.13 item 2. Pure additions implementing the frozen plan; no definition changed.
- The two-stage bootstrap is computed by a vectorized implementation of the sec.8 definition (the frozen loop implementation in intervals.py costs ~3.7 s per subsample at N=200, which is infeasible at B=2,000 x 16 designs x 3 models). Agreement with the frozen implementation was checked on four matrix shapes over five seeds each: bootstrap SEs agreed within 0.003 and interval widths within 0.007 (Monte Carlo error). intervals.py is unchanged.
- The (400, 5) matrix per model is asserted complete with no missing cells before the ANOVA variance components, per PLAN.md sec.13 item 3; the assertion passed for all three models.
- Bayes coverage uses the first 200 of the 2,000 subsamples per design (PLAN.md sec.7) and is cached under results/bayes_cache/ (deterministic given the study seeds; delete to recompute).

## Amendments to PLAN.md

None. The amendment log in PLAN.md sec.14 is empty; no definition in the frozen plan was changed.

## Limitations

As stated in PLAN.md sec.12: one benchmark (GSM8K, one prompt); three models chosen for mid-range pilot accuracy; the reference truth is the finite 400x5 pool, so large-N coverage is conservative in the stated way; Muse-Glimmer-30B's parse failures (26.2% in the pilot) mean part of its measured inaccuracy is output behaviour, not question difficulty; Bayes coverage rests on 200 subsamples per design, so its Monte Carlo intervals are wider.
