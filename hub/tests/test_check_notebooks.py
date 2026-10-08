# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from pathlib import Path

import nbformat
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "notebooks" / "tools"))
import check_notebooks  # noqa: E402

CONFIG = (
    "import os\n\nimport ipytest\n\n"
    'ipytest.autoconfig(raise_on_error=os.environ.get("HUDHUD_NB_CHECK") == "1")'
)


def make_notebook(tmp_path: Path, test_body: str, solution: str) -> Path:
    nb = nbformat.v4.new_notebook()
    nb.metadata["hudhud"] = {"solution": "tiny"}
    nb.metadata["kernelspec"] = {
        "name": "python3", "display_name": "Python 3", "language": "python"
    }
    stub = nbformat.v4.new_code_cell("def double(x):\n    raise NotImplementedError")
    stub.metadata["tags"] = ["stub"]
    test = nbformat.v4.new_code_cell(f"%%ipytest -q\n\ndef test_double():\n    {test_body}")
    test.metadata["tags"] = ["test"]
    nb.cells = [nbformat.v4.new_code_cell(CONFIG), stub, test]
    (tmp_path / "solutions").mkdir()
    (tmp_path / "solutions" / "tiny.py").write_text(solution, encoding="utf-8")
    path = tmp_path / "99-tiny.ipynb"
    nbformat.write(nb, path)
    return path


GOOD_SOLUTION = "def double(x):\n    return 2 * x\n"


def test_clean_notebook_passes_both_modes(tmp_path):
    path = make_notebook(tmp_path, "assert double(2) == 4", GOOD_SOLUTION)
    assert check_notebooks.check(path, "solution") == []
    assert check_notebooks.check(path, "stub") == []


def test_wrong_solution_is_reported(tmp_path):
    path = make_notebook(tmp_path, "assert double(2) == 4", "def double(x):\n    return x\n")
    problems = check_notebooks.check(path, "solution")
    assert len(problems) == 1 and "reference solution" in problems[0]


def test_test_that_ignores_the_stub_is_reported(tmp_path):
    path = make_notebook(tmp_path, "assert True", GOOD_SOLUTION)
    problems = check_notebooks.check(path, "stub")
    assert len(problems) == 1 and "passes against the stubs" in problems[0]


def test_unknown_mode_rejected(tmp_path):
    path = make_notebook(tmp_path, "assert double(2) == 4", GOOD_SOLUTION)
    with pytest.raises(ValueError):
        check_notebooks.check(path, "both")
