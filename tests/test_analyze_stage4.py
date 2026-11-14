"""Tests for the Stage 4 additions in errorbars.analyze (PLAN.md sec.13.2)."""

import numpy as np
import pytest

from errorbars.analyze import (
    _iter_designs, bootstrap_fast, budget_analysis, paired_study,
    predicted_se, variance_components)
from errorbars.intervals import intervals


def _mat(n=30, k=4, seed=3):
    rng = np.random.default_rng(seed)
    p_q = rng.beta(2, 2, size=n)
    return (rng.random((n, k)) < p_q[:, None]).astype(float)


def test_bootstrap_fast_matches_frozen_definition():
    mat = _mat()
    lo_f, hi_f, se_f = bootstrap_fast(mat, seed=11, draws=1000)
    ses, widths = [], []
    for s in range(6):
        r = intervals(mat, methods=("bootstrap",), seed=100 + s,
                      bootstrap_draws=1000)["bootstrap"]
        ses.append(r["se"])
        widths.append(r["upper"] - r["lower"])
    assert abs(se_f - float(np.mean(ses))) < 0.02
    assert abs((hi_f - lo_f) - float(np.mean(widths))) < 0.05


def test_bootstrap_fast_nan_fallback():
    mat = _mat(12, 3)
    mat[0, 0] = np.nan
    lo, hi, se = bootstrap_fast(mat, seed=1, draws=200)
    assert lo <= hi and se > 0


def test_variance_components_hand_case():
    mat = np.array([[1.0, 1.0], [0.0, 0.0]])
    vc = variance_components(mat)
    assert vc["sigma2_w"] == 0.0
    assert vc["sigma2_q"] == pytest.approx(0.5)


def test_predicted_se_formula():
    vc = {"sigma2_q": 0.04, "sigma2_w": 0.2}
    assert predicted_se(vc, 100, 5) == pytest.approx(
        np.sqrt(0.04 / 100 + 0.2 / 500))


def test_iter_designs_deterministic():
    mat = _mat(50, 5)
    d1 = next(iter(_iter_designs(mat, [25], [2], B=10, seed=5)))
    d2 = next(iter(_iter_designs(mat, [25], [2], B=10, seed=5)))
    assert np.array_equal(d1["subs"][0], d2["subs"][0])
    assert d1["seeds"]["cluster"] == d2["seeds"]["cluster"]
    assert d1["bayes_seeds"] == d2["bayes_seeds"]


def test_paired_study_smoke():
    rng = np.random.default_rng(0)
    a = (rng.random((60, 5)) < 0.6).astype(float)
    b = (rng.random((60, 5)) < 0.5).astype(float)
    df = paired_study(a, b, [20], [1, 5], B=40, seed=1)
    assert set(df["method"]) == {"naive", "paired_cluster",
                                 "paired_bootstrap"}
    assert df["coverage"].between(0, 1).all()
    assert df["reference"].iloc[0] == pytest.approx(a.mean() - b.mean())


def test_budget_analysis_smoke():
    mat = _mat(80, 5)
    vc = variance_components(mat)
    df = budget_analysis(mat, vc, [(20, 1), (10, 2)], B=40, seed=1)
    row = df[(df["N"] == 20) & (df["K"] == 1)
             & (df["method"] == "cluster")].iloc[0]
    assert row["predicted_width"] == pytest.approx(
        2 * 1.959964 * row["predicted_se"], abs=1e-4)
    assert row["median_width"] > 0
