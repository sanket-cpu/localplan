"""Localplan — a local-first planner where the model reads your words and
deterministic Python does everything else.

The package is organized by the trust boundary that boundary implies:

* :mod:`localplan.models`   — Layer 0, the cross-boundary Pydantic contracts.
* :mod:`localplan.extract`  — Layer 1, the AI boundary (the only ``ollama`` importer).
* :mod:`localplan.planner`  — Layer 2, the deterministic core (apply + schedule).
* :mod:`localplan.store` / :mod:`localplan.export` — persistence and rendering.
* :mod:`localplan.cli`      — the multi-turn REPL that wires them together.

``main`` is re-exported here so the ``localplan`` console script keeps working.
"""

from .cli import main

__all__ = ["main"]
