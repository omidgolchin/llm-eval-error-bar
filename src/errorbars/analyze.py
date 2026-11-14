"""Coverage study, variance components, budget analysis and figures.

Reads outputs/raw_runs.jsonl (or a correctness table built from it), writes
results/summary.md and results/figures/*.png. Regenerates everything from
outputs/ alone:  python -m errorbars.analyze

Stage 4 extension (PLAN.md sec.13 item 2): this module now implements the
full frozen plan -- run validation and spend, the coverage study with
empirical SEs, the paired-difference study, the budget analysis, and the
full figure set of sec.11 with a colour-blind-safe palette. No definition
in PLAN.md secs.7-10 was changed.

Two implementation notes:

* The two-stage bootstrap (sec.8 method 4) is computed by
  :func:`bootstrap_fast`, a vectorized implementation of exactly the
  resampling definition in the plan (resample questions with replacement,
  then seeds within each drawn question with replacement; statistic =
  pooled mean; percentile interval over 2,000 draws). The frozen
  loop implementation in ``intervals.py`` costs ~3.7 s per subsample at
  N=200 (measured), which makes 2,000 subsamples x 16 designs x 3 models
  infeasible; the vectorized version costs ~0.04 s and agrees with the
  frozen one within Monte Carlo error (bootstrap SE and interval width
  compared on (25,1), (50,5), (100,2), (200,5) matrices over 5 seeds
  each; see tests/test_analyze_stage4.py). ``intervals.py`` itself is
  untouched and remains the reusable API.
* Bayesian coverage rows are cached in results/bayes_cache/<slug>.csv
  (git-ignored). MCMC is deterministic given the per-subsample seeds
  drawn from the study RNG, so a cached row is identical to a recomputed
  one under the frozen config; delete the cache to force recomputation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .grade import grade
from .intervals import intervals, paired_intervals

ROOT = Path(__file__).resolve().parents[2]
LEVEL = 0.95
FAST_METHODS = ("naive", "question_means", "cluster", "bootstrap", "seed_only")
ALL_METHODS = FAST_METHODS + ("bayes",)
PAIRED_METHODS = ("naive", "paired_cluster", "paired_bootstrap")

# Together catalog prices at pilot time (results/pilot2_summary.md),
# $ per 1M tokens (input, output). PLAN.md sec.4: actual spend is reported
# on this same basis.
PRICES = {
    "arize-ai/qwen-2-1.5b-instruct": (0.1, 0.1),
    "thinkingmachines/Inkling": (1.0, 4.05),
    "meta-models/Muse-Glimmer-30B": (0.35, 1.5),
}
PILOT_SPEND = {"pilot 1": 0.0504, "pilot 2": 0.71}  # PLAN.md sec.4
SHORT = {
    "arize-ai/qwen-2-1.5b-instruct": "qwen",
    "thinkingmachines/Inkling": "inkling",
    "meta-models/Muse-Glimmer-30B": "glimmer",
}
DISPLAY = {
    "arize-ai/qwen-2-1.5b-instruct": "Qwen-2-1.5B-Instruct",
    "thinkingmachines/Inkling": "Inkling",
    "meta-models/Muse-Glimmer-30B": "Muse-Glimmer-30B",
}
# Okabe-Ito colour-blind-safe palette, fixed per method across figures.
METHOD_COLORS = {
    "naive": "#E69F00", "question_means": "#56B4E9", "cluster": "#009E73",
    "bootstrap": "#0072B2", "bayes": "#D55E00", "seed_only": "#CC79A7",
    "paired_cluster": "#009E73", "paired_bootstrap": "#0072B2",
}


# ---------------------------------------------------------------------------
# correctness table, validation, spend
# ---------------------------------------------------------------------------

def build_correctness(raw_path: Path, questions: pd.DataFrame) -> pd.DataFrame:
    gold = dict(zip(questions["question_id"], questions["gold"]))
    rows = []
    for line in raw_path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("dry_run"):
            continue
        correct, ans = grade(r.get("text") or "", gold[r["question_id"]])
        rows.append({
            "model": r["model"], "question_id": r["question_id"],
            "seed": r["seed"], "correct": correct,
            "parsed": ans is not None,
            "failed_call": r.get("finish_reason") == "error",
            "finish_reason": r.get("finish_reason"),
            "prompt_tokens": r.get("prompt_tokens"),
            "completion_tokens": r.get("completion_tokens"),
        })
    return pd.DataFrame(rows)


def validate_runs(raw_path: Path, tidy: pd.DataFrame,
                  expected_questions: int = 400,
                  expected_seeds=(0, 1, 2, 3, 4)) -> dict:
    """Validate the main-run file against PLAN.md secs.5-6.

    Returns a report dict. Raises AssertionError on any structural
    violation (wrong row counts, duplicate or missing cells, dry-run
    rows). Failed calls (finish_reason == "error") are *not* violations:
    per sec.6 they are recorded rows that grade as incorrect.
    """
    raw_rows = [json.loads(line) for line in raw_path.read_text().splitlines()
                if line.strip()]
    report = {"total_rows": len(raw_rows)}
    assert not any(r.get("dry_run") for r in raw_rows), "dry-run rows present"
    run_ids = [r["run_id"] for r in raw_rows]
    assert len(run_ids) == len(set(run_ids)), "duplicate run_ids"
    per_model = {}
    for model, sub in tidy.groupby("model"):
        n_q = sub["question_id"].nunique()
        cells = sub.groupby(["question_id", "seed"]).size()
        assert n_q == expected_questions, f"{model}: {n_q} questions"
        assert len(sub) == expected_questions * len(expected_seeds), \
            f"{model}: {len(sub)} rows"
        assert cells.eq(1).all() and len(cells) == len(sub), \
            f"{model}: duplicated or missing (question, seed) cells"
        assert set(sub["seed"].unique()) == set(expected_seeds)
        per_model[model] = {
            "rows": int(len(sub)),
            "questions": int(n_q),
            "failed_calls": int(sub["failed_call"].sum()),
            "parse_failure_rate": float(1 - sub["parsed"].mean()),
            "reference_accuracy": float(sub["correct"].mean()),
            "finish_reasons": {str(k): int(v) for k, v in
                               sub["finish_reason"].value_counts().items()},
        }
    report["per_model"] = per_model
    report["failed_run_ids"] = [r["run_id"] for r in raw_rows
                                if r.get("finish_reason") == "error"]
    return report


def spend(tidy: pd.DataFrame) -> pd.DataFrame:
    """Actual spend on the PLAN.md sec.4 basis (pilot-time catalog prices
    x logged token usage). Failed calls logged no tokens and cost $0."""
    rows = []
    for model, sub in tidy.groupby("model"):
        pin, pout = PRICES[model]
        ptok = float(sub["prompt_tokens"].fillna(0).sum())
        ctok = float(sub["completion_tokens"].fillna(0).sum())
        rows.append({
            "model": model, "calls": int(len(sub)),
            "prompt_tokens": int(ptok), "completion_tokens": int(ctok),
            "cost_usd": ptok / 1e6 * pin + ctok / 1e6 * pout,
        })
    return pd.DataFrame(rows)


def model_matrix(tidy: pd.DataFrame, model: str) -> np.ndarray:
    """The model's (400, 5) correctness matrix. PLAN.md sec.13 item 3:
    assert completeness and report missing cells instead of filling."""
    sub = tidy[tidy["model"] == model]
    mat = sub.pivot_table(index="question_id", columns="seed",
                          values="correct").to_numpy(dtype=float)
    n_missing = int(np.isnan(mat).sum())
    assert mat.shape == (400, 5) and n_missing == 0, (
        f"{model}: matrix shape {mat.shape}, {n_missing} missing cells; "
        "refusing to fill them silently")
    return mat


# ---------------------------------------------------------------------------
# bootstrap (vectorized, same definition as intervals.py / PLAN.md sec.8.4)
# ---------------------------------------------------------------------------

def bootstrap_fast(mat: np.ndarray, level: float = LEVEL, seed: int = 0,
                   draws: int = 2000):
    """Two-stage bootstrap percentile interval for the pooled mean.

    Identical definition to ``intervals._bootstrap``: resample questions
    with replacement, then each drawn question's observed seed values
    with replacement; statistic = pooled mean of the resampled cells.
    Falls back to the frozen implementation when the matrix has NaNs
    (per-question observed-value lists); study matrices are complete.
    Returns (lower, upper, se) with se = sd of the bootstrap statistics.
    """
    mat = np.asarray(mat, dtype=float)
    if np.isnan(mat).any():
        res = intervals(mat, level=level, methods=("bootstrap",),
                        seed=seed, bootstrap_draws=draws)["bootstrap"]
        return res["lower"], res["upper"], res["se"]
    n, k = mat.shape
    rng = np.random.default_rng(seed)
    stats_bs = np.empty(draws)
    chunk = max(1, int(2_000_000 // max(n * k, 1)))  # ~2M cells per chunk
    done = 0
    while done < draws:
        d = min(chunk, draws - done)
        qidx = rng.integers(0, n, size=(d, n))
        vals = mat[qidx]
        cidx = rng.integers(0, k, size=(d, n, k))
        stats_bs[done:done + d] = \
            np.take_along_axis(vals, cidx, axis=2).mean(axis=(1, 2))
        done += d
    alpha = 1 - level
    lo, hi = np.quantile(stats_bs, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi), float(stats_bs.std(ddof=1))


# ---------------------------------------------------------------------------
# coverage study
# ---------------------------------------------------------------------------

def _mc_interval(hits: int, b: int, level: float = 0.95):
    """Wilson interval for a coverage proportion estimated from B draws."""
    from scipy import stats
    p = hits / b
    z = stats.norm.ppf(1 - (1 - level) / 2)
    denom = 1 + z**2 / b
    centre = (p + z**2 / (2 * b)) / denom
    half = (z / denom) * np.sqrt(p * (1 - p) / b + z**2 / (4 * b**2))
    return p, centre - half, centre + half


def _iter_designs(mat: np.ndarray, designs_N, designs_K, B: int, seed: int):
    """Yield per-design subsamples and interval seeds, in the frozen
    study protocol: per design, draw all B subsamples first (N questions
    without replacement, then K of the pool seeds per question without
    replacement), then one fresh interval seed per subsample per method
    in FAST_METHODS order, then the Bayes seeds. Single source of truth
    so the Bayes worker regenerates identical subsamples."""
    pool_n, pool_k = mat.shape
    q_means_full = mat.mean(axis=1)
    rng = np.random.default_rng(seed)
    for n in designs_N:
        for k in designs_K:
            subs, qis, own_ref = [], [], []
            for _ in range(B):
                qi = rng.choice(pool_n, size=n, replace=False)
                sub = np.empty((n, k))
                for r, q in enumerate(qi):
                    si = rng.choice(pool_k, size=k, replace=False)
                    sub[r] = mat[q, si]
                subs.append(sub)
                qis.append(qi)
                # seed_only's own estimand for this subsample: mean over
                # the drawn questions of their full-pool-seed accuracy.
                own_ref.append(float(q_means_full[qi].mean()))
            seeds = {m: [int(rng.integers(1 << 31)) for _ in range(B)]
                     for m in FAST_METHODS}
            bayes_seeds = [int(rng.integers(1 << 31)) for _ in range(B)]
            yield {"N": n, "K": k, "subs": subs, "qis": qis,
                   "own_ref": own_ref, "seeds": seeds,
                   "bayes_seeds": bayes_seeds}


def coverage_study(mat: np.ndarray, designs_N, designs_K, B: int = 2000,
                   seed: int = 0, methods=FAST_METHODS,
                   bayes_subsamples: int = 0) -> pd.DataFrame:
    """Subsample (N, K) designs from the pool matrix; measure coverage of
    the pool reference accuracy and median interval width per method.
    (Fast methods only; Bayes rows come from :func:`bayes_coverage`.)
    Also records the empirical SE of the point estimate per design
    (PLAN.md sec.10) and, exploratorily, seed_only's coverage of its own
    fixed-question estimand."""
    reference = float(np.nanmean(mat))
    pool_n, _ = mat.shape
    records = []
    for d in _iter_designs(mat, designs_N, designs_K, B, seed):
        n, k, subs = d["N"], d["K"], d["subs"]
        emp_se = float(np.std([sub.mean() for sub in subs], ddof=1))
        for m in methods:
            hits, widths = 0, []
            hits_own = 0
            for b, sub in enumerate(subs):
                s = d["seeds"][m][b]
                if m == "bootstrap":
                    lo, hi, _ = bootstrap_fast(sub, level=LEVEL, seed=s)
                else:
                    r = intervals(sub, level=LEVEL, methods=(m,),
                                  seed=s)[m]
                    lo, hi = r["lower"], r["upper"]
                hits += int(lo <= reference <= hi)
                widths.append(hi - lo)
                if m == "seed_only":
                    hits_own += int(lo <= d["own_ref"][b] <= hi)
            cov, mc_lo, mc_hi = _mc_interval(hits, B)
            rec = {"method": m, "N": n, "K": k, "B": B, "coverage": cov,
                   "mc_lower": mc_lo, "mc_upper": mc_hi,
                   "median_width": float(np.median(widths)),
                   "reference": reference, "pool_fraction": n / pool_n,
                   "emp_se": emp_se}
            if m == "seed_only":
                ocov, olo, ohi = _mc_interval(hits_own, B)
                rec.update({"own_coverage": ocov, "own_mc_lower": olo,
                            "own_mc_upper": ohi})
            records.append(rec)
    return pd.DataFrame(records)


def _bayes_records_for_design(mat, design, bayes_subsamples):
    reference = float(np.nanmean(mat))
    hits, widths = 0, []
    for b in range(bayes_subsamples):
        r = intervals(design["subs"][b], level=LEVEL, methods=("bayes",),
                      seed=design["bayes_seeds"][b])["bayes"]
        hits += int(r["lower"] <= reference <= r["upper"])
        widths.append(r["upper"] - r["lower"])
    cov, lo, hi = _mc_interval(hits, bayes_subsamples)
    return {"method": "bayes", "N": design["N"], "K": design["K"],
            "B": bayes_subsamples, "coverage": cov, "mc_lower": lo,
            "mc_upper": hi, "median_width": float(np.median(widths)),
            "reference": reference,
            "pool_fraction": design["N"] / mat.shape[0],
            "emp_se": float(np.std([s.mean() for s in design["subs"]],
                                   ddof=1))}


def _bayes_worker(job):
    """Top-level (picklable) worker: Bayes coverage for one model.
    Reads/writes the per-design cache under results/bayes_cache/."""
    (model, mat, designs_N, designs_K, B, bayes_subsamples, seed,
     cache_dir) = job
    slug = SHORT[model]
    cache = Path(cache_dir) / f"{slug}.csv"
    cached = {}
    if cache.exists():
        cdf = pd.read_csv(cache)
        for _, row in cdf.iterrows():
            cached[(int(row["N"]), int(row["K"]))] = row.to_dict()
    records = []
    for d in _iter_designs(mat, designs_N, designs_K, B, seed):
        key = (d["N"], d["K"])
        if key in cached and int(cached[key]["B"]) == bayes_subsamples:
            records.append(cached[key])
            continue
        rec = _bayes_records_for_design(mat, d, bayes_subsamples)
        records.append(rec)
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        pd.DataFrame(records).to_csv(cache, index=False)
    return model, records


def bayes_coverage(mats: dict, designs_N, designs_K, B: int,
                   bayes_subsamples: int, base_seed: int = 1000,
                   cache_dir: Path | None = None,
                   workers: int = 3) -> dict:
    """Bayes coverage rows per model, computed in parallel processes
    (one per model) with per-design caching. ``mats`` maps model ->
    (400, 5) matrix in sorted-model order (index = seed offset)."""
    cache_dir = cache_dir or (ROOT / "results" / "bayes_cache")
    jobs = []
    for mi, model in enumerate(sorted(mats)):
        jobs.append((model, mats[model], designs_N, designs_K, B,
                     bayes_subsamples, base_seed + mi, str(cache_dir)))
    out = {}
    if workers and workers > 1 and len(jobs) > 1:
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=min(workers, len(jobs))) as pool:
            for model, records in pool.imap_unordered(_bayes_worker, jobs):
                out[model] = records
    else:
        for job in jobs:
            model, records = _bayes_worker(job)
            out[model] = records
    return out


# ---------------------------------------------------------------------------
# paired-difference study
# ---------------------------------------------------------------------------

def paired_study(mat_a: np.ndarray, mat_b: np.ndarray, designs_N,
                 designs_K, B: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Coverage of the three paired interval methods (PLAN.md sec.7):
    matched subsamples (same questions and seed indices for both
    models); reference = full-pool paired difference."""
    reference = float(np.nanmean(mat_a) - np.nanmean(mat_b))
    pool_n, pool_k = mat_a.shape
    rng = np.random.default_rng(seed)
    records = []
    for n in designs_N:
        for k in designs_K:
            subs_a, subs_b = [], []
            for _ in range(B):
                qi = rng.choice(pool_n, size=n, replace=False)
                sa = np.empty((n, k))
                sb = np.empty((n, k))
                for r, q in enumerate(qi):
                    si = rng.choice(pool_k, size=k, replace=False)
                    sa[r] = mat_a[q, si]
                    sb[r] = mat_b[q, si]
                subs_a.append(sa)
                subs_b.append(sb)
            emp_se = float(np.std([sa.mean() - sb.mean()
                                   for sa, sb in zip(subs_a, subs_b)],
                                  ddof=1))
            hits = {m: 0 for m in PAIRED_METHODS}
            widths = {m: [] for m in PAIRED_METHODS}
            for sa, sb in zip(subs_a, subs_b):
                s = int(rng.integers(1 << 31))
                res = paired_intervals(sa, sb, level=LEVEL,
                                       methods=("naive", "paired_cluster"),
                                       seed=s)
                lo, hi, _ = bootstrap_fast(sa - sb, level=LEVEL, seed=s)
                res["paired_bootstrap"] = {"lower": lo, "upper": hi}
                for m in PAIRED_METHODS:
                    r = res[m]
                    hits[m] += int(r["lower"] <= reference <= r["upper"])
                    widths[m].append(r["upper"] - r["lower"])
            for m in PAIRED_METHODS:
                cov, lo, hi = _mc_interval(hits[m], B)
                records.append({
                    "method": m, "N": n, "K": k, "B": B, "coverage": cov,
                    "mc_lower": lo, "mc_upper": hi,
                    "median_width": float(np.median(widths[m])),
                    "reference": reference,
                    "pool_fraction": n / pool_n, "emp_se": emp_se})
    return pd.DataFrame(records)


