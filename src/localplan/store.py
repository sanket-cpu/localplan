"""Persistence — the board survives between runs.

The whole of conversation state is one :class:`PlannerState`, so persistence is
just "serialize that object to JSON, read it back on startup". Deliberately dumb:
a single file, single day, no history. History/recall is a future seam (a dated
directory of these files) and intentionally out of scope for this commit.
"""

from pathlib import Path

from .models import PlannerState

# One file in the user's home. Single day, no history — see module docstring.
STATE_PATH = Path.home() / ".localplan" / "state.json"


def load_state(path: Path = STATE_PATH) -> PlannerState:
    """Read persisted state, or a fresh empty board if there is none."""
    if not path.exists():
        return PlannerState()
    return PlannerState.model_validate_json(path.read_text())


def save_state(state: PlannerState, path: Path = STATE_PATH) -> None:
    """Persist the board. Creates the parent directory on first write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.model_dump_json(indent=2))
