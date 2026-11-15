"""The page's calculator (docs/evalbar.js) must agree with the Python package.

Runs the JavaScript with node on random matrices and compares it with
errorbars.intervals (cluster, naive, paired) and analyze.variance_components.
Skipped when node is not installed.
"""
import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy import stats

from errorbars.analyze import variance_components
from errorbars.intervals import intervals, paired_intervals

JS = Path(__file__).resolve().parents[1] / "docs" / "evalbar.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def run_js(body):
    code = f"const E = require({json.dumps(str(JS))});\n{body}"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def as_text(mat):
    return "\n".join(" ".join(str(int(v)) for v in row) for row in mat)


@pytest.mark.parametrize("seed,n,k", [(0, 50, 5), (1, 25, 3), (2, 200, 2), (3, 40, 1)])
def test_single_model_matches_python(seed, n, k):
    rng = np.random.default_rng(seed)
    mat = (rng.random((n, k)) < rng.beta(2, 2, n)[:, None]).astype(float)
    js = run_js(f"""const r = E.parse({json.dumps(as_text(mat))}).rows;
console.log(JSON.stringify({{c: E.cluster(r), n: E.naive(r), v: E.components(r)}}));""")
    py = intervals(mat, methods=["cluster", "naive"])
    assert js["c"]["est"] == pytest.approx(py["cluster"]["estimate"], abs=1e-12)
    assert js["c"]["lo"] == pytest.approx(py["cluster"]["lower"], abs=2e-4)
    assert js["c"]["hi"] == pytest.approx(py["cluster"]["upper"], abs=2e-4)
    assert js["n"]["lo"] == pytest.approx(py["naive"]["lower"], abs=1e-6)
    if k >= 2:
        vc = variance_components(mat)
        assert js["v"]["sigma2_q"] == pytest.approx(vc["sigma2_q"], abs=1e-10)
        assert js["v"]["sigma2_w"] == pytest.approx(vc["sigma2_w"], abs=1e-10)


def test_paired_matches_python():
    rng = np.random.default_rng(7)
    d = rng.beta(2, 2, 80)
    a = (rng.random((80, 3)) < d[:, None]).astype(float)
    b = (rng.random((80, 3)) < np.clip(d + 0.05, 0, 1)[:, None]).astype(float)
    js = run_js(f"""const A = E.parse({json.dumps(as_text(a))}).rows, B = E.parse({json.dumps(as_text(b))}).rows;
console.log(JSON.stringify(E.paired(A, B)));""")
    py = paired_intervals(b, a, methods=["paired_cluster"])["paired_cluster"]
    assert js["diff"] == pytest.approx(py["estimate"], abs=1e-12)
    assert js["lo"] == pytest.approx(py["lower"], abs=2e-4)


def test_t_quantiles():
    js = run_js("console.log(JSON.stringify([1,2,3,5,10,30,100].map(d => E.tq(0.975, d))));")
    for d, v in zip([1, 2, 3, 5, 10, 30, 100], js):
        assert v == pytest.approx(stats.t.ppf(0.975, d), rel=2e-3)


def test_parse_formats():
    js = run_js(r"""console.log(JSON.stringify(E.parse("question,run1,run2\nq1,1,0\nq2 pass pass\n3/5\n\n# note\nq4, true, false, true").rows));""")
    assert js == [{"c": 1, "k": 2}, {"c": 2, "k": 2}, {"c": 3, "k": 5}, {"c": 2, "k": 3}]
