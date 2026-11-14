"""Run models on questions x seeds via Together AI (OpenAI-compatible).

Design rules from the plan:
* The API key comes from the TOGETHER_API_KEY environment variable (a local
  .env file is allowed; it is git-ignored). It is never printed or logged.
* Runs are resumable: a run's ID is (model, question_id, seed); IDs already
  present in the output file are skipped.
* Each call gets up to 3 attempts with exponential backoff. A call that
  fails all attempts is recorded with an error and, per the plan, grades
  as incorrect downstream; the count is reported.
* --dry-run writes placeholder rows to outputs/dry_run.jsonl only, never
  to the real file. A real run refuses to start if the real output file
  contains placeholder rows.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import pandas as pd

BASE_URL = "https://api.together.xyz/v1"
ROOT = Path(__file__).resolve().parents[2]


def _surrogate_key() -> str | None:
    """Fallback for running inside Muse: fetch a credential surrogate for
    the connected Together account. The surrogate is not the real key;
    Muse's egress layer swaps in the real key for api.together.xyz.
    Returns None when that machinery is not present (e.g. a plain local
    checkout), in which case TOGETHER_API_KEY must be set instead."""
    import sys

    bin_dir = "/opt/muse/skills/custom-connector-setup/bin"
    try:
        if bin_dir not in sys.path:
            sys.path.insert(0, bin_dir)
        from dynamic_credentials import dynamic_credential_entry

        entry = dynamic_credential_entry("custom.together", "access_token")
        return str(entry["surrogate"])
    except Exception:
        return None


def get_client():
    from dotenv import load_dotenv
    from openai import OpenAI

    load_dotenv(ROOT / ".env")
    key = os.environ.get("TOGETHER_API_KEY") or _surrogate_key()
    if not key:
        raise RuntimeError("TOGETHER_API_KEY is not set in the environment "
                           "or in a .env file at the repo root, and no "
                           "connected Together account was found.")
    return OpenAI(api_key=key, base_url=BASE_URL)


def list_models(client) -> list[str]:
    return sorted(m.id for m in client.models.list().data)


def _run_id(model: str, question_id: str, seed: int) -> str:
    return f"{model}|{question_id}|{seed}"


def _existing_ids(path: Path) -> set[str]:
    ids = set()
    if path.exists():
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("dry_run"):
                    raise RuntimeError(
                        f"{path} contains dry-run placeholder rows. "
                        "Move or delete it before starting a real run.")
                ids.add(row["run_id"])
    return ids


def _one_call(client, model, prompt_text, seed, temperature, top_p,
              max_tokens):
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        seed=seed,
    )
    choice = resp.choices[0]
    usage = resp.usage
    return {
        "model_returned": resp.model,
        "text": choice.message.content or "",
        "finish_reason": choice.finish_reason,
        "prompt_tokens": usage.prompt_tokens if usage else None,
        "completion_tokens": usage.completion_tokens if usage else None,
    }


def run_grid(models, questions: pd.DataFrame, seeds, prompt_template: str,
             out_path: Path, dry_run: bool = False, temperature: float = 0.7,
             top_p: float = 1.0, max_tokens: int = 512,
             shuffle_seed: int = 0, client=None) -> dict:
    """Run (model, question, seed) cells; returns a small summary dict."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        done: set[str] = set()
        if out_path.exists():
            with out_path.open() as f:
                done = {json.loads(l)["run_id"] for l in f if l.strip()}
    else:
        done = _existing_ids(out_path)

    jobs = []
    for model in models:
        for _, q in questions.iterrows():
            for s in seeds:
                rid = _run_id(model, q["question_id"], int(s))
                if rid not in done:
                    jobs.append((model, q, int(s), rid))
    random.Random(shuffle_seed).shuffle(jobs)

    if not dry_run and client is None:
        client = get_client()

    n_new, n_failed = 0, 0
    with out_path.open("a") as f:
        for model, q, s, rid in jobs:
            row = {
                "run_id": rid, "model": model,
                "question_id": q["question_id"], "seed": s,
            }
            if dry_run:
                row.update({"model_returned": model, "text": "",
                            "finish_reason": "dry_run",
                            "prompt_tokens": 0, "completion_tokens": 0,
                            "dry_run": True, "error": None})
            else:
                prompt_text = prompt_template.replace("{question}",
                                                      q["question"])
                result, error = None, None
                for attempt in range(3):
                    try:
                        result = _one_call(client, model, prompt_text, s,
                                           temperature, top_p, max_tokens)
                        break
                    except Exception as e:  # noqa: BLE001 - record & retry
                        error = f"{type(e).__name__}: {e}"
                        # A credential surrogate can expire mid-run; on an
                        # auth rejection, rebuild the client (fresh
                        # surrogate) before the next attempt.
                        if "401" in error or "AuthenticationError" in error:
                            try:
                                client = get_client()
                            except Exception:
                                pass
                        if attempt < 2:
                            time.sleep(2 ** attempt * 2)
                if result is None:
                    n_failed += 1
                    row.update({"model_returned": None, "text": "",
                                "finish_reason": "error",
                                "prompt_tokens": None,
                                "completion_tokens": None,
                                "dry_run": False, "error": error})
                else:
                    row.update({**result, "dry_run": False, "error": None})
            f.write(json.dumps(row) + "\n")
            f.flush()
            n_new += 1
    return {"attempted": len(jobs), "written": n_new, "failed": n_failed,
            "skipped_existing": len(done)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--n-questions", type=int, default=40)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1])
    ap.add_argument("--question-seed", type=int, default=20261112)
    ap.add_argument("--limit-questions-from-pool", action="store_true",
                    help="sample from the frozen 400-question pool instead "
                         "of the full test split")
    ap.add_argument("--out", default=str(ROOT / "outputs" / "raw_runs.jsonl"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    from .data import load_gsm8k, sample_questions
    import yaml

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
    questions = load_gsm8k("test")
    if args.limit_questions_from_pool:
        questions = sample_questions(questions, cfg["benchmark"]["pool_size"],
                                     cfg["benchmark"]["pool_seed"])
    questions = sample_questions(questions, args.n_questions,
                                 args.question_seed)
    prompt_template = (ROOT / cfg["sampling"]["prompt_file"]).read_text()
    out = (ROOT / "outputs" / "dry_run.jsonl") if args.dry_run else Path(args.out)
    summary = run_grid(args.models, questions, args.seeds, prompt_template,
                       out, dry_run=args.dry_run,
                       temperature=cfg["sampling"]["temperature"],
                       top_p=cfg["sampling"]["top_p"],
                       max_tokens=cfg["sampling"]["max_tokens"],
                       shuffle_seed=args.question_seed)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
