"""Interval methods for repeated-run LLM evaluations.

The reusable entry points are :func:`intervals` and :func:`paired_intervals`.

Input ``table`` is either

* a pandas DataFrame with columns ``question_id``, ``seed``, ``correct``
  (``correct`` in {0, 1}), or
* a 2-D array-like of shape (N, K) with one row per question and one column
  per seed. NaN is allowed for missing cells.

Every method returns a dict with keys: ``estimate``, ``lower``, ``upper``,
``se`` (where defined, else None), ``n_questions``, ``n_seeds`` (mean number
of observed seeds per question), and ``note`` — a string stating what the
interval targets. Read the notes: ``seed_only`` answers a different question
from the others.

Methods
-------
naive           All N*K answers treated as independent; Wilson interval on
                the pooled proportion.
question_means  Average each question over its seeds, then a t interval
                (df = N-1) over the N question means.
cluster         Pooled mean with a cluster-robust (by question) standard
                error, small-sample correction N/(N-1), t critical value
                with N-1 degrees of freedom.
bootstrap       Two-stage bootstrap: resample questions with replacement,
                then seeds within each question with replacement;
                percentile interval.
bayes           Hierarchical Bayesian logistic model with a question random
                effect (NumPyro, lazy-imported so the base install is light).
                The target is the population accuracy
                E[logit^-1(mu + u)], u ~ Normal(0, sigma).
seed_only       Treats the N questions as fixed: an interval for accuracy
                on *these* questions only. Different estimand.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

__all__ = ["intervals", "paired_intervals", "DEFAULT_METHODS"]

DEFAULT_METHODS = ("naive", "question_means", "cluster", "bootstrap", "bayes")

_NOTES = {
    "naive": "Targets population accuracy but treats every answer as "
             "independent; too narrow when questions differ in difficulty.",
    "question_means": "Targets the population accuracy over questions like "
                      "these, averaged over sampling randomness.",
    "cluster": "Targets the population accuracy over questions like these, "
               "averaged over sampling randomness (cluster-robust SE by "
               "question, t critical value, df = N-1).",
    "bootstrap": "Targets the population accuracy over questions like these, "
                 "averaged over sampling randomness (two-stage bootstrap).",
    "bayes": "Targets the population accuracy E[logit^-1(mu + u)] under a "
             "hierarchical logistic model with a question random effect; "
             "95% credible interval.",
    "seed_only": "Targets accuracy on THESE N questions only (questions "
                 "treated as fixed). Different estimand: says nothing about "
                 "new questions.",
    "paired_naive": "Targets the population accuracy difference, but treats "
                    "the two models' answers as independent samples.",
    "paired_cluster": "Targets the population accuracy difference between "
                      "the two models on the same questions (paired "
                      "per-question differences, cluster-robust SE, t "
                      "critical value, df = N-1).",
    "paired_bootstrap": "Targets the population accuracy difference between "
                        "the two models on the same questions (paired "
                        "two-stage bootstrap).",
}


# --------------------------------------------------------------------------
# input handling
# --------------------------------------------------------------------------

def _as_matrix(table) -> np.ndarray:
    """Return a float array of shape (N, K); NaN marks missing cells."""
    if hasattr(table, "columns"):  # pandas DataFrame
        cols = {"question_id", "seed", "correct"}
        if not cols.issubset(set(table.columns)):
            raise ValueError(
                f"DataFrame must have columns {sorted(cols)}; "
                f"got {list(table.columns)}")
        pivot = table.pivot_table(index="question_id", columns="seed",
                                  values="correct", aggfunc="first")
        return pivot.to_numpy(dtype=float)
    arr = np.asarray(table, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"array input must be 2-D (N, K); got shape {arr.shape}")
    return arr


def _z_or_t(level: float, df: int | None) -> float:
    alpha = 1.0 - level
    if df is None:
        return float(stats.norm.ppf(1 - alpha / 2))
    return float(stats.t.ppf(1 - alpha / 2, df))


def _result(estimate, lower, upper, se, mat, method):
    n_q = mat.shape[0]
    n_seeds = float(np.mean(np.sum(~np.isnan(mat), axis=1))) if n_q else 0.0
    return {
        "estimate": float(estimate),
        "lower": float(lower),
        "upper": float(upper),
        "se": None if se is None else float(se),
        "n_questions": int(n_q),
        "n_seeds": n_seeds,
        "note": _NOTES[method],
    }


# --------------------------------------------------------------------------
# single-model methods
# --------------------------------------------------------------------------

def _naive(mat, level):
    vals = mat[~np.isnan(mat)]
    n = vals.size
    p = vals.mean()
    z = _z_or_t(level, None)
    # Wilson score interval
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z / denom) * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    se = np.sqrt(p * (1 - p) / n)
    return _result(p, centre - half, centre + half, se, mat, "naive")


def _question_means(mat, level):
    means = np.nanmean(mat, axis=1)
    n = means.size
    est = means.mean()
    se = means.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0
    crit = _z_or_t(level, n - 1)
    return _result(est, est - crit * se, est + crit * se, se, mat,
                   "question_means")


def _cluster_se(mat, est):
    """Cluster-robust SE of the pooled mean, clusters = questions."""
    n_q = mat.shape[0]
    total = np.sum(~np.isnan(mat))
    resid = mat - est  # NaN stays NaN
    u = np.nansum(resid, axis=1)  # per-cluster score sums
    var = (n_q / (n_q - 1)) * np.sum(u**2) / total**2 if n_q > 1 else 0.0
    return float(np.sqrt(var))


def _cluster(mat, level):
    vals = mat[~np.isnan(mat)]
    est = vals.mean()
    se = _cluster_se(mat, est)
    crit = _z_or_t(level, mat.shape[0] - 1)
    return _result(est, est - crit * se, est + crit * se, se, mat, "cluster")


def _bootstrap(mat, level, seed, draws=2000):
    rng = np.random.default_rng(seed)
    n_q = mat.shape[0]
    rows = [row[~np.isnan(row)] for row in mat]
    stats_bs = np.empty(draws)
    for b in range(draws):
        idx = rng.integers(0, n_q, size=n_q)
        total, count = 0.0, 0
        for i in idx:
            r = rows[i]
            take = r[rng.integers(0, r.size, size=r.size)]
            total += take.sum()
            count += take.size
        stats_bs[b] = total / count
    alpha = 1 - level
    lo, hi = np.quantile(stats_bs, [alpha / 2, 1 - alpha / 2])
    est = float(np.nanmean(mat))
    return _result(est, lo, hi, float(stats_bs.std(ddof=1)), mat, "bootstrap")


def _seed_only(mat, level):
    n_q, _ = mat.shape
    p_q = np.nanmean(mat, axis=1)
    k_q = np.sum(~np.isnan(mat), axis=1)
    est = p_q.mean()
    var = np.sum(p_q * (1 - p_q) / k_q) / n_q**2
    se = float(np.sqrt(var))
    crit = _z_or_t(level, None)
    return _result(est, est - crit * se, est + crit * se, se, mat, "seed_only")


def _bayes(mat, level, seed, draws_warmup=500, draws_sample=1000):
    """Hierarchical logistic model via NumPyro (lazy import)."""
    try:
        import jax
        import jax.numpy as jnp
        import numpyro
        import numpyro.distributions as dist
        from numpyro.infer import MCMC, NUTS, Predictive
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "The 'bayes' method needs numpyro and jax: "
            "pip install numpyro jax") from e

    n_q, _ = mat.shape
    k_q = np.sum(~np.isnan(mat), axis=1).astype(int)
    y_q = np.nansum(mat, axis=1).astype(int)

    def model(k, y=None):
        mu = numpyro.sample("mu", dist.Normal(0.0, 1.5))
        sigma = numpyro.sample("sigma", dist.HalfNormal(1.5))
        with numpyro.plate("questions", n_q):
            u = numpyro.sample("u", dist.Normal(0.0, sigma))
            numpyro.sample("obs", dist.Binomial(total_count=k,
                                                logits=mu + u), obs=y)

    mcmc = MCMC(NUTS(model), num_warmup=draws_warmup,
                num_samples=draws_sample, progress_bar=False)
    mcmc.run(jax.random.PRNGKey(seed), k=jnp.asarray(k_q), y=jnp.asarray(y_q))
    post = mcmc.get_samples()
    mu = np.asarray(post["mu"])
    sigma = np.asarray(post["sigma"])
    # Population accuracy per posterior draw: E[logit^-1(mu + u)] for
    # u ~ Normal(0, sigma), estimated by Gauss-Hermite quadrature.
    nodes, weights = np.polynomial.hermite_e.hermegauss(32)
    vals = []
    for m, s in zip(mu, sigma):
        p = 1.0 / (1.0 + np.exp(-(m + s * nodes)))
        vals.append(float(np.sum(weights * p) / np.sqrt(2 * np.pi)))
    vals = np.asarray(vals)
    alpha = 1 - level
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return _result(vals.mean(), lo, hi, vals.std(ddof=1), mat, "bayes")


_METHODS = {
    "naive": _naive,
    "question_means": _question_means,
    "cluster": _cluster,
    "seed_only": _seed_only,
}


def intervals(table, level: float = 0.95, methods=DEFAULT_METHODS,
              seed: int = 0, bootstrap_draws: int = 2000) -> dict:
    """Compute accuracy intervals for one model's repeated-run results.

    ``table``: DataFrame with columns question_id, seed, correct, or a 2-D
    (N, K) array (NaN allowed). Returns {method: result-dict}.
    """
    mat = _as_matrix(table)
    out = {}
    for m in methods:
        if m == "bootstrap":
            out[m] = _bootstrap(mat, level, seed, draws=bootstrap_draws)
        elif m == "bayes":
            out[m] = _bayes(mat, level, seed)
        elif m in _METHODS:
            out[m] = _METHODS[m](mat, level)
        else:
            raise ValueError(f"unknown method {m!r}; "
                             f"choose from {sorted(_METHODS) + ['bootstrap', 'bayes']}")
    return out


# --------------------------------------------------------------------------
# paired methods (two models, same questions and seeds)
# --------------------------------------------------------------------------

def _paired_matrix(table_a, table_b):
    if hasattr(table_a, "columns") and hasattr(table_b, "columns"):
        a = table_a.set_index(["question_id", "seed"])["correct"]
        b = table_b.set_index(["question_id", "seed"])["correct"]
        joined = a.to_frame("a").join(b.to_frame("b"), how="inner")
        # rebuild aligned matrices on the shared (question, seed) grid
        qa = joined.reset_index().pivot_table(index="question_id",
                                              columns="seed", values="a")
        qb = joined.reset_index().pivot_table(index="question_id",
                                              columns="seed", values="b")
        return qa.to_numpy(dtype=float), qb.to_numpy(dtype=float)
    ma = _as_matrix(table_a)
    mb = _as_matrix(table_b)
    if ma.shape != mb.shape:
        raise ValueError("paired array inputs must have the same shape")
    return ma, mb


def paired_intervals(table_a, table_b, level: float = 0.95,
                     methods=("naive", "paired_cluster", "paired_bootstrap"),
                     seed: int = 0, bootstrap_draws: int = 2000) -> dict:
    """Intervals for the accuracy difference (A - B) on matched runs."""
    ma, mb = _paired_matrix(table_a, table_b)
    both = ~np.isnan(ma) & ~np.isnan(mb)
    diff = np.where(both, ma - mb, np.nan)
    out = {}
    for m in methods:
        if m == "naive":
            va = ma[~np.isnan(ma)]
            vb = mb[~np.isnan(mb)]
            est = va.mean() - vb.mean()
            se = np.sqrt(va.var(ddof=1) / va.size + vb.var(ddof=1) / vb.size)
            crit = _z_or_t(level, None)
            out[m] = _result(est, est - crit * se, est + crit * se, se,
                             diff, "paired_naive")
        elif m == "paired_cluster":
            vals = diff[~np.isnan(diff)]
            est = vals.mean()
            se = _cluster_se(diff, est)
            crit = _z_or_t(level, diff.shape[0] - 1)
            out[m] = _result(est, est - crit * se, est + crit * se, se,
                             diff, "paired_cluster")
        elif m == "paired_bootstrap":
            res = _bootstrap(diff, level, seed, draws=bootstrap_draws)
            res["note"] = _NOTES["paired_bootstrap"]
            out[m] = res
        else:
            raise ValueError(f"unknown paired method {m!r}")
    return out
