"""Export the sample inputs for the page's "My eval" mode from the saved runs.

Writes docs/data/examples.json: per-question rows of 0/1 answers taken from
outputs/correctness.parquet (real GSM8K runs), so every example on the page
is real data. Run: python scripts/export_examples.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
df = pd.read_parquet(ROOT / "outputs" / "correctness.parquet")
names = {"arize-ai/qwen-2-1.5b-instruct": "Qwen-2-1.5B-Instruct",
         "thinkingmachines/Inkling": "Inkling",
         "meta-models/Muse-Glimmer-30B": "Muse-Glimmer-30B"}
mats = {names[m]: g.pivot_table(index="question_id", columns="seed", values="correct", aggfunc="first")
        for m, g in df.groupby("model")}
qs = sorted(set.intersection(*[set(m.index) for m in mats.values()]))


def rows(model, n, k):
    m = mats[model].loc[qs[:n]].iloc[:, :k]
    return "\n".join(" ".join(str(int(v)) for v in r) for r in m.to_numpy())


examples = [
    {"label": "One model, 100 questions × 5 runs (real GSM8K runs)",
     "a": rows("Qwen-2-1.5B-Instruct", 100, 5), "b": "", "nameA": "Qwen-2-1.5B-Instruct", "nameB": ""},
    {"label": "Compare two models on the same 100 questions",
     "a": rows("Qwen-2-1.5B-Instruct", 100, 3), "b": rows("Inkling", 100, 3),
     "nameA": "Qwen-2-1.5B-Instruct", "nameB": "Inkling"},
    {"label": "One run per question, 200 questions",
     "a": rows("Muse-Glimmer-30B", 200, 1), "b": "", "nameA": "Muse-Glimmer-30B", "nameB": ""},
]
out = ROOT / "docs" / "data" / "examples.json"
out.write_text(json.dumps(examples, indent=0) + "\n")
print(out, [e["label"] for e in examples])
