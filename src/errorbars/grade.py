"""Extract and grade final answers from raw model output.

Rule: take the number after the last '####'; if absent, the last number in
the text. Normalization: strip commas, dollar signs, percent signs and
whitespace; drop a trailing '.0'. A response with no number at all is
unparsable (``extract_answer`` returns None) and grades as incorrect.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"-?\d[\d,]*\.?\d*")


def _normalize(token: str) -> str:
    t = token.replace(",", "").replace("$", "").replace("%", "").strip()
    if t.endswith("."):
        t = t[:-1]
    try:
        val = float(t)
    except ValueError:
        return t
    if val == int(val):
        return str(int(val))
    return str(val)


def extract_answer(text: str | None) -> str | None:
    """Return the normalized final answer string, or None if unparsable."""
    if not text:
        return None
    if "####" in text:
        tail = text.rsplit("####", 1)[1]
        m = _NUMBER.search(tail)
        if m:
            return _normalize(m.group(0))
        # marker present but no number after it: fall through to last number
    nums = _NUMBER.findall(text)
    if not nums:
        return None
    return _normalize(nums[-1])


def parse_gold(solution: str) -> str:
    """GSM8K gold answer: the number after '####' in the reference solution."""
    tail = solution.rsplit("####", 1)[1]
    return _normalize(_NUMBER.search(tail).group(0))


def grade(text: str | None, gold: str) -> tuple[int, str | None]:
    """Return (correct 0/1, extracted answer or None)."""
    ans = extract_answer(text)
    if ans is None:
        return 0, None
    try:
        return int(float(ans) == float(gold)), ans
    except ValueError:
        return int(ans == gold), ans