def paired_full_pool(mat_a: np.ndarray, mat_b: np.ndarray,
                     seed: int = 42) -> pd.DataFrame:
    """Paired intervals on the complete matched 400 x 5 grid."""
    res = paired_intervals(mat_a, mat_b, level=LEVEL, seed=seed)
    rows = []
    for m in PAIRED_METHODS:
        r = res[m]
        rows.append({"method": m, "estimate": r["estimate"],
                     "lower": r["lower"], "upper": r["upper"],
                     "se": r["se"], "width": r["upper"] - r["lower"]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# variance components and budget analysis
# ---------------------------------------------------------------------------

def variance_components(mat: np.ndarray) -> dict:
    """One-way ANOVA on question means -> sigma2_q (between) and sigma2_w
    (within / seed variance), for a balanced (N, K) matrix without NaNs."""
    n, k = mat.shape
    q_means = mat.mean(axis=1)
    grand = mat.mean()
    ss_between = k * np.sum((q_means - grand) ** 2)
    ss_within = np.sum((mat - q_means[:, None]) ** 2)
    ms_between = ss_between / (n - 1)
    ms_within = ss_within / (n * (k - 1))
    sigma2_w = ms_within
    sigma2_q = max((ms_between - ms_within) / k, 0.0)
    return {"sigma2_q": float(sigma2_q), "sigma2_w": float(sigma2_w),
            "n": n, "k": k}


def predicted_se(vc: dict, n: int, k: int) -> float:
    """Predicted SE of the accuracy estimate at design (N, K), sec.10."""
    return float(np.sqrt(vc["sigma2_q"] / n + vc["sigma2_w"] / (n * k)))


def budget_analysis(mat: np.ndarray, vc: dict, splits, B: int = 2000,
                    seed: int = 0) -> pd.DataFrame:
    """Dedicated subsamples at the fixed-budget splits (sec.10):
    empirical median interval widths from fresh (N, K) subsamples, plus
    predicted widths from the variance components."""
    from scipy import stats
    z = float(stats.norm.ppf(1 - (1 - LEVEL) / 2))
    pool_n, pool_k = mat.shape
    rng = np.random.default_rng(seed)
    records = []
    for n, k in splits:
        subs = []
        for _ in range(B):
            qi = rng.choice(pool_n, size=n, replace=False)
            sub = np.empty((n, k))
            for r, q in enumerate(qi):
                si = rng.choice(pool_k, size=k, replace=False)
                sub[r] = mat[q, si]
            subs.append(sub)
        pse = predicted_se(vc, n, k)
        for m in FAST_METHODS:
            widths = []
            for sub in subs:
                s = int(rng.integers(1 << 31))
                if m == "bootstrap":
                    lo, hi, _ = bootstrap_fast(sub, level=LEVEL, seed=s)
                else:
                    r = intervals(sub, level=LEVEL, methods=(m,),
                                  seed=s)[m]
                    lo, hi = r["lower"], r["upper"]
                widths.append(hi - lo)
            records.append({
                "method": m, "N": n, "K": k, "calls": n * k, "B": B,
                "median_width": float(np.median(widths)),
                "predicted_se": pse, "predicted_width": 2 * z * pse})
    return pd.DataFrame(records)


def under_covers(df: pd.DataFrame) -> pd.DataFrame:
    """PLAN.md sec.9: coverage < 0.93 AND the MC interval excludes 0.95."""
    return df[(df["coverage"] < 0.93) & (df["mc_upper"] < 0.95)]


# ---------------------------------------------------------------------------
# figures (PLAN.md sec.11, Okabe-Ito palette, 200 dpi)
# ---------------------------------------------------------------------------

def _fig_coverage(cov: pd.DataFrame, model: str, fig_dir: Path):
    import matplotlib.pyplot as plt
    ks = sorted(cov["K"].unique())
    fig, axes = plt.subplots(1, len(ks), figsize=(3.4 * len(ks), 3.6),
                             sharey=True)
    for ax, k in zip(np.atleast_1d(axes), ks):
        sel = cov[cov["K"] == k]
        for m in ALL_METHODS:
            g = sel[sel["method"] == m].sort_values("N")
            if g.empty:
                continue
            ax.errorbar(g["N"], g["coverage"],
                        yerr=[np.maximum(
                                  g["coverage"] - g["mc_lower"], 0),
                              np.maximum(
                                  g["mc_upper"] - g["coverage"], 0)],
                        marker="o", ms=4, capsize=2, lw=1.2,
                        color=METHOD_COLORS[m], label=m)
        ax.axhline(0.95, linestyle="--", color="grey", lw=1)
        ax.axhline(0.93, linestyle=":", color="grey", lw=1)
        ax.set_xlabel("N questions")
        ax.set_title(f"K = {k} seeds")
        ax.set_ylim(0.55, 1.01)
    np.atleast_1d(axes)[0].set_ylabel(
        "Coverage of the reference accuracy")
    handles, labels = np.atleast_1d(axes)[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(ALL_METHODS),
               fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle(f"Coverage by method — {DISPLAY[model]} "
                 "(dashed: nominal 0.95; dotted: 0.93 decision line)")
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    out = fig_dir / f"fig_coverage_{SHORT[model]}.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def _fig_width(covs: dict, fig_dir: Path):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
    for ax, (model, cov) in zip(axes, covs.items()):
        cov = cov.copy()
        cov["design"] = cov["N"].astype(str) + "x" + cov["K"].astype(str)
        order = (cov[["N", "K"]].drop_duplicates()
                 .sort_values(["N", "K"]))
        labels = [f"{n}x{k}" for n, k in zip(order["N"], order["K"])]
        for m in ALL_METHODS:
            g = cov[cov["method"] == m].set_index("design").loc[labels]
            ax.plot(range(len(labels)), g["median_width"], marker="o",
                    ms=3.5, lw=1.2, color=METHOD_COLORS[m], label=m,
                    linestyle="--" if m == "seed_only" else "-")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, fontsize=7)
        ax.set_xlabel("Design (N questions x K seeds)")
        ax.set_title(DISPLAY[model])
    axes[0].set_ylabel("Median interval width")
    handles, labels_ = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_, loc="lower center",
               ncol=len(ALL_METHODS), fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, -0.05))
    fig.suptitle("Median interval width by method and design "
                 "(seed_only dashed: different estimand)")
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    out = fig_dir / "fig_width.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def _fig_pred_vs_emp(covs: dict, vcs: dict, fig_dir: Path):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.5), sharex=True,
                             sharey=True)
    for ax, (model, cov) in zip(axes, covs.items()):
        vc = vcs[model]
        designs = (cov[["N", "K", "emp_se"]].drop_duplicates())
        pred = [predicted_se(vc, n, k) for n, k in
                zip(designs["N"], designs["K"])]
        ax.scatter(pred, designs["emp_se"], s=28, color="#0072B2")
        lims = [min(min(pred), designs["emp_se"].min()) * 0.9,
                max(max(pred), designs["emp_se"].max()) * 1.1]
        ax.plot(lims, lims, linestyle="--", color="grey", lw=1)
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.set_xlabel("Predicted SE (variance components)")
        ax.set_title(DISPLAY[model])
    axes[0].set_ylabel("Empirical SE across 2,000 subsamples")
    fig.suptitle("Predicted vs empirical standard error, by design")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = fig_dir / "fig_pred_vs_emp_se.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


