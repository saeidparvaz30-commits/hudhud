# SPDX-License-Identifier: AGPL-3.0-or-later
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "notebooks" / "tools"))
import check_notebooks  # noqa: E402

NOTEBOOKS = sorted((ROOT / "notebooks").glob("[0-9][0-9]-*.ipynb"))


@pytest.mark.parametrize("mode", ["solution", "stub"])
@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_notebook(path, mode):
    assert check_notebooks.check(path, mode) == []
