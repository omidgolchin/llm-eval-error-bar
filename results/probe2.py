"""Phase 1 probe: one short chat call per chat/language catalog model.

Resumable: skips models already recorded in results/probe2_results.json.
Saves after every call. Stops immediately on a 429 / rate-limit response.
Uses the runner's client machinery (credential surrogate, rebuild on 401).
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from errorbars.run import get_client  # noqa: E402

MODELS_JSON = "/tmp/models_fresh.json"
OUT = ROOT / "results" / "probe2_results.json"
PROMPT = "What is 2+2? Give the final answer after '####'."

KNOWN_WORKING = {
    "together/Tev1-4B-experimental",
    "Qwen/Qwen3.5-9B",
    "deepseek-ai/DeepSeek-V4.1-Flash",
    "MiniMaxAI/MiniMax-M3.1-Flash",
    "moonshotai/Kimi-K3",
}

# Legacy / small models the spec cares about most — probe these first.
PRIORITY = [
    "meta-llama/Llama-3.2-1B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Llama-3.2-1B",
    "meta-llama/Llama-3.2-3B",
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3-8B-Instruct",
    "meta-llama/Llama-3-8b-chat-hf",
    "meta-llama/Meta-Llama-3.1-8B",
    "Qwen/Qwen2.5-7B-Instruct-Turbo",
    "Qwen/Qwen2.5-7B-Instruct",
    "Qwen/Qwen2.5-7B",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "mistralai/Mistral-7B-Instruct-v0.1",
    "mistralai/Mistral-7B-v0.1",
    "Qwen/Qwen2-1.5B-Instruct",
    "Qwen/Qwen2-1.5B",
    "Qwen/Qwen2.5-1.5B-Instruct",
    "Qwen/Qwen2.5-1.5B",
    "Qwen/Qwen2.5-3B-Instruct",
    "google/gemma-2-9b-it",
    "google/gemma-2-27b-it",
    "google/gemma-2b-it",
    "google/gemma-3-1b-it",
    "google/gemma-3-4b-it",
    "google/gemma-3-27b-it",
    "meta-llama/Llama-2-7b-chat-hf",
]


def load_existing():
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text())
            return {r["id"]: r for r in data}
        except Exception:
            return {}
    return {}


def save(results_by_id, order):
    rows = [results_by_id[m] for m in order if m in results_by_id]
    OUT.write_text(json.dumps(rows, indent=1))


def main():
    catalog = json.loads(Path(MODELS_JSON).read_text())
    cand = [m for m in catalog
            if m.get("type") in ("chat", "language")
            and m.get("id") not in KNOWN_WORKING]
    ids = [m["id"] for m in cand]
    order = [m for m in PRIORITY if m in ids] + [m for m in ids if m not in PRIORITY]

    results = load_existing()
    todo = [m for m in order if m not in results]
    print(f"catalog candidates: {len(order)}; already probed: {len(results)}; todo: {len(todo)}", flush=True)

    client = get_client()
    rate_limited = False
    for i, model in enumerate(todo, 1):
        rec = {"id": model}
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": PROMPT}],
                temperature=0.7, max_tokens=64, seed=0, timeout=60,
            )
            choice = resp.choices[0]
            text = choice.message.content or ""
            rec.update({
                "status": "works",
                "finish_reason": choice.finish_reason,
                "completion_tokens": resp.usage.completion_tokens if resp.usage else None,
                "prompt_tokens": resp.usage.prompt_tokens if resp.usage else None,
                "text_preview": text[:120],
                "empty_or_fragment": bool(
                    len(text.strip()) < 20
                    or (resp.usage and resp.usage.completion_tokens is not None
                        and resp.usage.completion_tokens <= 10)
                ),
                "error": None,
            })
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            low = err.lower()
            if "429" in err or "rate_limit" in low or "rate limit" in low or "ratelimit" in low:
                rec.update({"status": "rate_limited", "error": err[:300]})
                results[model] = rec
                save(results, order)
                print(f"RATE LIMITED at {model}; stopping.", flush=True)
                rate_limited = True
                break
            if "non-serverless" in low or "unable to access" in low:
                status = "non-serverless"
            else:
                status = "other-error"
                # one client rebuild + retry only for auth failures
                if "401" in err or "authenticationerror" in low:
                    try:
                        client = get_client()
                    except Exception:
                        pass
            rec.update({"status": status, "error": err[:300],
                        "finish_reason": None, "completion_tokens": None})
        results[model] = rec
        save(results, order)
        if i % 10 == 0 or rec["status"] == "works":
            print(f"[{i}/{len(todo)}] {model}: {rec['status']}", flush=True)
        time.sleep(0.2)

    counts = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("DONE" if not rate_limited else "STOPPED_RATE_LIMIT", counts, flush=True)
    works = [m for m, r in results.items() if r["status"] == "works"]
    print("WORKS:", json.dumps(works), flush=True)


if __name__ == "__main__":
    main()
