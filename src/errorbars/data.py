"""Load GSM8K and sample questions deterministically."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .grade import parse_gold


def load_gsm8k(split: str = "test") -> pd.DataFrame:
    """Return a DataFrame with question_id, question, gold for the split."""
    from datasets import load_dataset

    ds = load_dataset("openai/gsm8k", "main", split=split)
    df = pd.DataFrame({
        "question_id": [f"gsm8k-{split}-{i}" for i in range(len(ds))],
        "question": ds["question"],
        "gold": [parse_gold(a) for a in ds["answer"]],
    })
    return df


def sample_questions(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    """Sample n questions without replacement, with a fixed seed."""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(df), size=n, replace=False)
    return df.iloc[np.sort(idx)].reset_index(drop=True)
