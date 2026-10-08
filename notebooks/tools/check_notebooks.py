# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify the guided notebooks.

solution mode: every `stub` cell is replaced by an import of the notebook's
reference module (metadata.hudhud.solution) and no cell may error.

stub mode: the notebook runs as shipped. Every `test` cell must fail and no
other cell may error, which proves the tests exercise the stubs.
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

NOTEBOOKS_DIR = Path(__file__).resolve().parent.parent
MODES = ("solution", "stub")


def _tags(cell) -> set[str]:
    return set(cell.get("metadata", {}).get("tags", []))


def _errored(cell) -> bool:
    return any(o.get("output_type") == "error" for o in cell.get("outputs", []))


def _prepare(nb, mode: str):
    nb = copy.deepcopy(nb)
    if mode == "solution":
        module = nb.metadata["hudhud"]["solution"]
        first = True
        for cell in nb.cells:
            if "stub" in _tags(cell):
                cell.source = f"from solutions.{module} import *  # noqa: F403" if first else ""
                first = False
    return nb


def _execute(nb, cwd: Path):
    os.environ["HUDHUD_NB_CHECK"] = "1"
    client = NotebookClient(
        nb,
        timeout=600,
        kernel_name="python3",
        allow_errors=True,
        resources={"metadata": {"path": str(cwd)}},
    )
    client.execute()
    return nb


def check(path: Path, mode: str) -> list[str]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    nb = _execute(_prepare(nbformat.read(path, as_version=4), mode), path.parent)
    problems = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        is_test = "test" in _tags(cell)
        if mode == "solution" and _errored(cell):
            problems.append(f"{path.name} cell {i}: errors with the reference solution")
        elif mode == "stub" and is_test and not _errored(cell):
            problems.append(f"{path.name} cell {i}: test passes against the stubs")
        elif mode == "stub" and not is_test and _errored(cell):
            problems.append(f"{path.name} cell {i}: errors before any stub is filled in")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebooks", nargs="*", type=Path)
    parser.add_argument("--mode", choices=[*MODES, "both"], default="both")
    args = parser.parse_args(argv)
    paths = args.notebooks or sorted(NOTEBOOKS_DIR.glob("[0-9][0-9]-*.ipynb"))
    modes = MODES if args.mode == "both" else (args.mode,)
    problems = [p for path in paths for mode in modes for p in check(path, mode)]
    for p in problems:
        print(p)
    print(f"{len(paths)} notebook(s), {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
