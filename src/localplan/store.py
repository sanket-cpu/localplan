"""Persistence — the board survives between runs.

The whole of conversation state is one :class:`PlannerState`, so persistence is
just "serialize that object to JSON, read it back on startup". Deliberately dumb:
a single file, single day, no history. History/recall is a future seam (a dated
directory of these files) and intentionally out of scope for this commit.

Two things it is *not* dumb about, because this file is the first thing ``main``
touches and a failure here locks the user out before they can type anything:
writes are atomic, and an unreadable file is quarantined rather than raised.
"""

import os
from pathlib import Path

from pydantic import ValidationError

from .models import PlannerState

# One file in the user's home. Single day, no history — see module docstring.
STATE_PATH = Path.home() / ".localplan" / "state.json"


def load_state(path: Path = STATE_PATH) -> tuple[PlannerState, str | None]:
    """Read persisted state, plus a problem string if it could not be read.

    Failures are data here, exactly as in :func:`~localplan.apply.apply_ops`. A
    corrupt or schema-incompatible file is moved aside and reported rather than
    raised: this runs before the CLI prints its banner, so an exception would
    crash every launch with no way to reach ``clear`` — the board would have to
    be deleted by hand. Quarantining preserves it for inspection instead.
    """
    if not path.exists():
        return PlannerState(), None
    try:
        text = path.read_text(encoding="utf-8")
        return PlannerState.model_validate_json(text), None
    except (ValidationError, ValueError, OSError):
        quarantine = path.with_suffix(".corrupt.json")
        try:
            path.replace(quarantine)
        except OSError:
            return PlannerState(), f"could not read {path}; started a fresh day"
        return PlannerState(), (
            f"could not read the saved plan; moved it to {quarantine} "
            "and started a fresh day"
        )


def save_state(state: PlannerState, path: Path = STATE_PATH) -> None:
    """Persist the board atomically. Creates the parent directory on first write.

    Writes a sibling temp file and renames it over the target, so an interrupted
    save (Ctrl-C, crash, full disk) leaves the previous good file intact instead
    of a half-written one. ``os.replace`` is atomic on POSIX and Windows alike.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)
