"""Interval tests: known answers, edge behaviour, and a fast simulation."""

import numpy as np
import pandas as pd
import pytest

from errorbars.intervals import intervals, paired_intervals

FAST = ("naive", "question_means", "cluster", "bootstrap", "seed_only")


def test_all_correct_and_all_wrong():
    mat = np.ones((20, 3))
    res = intervals(mat, methods=FAST, seed=0)
    assert res["question_means"]["estimate"] == 1.0
    assert res["question_means"]["upper"] <= 1.0 + 1e-9
    mat0 = np.zeros((20, 3))
    res0 = intervals(mat0, methods=FAST, seed=0)
    assert res0["question_means"]["estimate"] == 0.0
    assert res0["question_means"]["lower"] >= -1e-9


def test_known_question_means_interval():
    # 4 questions, K=1, values 0,1,1,1 -> mean 0.75; sd(ddof=1)=0.5;
    # se = 0.25; t_{0.975,3} = 3.182 -> half width 0.796 (clipped at 1 below).
    mat = np.array([[0.0], [1.0], [1.0], [1.0]])
    r = intervals(mat, methods=("question_means",))["question_means"]
    assert r["estimate"] == pytest.approx(0.75)
    assert r["se"] == pytest.approx(0.25)
    assert r["lower"] == pytest.approx(0.75 - 3.182 * 0.25, abs=1e-3)
    assert r["upper"] == pytest.approx(0.75 + 3.182 * 0.25, abs=1e-3)


def test_naive_estimate_is_pooled_proportion():
    mat = np.array([[1, 0], [1, 1], [0, 0], [1, 0]], dtype=float)
    r = intervals(mat, methods=("naive",))["naive"]
    assert r["estimate"] == pytest.approx(4 / 8)
    assert r["n_questions"] == 4
    assert r["n_seeds"] == 2.0


def test_naive_and_cluster_agree_when_k1_identical_difficulty():
    # Every question has the same true difficulty; with K=1 the cluster
    # interval should nearly coincide with the naive interval.
    rng = np.random.default_rng(7)
    mat = (rng.random((200, 1)) < 0.6).astype(float)
    res = intervals(mat, methods=("naive", "cluster"), seed=0)
    assert abs(res["naive"]["lower"] - res["cluster"]["lower"]) < 0.03
    assert abs(res["naive"]["upper"] - res["cluster"]["upper"]) < 0.03


def test_cluster_wider_than_naive_when_difficulty_varies():
    # Half the questions are always right, half always wrong, K=5:
    # question difficulty dominates, so the naive interval is far too narrow.
    mat = np.vstack([np.ones((25, 5)), np.zeros((25, 5))])
    res = intervals(mat, methods=("naive", "cluster"), seed=0)
    w_naive = res["naive"]["upper"] - res["naive"]["lower"]
    w_cluster = res["cluster"]["upper"] - res["cluster"]["lower"]
    assert w_cluster > 2 * w_naive


def test_seed_only_is_narrower_and_labelled_different():
    rng = np.random.default_rng(3)
    p_q = rng.beta(2, 2, size=40)
    mat = (rng.random((40, 5)) < p_q[:, None]).astype(float)
    res = intervals(mat, methods=("cluster", "seed_only"), seed=0)
    w_cluster = res["cluster"]["upper"] - res["cluster"]["lower"]
    w_seed = res["seed_only"]["upper"] - res["seed_only"]["lower"]
    assert w_seed < w_cluster
    assert "THESE" in res["seed_only"]["note"]


def test_dataframe_input_matches_array_input():
    mat = np.array([[1, 0, 1], [0, 0, 1], [1, 1, 1], [0, 1, 0]], dtype=float)
    rows = [{"question_id": f"q{i}", "seed": j, "correct": int(mat[i, j])}
            for i in range(4) for j in range(3)]
    df = pd.DataFrame(rows)
    a = intervals(mat, methods=("cluster",), seed=0)["cluster"]
    b = intervals(df, methods=("cluster",), seed=0)["cluster"]
    assert a["estimate"] == pytest.approx(b["estimate"])
    assert a["lower"] == pytest.approx(b["lower"])


def test_nan_cells_are_ignored():
    mat = np.array([[1.0, np.nan], [0.0, 1.0], [1.0, 1.0], [0.0, 0.0]])
    r = intervals(mat, methods=("naive",))["naive"]
    assert r["estimate"] == pytest.approx(4 / 7)


def test_paired_identical_models_give_zero_difference():
    rng = np.random.default_rng(11)
    mat = (rng.random((30, 4)) < 0.7).astype(float)
    res = paired_intervals(mat, mat, seed=0)
    for m in ("naive", "paired_cluster"):
        assert res[m]["estimate"] == pytest.approx(0.0)
        assert res[m]["lower"] <= 0.0 <= res[m]["upper"]


def test_cluster_coverage_on_simulated_data():
    # Known truth: question probabilities drawn once from Beta(6, 4)
    # (mean 0.6). The cluster interval should cover near 95%.
    rng = np.random.default_rng(2026)
    truth_p = rng.beta(6, 4, size=400)
    truth = truth_p.mean()
    hits, draws = 0, 500
    for d in range(draws):
        qi = rng.choice(400, size=50, replace=False)
        mat = (rng.random((50, 5)) < truth_p[qi][:, None]).astype(float)
        r = intervals(mat, methods=("cluster",))["cluster"]
        hits += int(r["lower"] <= truth <= r["upper"])
    coverage = hits / draws
    assert 0.90 <= coverage <= 0.99, f"cluster coverage was {coverage:.3f}"
