"""Error bars for repeated-run LLM evaluations.

The reusable entry point is :mod:`errorbars.intervals`.
"""

from .intervals import intervals, paired_intervals

__all__ = ["intervals", "paired_intervals"]
__version__ = "0.1.0"
