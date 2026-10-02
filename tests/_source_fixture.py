"""Copy source contracts without racing live Cargo or other generated output."""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT_GENERATED = {".git", "target", ".cache", ".pytest_cache", "build", "dist", "out"}


def copy_source_tree(source: Path, destination: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        generated = set(names) & ROOT_GENERATED if Path(directory) == source else set()
        generated.update(name for name in names
                         if name == "__pycache__" or name.endswith((".pyc", ".pyo")))
        if Path(directory) == source / "evidence" and "local" in names:
            generated.add("local")
        return generated

    # Keep source symlinks intact so the hostile validators still inspect them.
    # Ignoring only generated outputs preserves docs/evidence and all workflows.
    shutil.copytree(source, destination, symlinks=True, ignore=ignore)
