"""Layer 2 — the deterministic core. Zero AI, pure functions, fully unit-tested.

This package is the trusted side of the boundary: no module here imports
``ollama`` or takes model output as anything but already-validated Pydantic
data. Two pure functions live here, both "same input → same output, failures
carried as data, never raised":

* :func:`~localplan.planner.apply.apply_ops` — applies the model's chosen edit
  ops to the board and assigns task ids.
* :func:`~localplan.planner.scheduler.build_schedule` — turns tasks into a
  concrete, time-blocked timeline with conflict/capacity reporting.

All time and id arithmetic lives behind this wall. See CLAUDE.md's build
boundary: the logic here is hand-designed and must not be changed silently.
"""

from .apply import apply_ops
from .scheduler import build_schedule

__all__ = ["apply_ops", "build_schedule"]
