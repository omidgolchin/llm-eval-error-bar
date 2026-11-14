"""Freeze the pre-registered plan.

Writes SHA-256 hashes of PLAN.md, config.yaml, the prompt files and all
source code to FREEZE_MANIFEST.txt. Run this after PLAN.md is approved and
before any main-run call.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(root: Path = ROOT) -> Path:
    targets: list[Path] = []
    for name in ("PLAN.md", "config.yaml"):
        p = root / name
        if p.exists():
            targets.append(p)
    targets += sorted((root / "prompts").glob("*"))
    targets += sorted((root / "src").rglob("*.py"))
    targets += sorted((root / "tests").glob("*.py"))

    lines = ["# Freeze manifest: SHA-256 of the plan, config, prompts and "
             "code, recorded before the main run."]
    for p in targets:
        lines.append(f"{_sha256(p)}  {p.relative_to(root)}")
    out = root / "FREEZE_MANIFEST.txt"
    out.write_text("\n".join(lines) + "\n")
    return out


if __name__ == "__main__":
    print(freeze())
