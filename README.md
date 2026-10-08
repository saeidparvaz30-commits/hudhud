# Hudhud

A self-hosted, open-source book reader that remembers where you stopped, feels
like paper, turns highlights into Obsidian notes, and, when you select a
passage, finds what you wrote about the same idea in other books.

Hudhud is the hoopoe. In Attar's *Conference of the Birds* it guides the other
birds to the Simorgh.

## Status

Early and learning-first. The hub is built through guided Jupyter notebooks:
each one explains a concept, gives function signatures and tests, and the code
graduates into `hub/src/hudhud_hub/` once the tests pass.

| Notebook | Graduates to |
|---|---|
| 00 Setup and tour | (none) |
| 01 Book formats | `library.py` |
| 02 Data model | `db.py` |
| 03 Locators and progress | `progress.py` |
| 04 Vault writer | `vault.py` |

## Layout

    hub/         Python hub (uv project): src/hudhud_hub/, tests/
    notebooks/   guided notebooks; solutions/ holds reference answers
    LICENSE      AGPL-3.0-or-later
    CLA.md       contributor licence agreement

## Working the notebooks

    uv sync --project hub
    uv run --project hub jupyter lab notebooks

Fill in each cell that raises `NotImplementedError`, then run the test cells.
Look in `notebooks/solutions/` only when stuck.

Check every notebook (tests pass with the reference answers, fail with the
stubs):

    uv run --project hub pytest hub/tests

## Licence

AGPL-3.0-or-later. Outside contributions need the [CLA](CLA.md).