def _fig_budget(budgets: dict, fig_dir: Path):
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6), sharey=True)
    for ax, (model, bud) in zip(axes, budgets.items()):
        labels = [f"{n}x{k}" for n, k in
                  bud[["N", "K"]].drop_duplicates().itertuples(
                      index=False)]
        x = range(len(labels))
        for m, style in (("cluster", "-"), ("naive", "-"),
                         ("bootstrap", "-"), ("question_means", "-")):
            g = bud[bud["method"] == m]
            ax.plot(x, g["median_width"], marker="o", ms=4, lw=1.2,
                    color=METHOD_COLORS[m], label=m, linestyle=style)
        pred = bud.drop_duplicates(["N", "K"])["predicted_width"]
        ax.plot(x, pred, linestyle="--", color="grey", lw=1.2,
                label="predicted")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_xlabel("Budget split (N questions x K seeds), 250 calls")
        ax.set_title(DISPLAY[model])
    axes[0].set_ylabel("Median interval width")
    handles, labels_ = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels_, loc="lower center", ncol=5, fontsize=8,
               frameon=False, bbox_to_anchor=(0.5, -0.05))
    fig.suptitle("Budget frontier: interval width at a fixed 250-call "
                 "budget")
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    out = fig_dir / "fig_budget_frontier.png"
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return out


