"""Compute the pilot-2 table exactly as pilot_summary.md did for pilot 1."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from errorbars.analyze import build_correctness  # noqa: E402
from errorbars.data import load_gsm8k  # noqa: E402

RAW = ROOT / "outputs" / "pilot2_runs.jsonl"
MODELS_JSON = "/tmp/models_fresh2.json"

questions = load_gsm8k("test")
corr = build_correctness(RAW, questions)

raw_rows = [json.loads(l) for l in RAW.read_text().splitlines() if l.strip()]
pricing = {m["id"]: (m.get("pricing") or {}) for m in json.loads(Path(MODELS_JSON).read_text())}

import collections
raw_by_model = collections.defaultdict(list)
for r in raw_rows:
    raw_by_model[r["model"]].append(r)

out = {}
for model, df in corr.groupby("model"):
    rows = raw_by_model[model]
    n = len(df)
    acc = float(df["correct"].mean())
    parse_fail = float(1 - df["parsed"].mean())
    mean_prompt = sum(r["prompt_tokens"] or 0 for r in rows) / len(rows)
    mean_comp = sum(r["completion_tokens"] or 0 for r in rows) / len(rows)
    finishes = collections.Counter(r["finish_reason"] for r in rows)
    errors = sum(1 for r in rows if r.get("error"))
    p = pricing.get(model, {})
    pin, pout = float(p.get("input") or 0), float(p.get("output") or 0)
    cost_call = (mean_prompt * pin + mean_comp * pout) / 1e6
    out[model] = {
        "n": n, "accuracy": acc, "correct": int(df["correct"].sum()),
        "parse_fail_rate": parse_fail,
        "parse_fail_n": int((~df["parsed"]).sum()),
        "mean_prompt_tokens": round(mean_prompt, 1),
        "mean_completion_tokens": round(mean_comp, 1),
        "finish_stop": finishes.get("stop", 0),
        "finish_length": finishes.get("length", 0),
        "finish_other": {k: v for k, v in finishes.items() if k not in ("stop", "length")},
        "error_rows": errors,
        "pricing_input": pin, "pricing_output": pout,
        "cost_per_call": cost_call,
        "projected_main_2000": cost_call * 2000,
        "in_band_45_85": bool(0.45 <= acc <= 0.85),
    }

print(json.dumps(out, indent=1))
Path(ROOT / "results" / "pilot2_table.json").write_text(json.dumps(out, indent=1))
total_cost = sum(v["cost_per_call"] * v["n"] for v in out.values())
print("TOTAL PILOT2 SPEND:", round(total_cost, 4), "rows:", len(raw_rows))
