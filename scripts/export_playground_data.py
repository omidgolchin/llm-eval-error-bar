"""Export the Stage 4 results into docs/data/results.json for the playground.

Everything in the JSON comes from the committed Stage 4 outputs:

* coverage rows  <- results/coverage_{qwen,inkling,glimmer}.csv
* budget rows    <- results/budget.csv
* per-model reference accuracy <- the `reference` column of the coverage CSVs
* parse-failure rates, failed-call counts and variance components
                 <- parsed out of results/summary.md (the human summary of
                    the same run; the numbers are not re-derived here)

The under-coverage flag applies PLAN.md sec.9 exactly: coverage < 0.93
with the Monte Carlo 95% interval lying entirely below 0.95.

Run from the repo root:  .venv/bin/python scripts/export_playground_data.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

MODELS = [
    ("qwen", "arize-ai/qwen-2-1.5b-instruct", "Qwen-2-1.5B-Instruct"),
    ("inkling", "thinkingmachines/Inkling", "Inkling"),
    ("glimmer", "meta-models/Muse-Glimmer-30B", "Muse-Glimmer-30B"),
]

METHODS = [
    ("naive", "Naive — pooled Wilson",
     "All N x K answers treated as independent Bernoulli trials."),
    ("question_means", "Question means + t",
     "Per-question mean accuracy, t-interval over the N question means."),
    ("cluster", "Cluster-robust by question",
     "Pooled mean with a cluster-robust (sandwich) standard error by "
     "question and a t critical value."),
    ("bootstrap", "Two-stage bootstrap",
     "Resample questions, then seeds within each question; percentile "
     "interval over 2,000 draws."),
    ("bayes", "Hierarchical Bayesian",
     "Logistic model with a question random effect (NumPyro NUTS); "
     "coverage measured on 200 subsamples per design, not 2,000."),
    ("seed_only", "Seed-only (different estimand)",
     "Questions treated as fixed: this interval is for accuracy on "
     "these questions only, not for new questions."),
]


def under_covers(coverage: float, mc_upper: float) -> bool:
    """PLAN.md sec.9 decision rule."""
    return bool(coverage < 0.93 and mc_upper < 0.95)


def model_metadata(summary_text: str, model_id: str) -> dict:
    """Pull parse-failure rate, failed calls and variance components for
    one model out of results/summary.md."""
    # Section header: ## Display (`model/id`) ... body until the next ##.
    pat = re.compile(
        r"## [^\n]*\(`" + re.escape(model_id) + r"`\)\n(.*?)(?=\n## |\Z)",
        re.S)
    m = pat.search(summary_text)
    if not m:
        raise ValueError(f"summary.md section not found for {model_id}")
    body = m.group(1)
    pf = re.search(r"Parse-failure rate: ([\d.]+)%", body)
    fc = re.search(r"Failed calls: (\d+)", body)
    vc = re.search(r"sigma2_q = ([\d.]+).*?sigma2_w = ([\d.]+)", body)
    if not (pf and fc and vc):
        raise ValueError(f"metadata incomplete for {model_id}")
    return {
        "parse_fail_pct": float(pf.group(1)),
        "failed_calls": int(fc.group(1)),
        "sigma2_q": float(vc.group(1)),
        "sigma2_w": float(vc.group(2)),
    }


def r4(x) -> float:
    return round(float(x), 4)


def main() -> None:
    summary_text = (ROOT / "results" / "summary.md").read_text()

    models, coverage = [], []
    for slug, model_id, display in MODELS:
        cov = pd.read_csv(ROOT / "results" / f"coverage_{slug}.csv")
        meta = model_metadata(summary_text, model_id)
        models.append({
            "slug": slug, "id": model_id, "name": display,
            "reference": r4(cov["reference"].iloc[0]), **meta,
        })
        for row in cov.itertuples():
            coverage.append({
                "model": slug, "method": row.method,
                "N": int(row.N), "K": int(row.K), "B": int(row.B),
                "coverage": r4(row.coverage),
                "mc_lower": r4(row.mc_lower), "mc_upper": r4(row.mc_upper),
                "median_width": r4(row.median_width),
                "under_covers": under_covers(row.coverage, row.mc_upper),
            })

    budget = []
    bud = pd.read_csv(ROOT / "results" / "budget.csv")
    slug_of = {mid: slug for slug, mid, _ in MODELS}
    for row in bud.itertuples():
        budget.append({
            "model": slug_of[row.model], "method": row.method,
            "N": int(row.N), "K": int(row.K), "calls": int(row.calls),
            "median_width": r4(row.median_width),
            "predicted_width": r4(row.predicted_width),
        })

    out = {
        "nominal": 0.95,
        "default_design": {"N": 50, "K": 5},
        "budget_calls": 250,
        "models": models,
        "methods": [{"id": mid, "name": name, "note": note}
                    for mid, name, note in METHODS],
        "coverage": coverage,
        "budget": budget,
    }
    dest = ROOT / "docs" / "data" / "results.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {dest}: {len(coverage)} coverage rows, "
          f"{len(budget)} budget rows, {len(models)} models")


if __name__ == "__main__":
    main()