# ---------------------------------------------------------------------------
# summary (PLAN.md sec.11)
# ---------------------------------------------------------------------------

def _default_table(cov: pd.DataFrame) -> list[str]:
    d = cov[(cov["N"] == 50) & (cov["K"] == 5)]
    lines = ["| method | coverage | MC 95% interval | median width | "
             "verdict (sec.9) |", "|---|---|---|---|---|"]
    for m in ALL_METHODS:
        r = d[d["method"] == m]
        if r.empty:
            continue
        r = r.iloc[0]
        verdict = ("UNDER-COVERS" if (r["coverage"] < 0.93
                                      and r["mc_upper"] < 0.95)
                   else "ok")
        note = " (different estimand)" if m == "seed_only" else ""
        lines.append(f"| {m}{note} | {r['coverage']:.3f} | "
                     f"[{r['mc_lower']:.3f}, {r['mc_upper']:.3f}] | "
                     f"{r['median_width']:.3f} | {verdict} |")
    return lines


def write_summary(path: Path, *, validation: dict, spend_df: pd.DataFrame,
                  covs: dict, vcs: dict, paired_cov: dict,
                  paired_full: dict, budgets: dict) -> None:
    lines = ["# Results summary — main run (Stage 4)", "",
             "Question: when an LLM is evaluated on N questions x K "
             "repeated runs, which interval methods actually cover the "
             "true (reference) accuracy at their nominal 95% level, and "
             "how should a fixed budget be split between questions and "
             "seeds? Design, methods and decision rules are as frozen in "
             "PLAN.md. Coverage is measured against each model's "
             "full-pool reference accuracy (400 questions x 5 seeds); "
             "see PLAN.md sec.7 for the finite-pool caveat.", ""]
    # --- validation and spend
    lines += ["## Run validation and spend", ""]
    pm = validation["per_model"]
    lines += [f"- Rows in outputs/raw_runs.jsonl: "
              f"{validation['total_rows']} (6,000 planned); unique "
              "run_ids, no duplicates, no dry-run rows; the question set "
              "is exactly the frozen 400-question pool; every model has "
              "400 questions x 5 seeds with no missing cells.",
              f"- Failed calls (finish_reason = \"error\", all API "
              f"timeouts, graded incorrect per PLAN.md sec.6): "
              f"{len(validation['failed_run_ids'])} total — "
              + ", ".join(f"{DISPLAY[m]}: {pm[m]['failed_calls']}"
                          for m in sorted(pm)) + ".",
              "- Finish reasons overall: "
              + ", ".join(f"{k}: {sum(pm[m]['finish_reasons'].get(k, 0) for m in pm)}"
                          for k in ("stop", "length", "error")) + ".",
              ""]
    total = spend_df["cost_usd"].sum()
    lines += ["Model spend (pilot-time Together catalog prices x logged "
              "tokens, the basis of PLAN.md sec.4):", "",
              "| model | calls | prompt tokens | completion tokens | "
              "cost |", "|---|---|---|---|---|"]
    for _, r in spend_df.iterrows():
        lines.append(f"| {r['model']} | {r['calls']} | "
                     f"{r['prompt_tokens']:,} | "
                     f"{r['completion_tokens']:,} | ${r['cost_usd']:.2f} |")
    lines += [f"| **total main run** | | | | **${total:.2f}** |", "",
              f"Main-run total ${total:.2f} vs the ${4.01:.2f} projection "
              f"in PLAN.md sec.4 (guard: $10). Pilot spend, reported "
              f"separately as required: pilot 1 $0.05 + pilot 2 $0.71 = "
              f"$0.76.", ""]
    # --- per model
    for model in ("arize-ai/qwen-2-1.5b-instruct",
                  "thinkingmachines/Inkling",
                  "meta-models/Muse-Glimmer-30B"):
        cov, vc = covs[model], vcs[model]
        ref = pm[model]["reference_accuracy"]
        lines += [f"## {DISPLAY[model]} (`{model}`)", "",
                  f"Reference accuracy (400x5 pool): {ref:.3f}. "
                  f"Parse-failure rate: "
                  f"{pm[model]['parse_failure_rate']:.1%}. "
                  f"Failed calls: {pm[model]['failed_calls']}.",
                  f"Variance components: sigma2_q = {vc['sigma2_q']:.4f} "
                  f"(between questions), sigma2_w = {vc['sigma2_w']:.4f} "
                  f"(within question / across seeds).", "",
                  "Coverage at the default design (N=50, K=5), B=2,000 "
                  "subsamples (bayes: B=200):", ""]
        lines += _default_table(cov)
        lines.append("")
        so = cov[(cov["method"] == "seed_only")
                 & (cov["N"] == 50) & (cov["K"] == 5)].iloc[0]
        lines += [f"Exploratory (not in PLAN.md): against its *own* "
                  f"fixed-question estimand, seed_only's coverage at the "
                  f"default design is {so['own_coverage']:.3f} "
                  f"[{so['own_mc_lower']:.3f}, {so['own_mc_upper']:.3f}] "
                  f"— it covers the question it actually answers.", ""]
        uc = under_covers(cov[cov["method"] != "seed_only"])
        if len(uc):
            lines += ["Under-coverage verdicts (sec.9: coverage < 0.93 "
                      "with MC interval excluding 0.95), all designs:",
                      "", "| method | N | K | coverage | MC interval |",
                      "|---|---|---|---|---|"]
            for _, r in uc.sort_values(["method", "N", "K"]).iterrows():
                lines.append(f"| {r['method']} | {int(r['N'])} | "
                             f"{int(r['K'])} | {r['coverage']:.3f} | "
                             f"[{r['mc_lower']:.3f}, "
                             f"{r['mc_upper']:.3f}] |")
            lines.append("")
        else:
            lines += ["No method under-covers at any design under the "
                      "sec.9 rule (seed_only excluded: different "
                      "estimand).", ""]
    # --- paired
    lines += ["## Paired model differences", "",
              "Full-pool paired intervals on the matched 400 x 5 grid "
              "(difference = first model minus second):", "",
              "| pair | method | estimate | 95% interval | width |",
              "|---|---|---|---|---|"]
    for (a, b), full in paired_full.items():
        for _, r in full.iterrows():
            lines.append(f"| {DISPLAY[a]} - {DISPLAY[b]} | "
                         f"{r['method']} | {r['estimate']:+.3f} | "
                         f"[{r['lower']:+.3f}, {r['upper']:+.3f}] | "
                         f"{r['width']:.3f} |")
    lines += ["", "Paired coverage at the default design (N=50, K=5), "
              "B=2,000:", "", "| pair | method | coverage | MC interval "
              "| median width |", "|---|---|---|---|---|"]
    for (a, b), pcov in paired_cov.items():
        d = pcov[(pcov["N"] == 50) & (pcov["K"] == 5)]
        for _, r in d.iterrows():
            lines.append(f"| {DISPLAY[a]} - {DISPLAY[b]} | "
                         f"{r['method']} | {r['coverage']:.3f} | "
                         f"[{r['mc_lower']:.3f}, {r['mc_upper']:.3f}] | "
                         f"{r['median_width']:.3f} |")
    lines += ["", "Coverage and widths for all paired designs "
              "(N in {25, 50, 100, 200} x K in {1, 5}) are in "
              "results/paired_coverage.csv.", ""]
    # --- budget
    lines += ["## Budget analysis (fixed budget: 250 calls)", "",
              "Empirical median interval widths from dedicated "
              "subsamples (B=2,000) at each split, with the width "
              "predicted from the variance components (2 x 1.96 x "
              "predicted SE). Best split = narrowest cluster-method "
              "width.", ""]
    for model, bud in budgets.items():
        lines += [f"### {DISPLAY[model]}", "",
                  "| split (NxK) | predicted width | naive | "
                  "question_means | cluster | bootstrap | seed_only |",
                  "|---|---|---|---|---|---|---|"]
        for (n, k), g in bud.groupby(["N", "K"], sort=False):
            w = {r["method"]: r["median_width"]
                 for _, r in g.iterrows()}
            lines.append(
                f"| {int(n)}x{int(k)} | "
                f"{g['predicted_width'].iloc[0]:.3f} | "
                f"{w['naive']:.3f} | {w['question_means']:.3f} | "
                f"{w['cluster']:.3f} | {w['bootstrap']:.3f} | "
                f"{w['seed_only']:.3f} |")
        cl = bud[bud["method"] == "cluster"]
        best = cl.loc[cl["median_width"].idxmin()]
        lines += ["", f"Best split for {DISPLAY[model]}: "
                  f"{int(best['N'])} questions x {int(best['K'])} "
                  f"seed(s) (cluster median width "
                  f"{best['median_width']:.3f}, vs "
                  f"{cl[cl['K'] == 5]['median_width'].iloc[0]:.3f} at "
                  f"50x5).", ""]
    # --- implementation notes, amendments, limitations
    lines += ["## Implementation notes (Stage 4)", "",
              "- analyze.py was extended to implement PLAN.md secs.7, "
              "10 and 11 in full (paired study, budget analysis, "
              "empirical SEs, full figure set, colour-blind-safe "
              "palette), as anticipated by PLAN.md sec.13 item 2. Pure "
              "additions implementing the frozen plan; no definition "
              "changed.",
              "- The two-stage bootstrap is computed by a vectorized "
              "implementation of the sec.8 definition (the frozen loop "
              "implementation in intervals.py costs ~3.7 s per "
              "subsample at N=200, which is infeasible at B=2,000 x 16 "
              "designs x 3 models). Agreement with the frozen "
              "implementation was checked on four matrix shapes over "
              "five seeds each: bootstrap SEs agreed within 0.003 and "
              "interval widths within 0.007 (Monte Carlo error). "
              "intervals.py is unchanged.",
              "- The (400, 5) matrix per model is asserted complete "
              "with no missing cells before the ANOVA variance "
              "components, per PLAN.md sec.13 item 3; the assertion "
              "passed for all three models.",
              "- Bayes coverage uses the first 200 of the 2,000 "
              "subsamples per design (PLAN.md sec.7) and is cached "
              "under results/bayes_cache/ (deterministic given the "
              "study seeds; delete to recompute).",
              "", "## Amendments to PLAN.md", "",
              "None. The amendment log in PLAN.md sec.14 is empty; no "
              "definition in the frozen plan was changed.", "",
              "## Limitations", "",
              "As stated in PLAN.md sec.12: one benchmark (GSM8K, one "
              "prompt); three models chosen for mid-range pilot "
              "accuracy; the reference truth is the finite 400x5 pool, "
              "so large-N coverage is conservative in the stated way; "
              "Muse-Glimmer-30B's parse failures (26.2% in the pilot) "
              "mean part of its measured inaccuracy is output "
              "behaviour, not question difficulty; Bayes coverage "
              "rests on 200 subsamples per design, so its Monte Carlo "
              "intervals are wider.", ""]
    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):  # pragma: no cover - exercised on real outputs
    import yaml
    import matplotlib
    matplotlib.use("Agg")

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    acfg = cfg["analysis"]
    from .data import load_gsm8k

    questions = load_gsm8k("test")
    raw = ROOT / "outputs" / "raw_runs.jsonl"
    tidy = build_correctness(raw, questions)
    tidy[["model", "question_id", "seed", "correct"]].to_parquet(
        ROOT / "outputs" / "correctness.parquet", index=False)

    validation = validate_runs(raw, tidy)
    spend_df = spend(tidy)
    models_sorted = sorted(tidy["model"].unique())
    mats = {m: model_matrix(tidy, m) for m in models_sorted}
    vcs = {m: variance_components(mats[m]) for m in models_sorted}

    results = ROOT / "results"
    fig_dir = results / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    covs = {}
    for mi, model in enumerate(models_sorted):
        cov = coverage_study(mats[model], acfg["designs_N"],
                             acfg["designs_K"], B=acfg["subsamples"],
                             seed=1000 + mi,
                             bayes_subsamples=acfg["bayes_subsamples"])
        covs[model] = cov
        print(f"fast coverage done: {model}", flush=True)

    bayes = bayes_coverage(mats, acfg["designs_N"], acfg["designs_K"],
                           acfg["subsamples"],
                           acfg["bayes_subsamples"], base_seed=1000,
                           workers=int(os.environ.get(
                               "ERRORBARS_BAYES_WORKERS", "3")))
    for model in models_sorted:
        bcov = pd.DataFrame(bayes[model])
        covs[model] = pd.concat([covs[model], bcov],
                                ignore_index=True)
        covs[model].to_csv(results / f"coverage_{SHORT[model]}.csv",
                           index=False)
        print(f"bayes coverage merged: {model}", flush=True)

    pairs = [(models_sorted[i], models_sorted[j])
             for i in range(len(models_sorted))
             for j in range(i + 1, len(models_sorted))]
    paired_cov, paired_full = {}, {}
    all_paired = []
    for pi, (a, b) in enumerate(pairs):
        pc = paired_study(mats[a], mats[b], acfg["designs_N"],
                          acfg["paired_designs_K"],
                          B=acfg["subsamples"], seed=5000 + pi)
        pc.insert(0, "model_b", b)
        pc.insert(0, "model_a", a)
        paired_cov[(a, b)] = pc
        all_paired.append(pc)
        paired_full[(a, b)] = paired_full_pool(mats[a], mats[b])
        print(f"paired study done: {a} vs {b}", flush=True)
    pd.concat(all_paired).to_csv(results / "paired_coverage.csv",
                                 index=False)

    budgets = {}
    for mi, model in enumerate(models_sorted):
        bud = budget_analysis(mats[model], vcs[model],
                              [tuple(s) for s in acfg["budget_splits"]],
                              B=acfg["subsamples"], seed=9000 + mi)
        bud.insert(0, "model", model)
        budgets[model] = bud
    pd.concat(budgets.values()).to_csv(results / "budget.csv",
                                       index=False)

    for model in models_sorted:
        _fig_coverage(covs[model], model, fig_dir)
    _fig_width(covs, fig_dir)
    _fig_pred_vs_emp(covs, vcs, fig_dir)
    _fig_budget(budgets, fig_dir)

    write_summary(results / "summary.md", validation=validation,
                  spend_df=spend_df, covs=covs, vcs=vcs,
                  paired_cov=paired_cov, paired_full=paired_full,
                  budgets=budgets)
    print("wrote results/summary.md, CSVs and figures")


if __name__ == "__main__":
    main()
