"""Pydantic schemas — the contract between the AI and deterministic layers.

Three families of types:

* AI output (`Op` and its variants, wrapped in `OpList`) — the *edits* the model
  is allowed to produce. Fork B: the model never returns a task list, only a list
  of operations against the current board. Times are raw "HH:MM" strings; there is
  no computed timeline here.
* Long-lived state (`Task`, `PlannerState`) — the board the deterministic layer
  owns and mutates. Every `Task` carries a Python-assigned ``id``; the model may
  only reference ids it was shown, never invent them.
* Scheduler output (`ScheduledBlock`, `Schedule`) — what deterministic Python
  produces. Times are real ``datetime.time`` objects. The type change *is* the
  boundary crossing: strings of understanding in, computed clock times out.
"""

from datetime import time
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Priority = Literal["high", "medium", "low"]


class Task(BaseModel):
    """A single task on the board. ``id`` is assigned by the deterministic layer.

    The model sees ``id`` (to reference tasks) but never mints one — new tasks
    arrive via :class:`AddTask`, which carries no id, and Python stamps it on
    insert. ``id`` defaults to 0 so scheduler-only code and tests, which never
    look at ids, can build tasks without one.
    """

    id: int = 0
    name: str = Field(description="Short description of the task.")
    duration_minutes: int = Field(
        description="How long the task takes, in minutes.", gt=0
    )
    fixed_start: str | None = Field(
        default=None,
        description=(
            'Start time as a 24-hour "HH:MM" string if the user pinned one '
            "(e.g. 3pm -> \"15:00\"). Null if the task is flexible."
        ),
    )
    priority: Priority = Field(
        default="medium",
        description="Task priority, used to order flexible tasks.",
    )


# --- Edit operations: the ONLY thing the model emits (Fork B) ----------------
#
# Each op is a CRUD verb against the board. `AddTask` creates (no id — Python
# assigns it); the rest reference an existing task by the `id` the model was
# shown this turn. The `op` literal is the discriminator.


class AddTask(BaseModel):
    """Create a new task. Carries no id — the deterministic layer assigns one."""

    op: Literal["add"] = "add"
    name: str = Field(description="Short description of the task.")
    duration_minutes: int = Field(
        description="How long the task takes, in minutes.", gt=0
    )
    fixed_start: str | None = Field(
        default=None,
        description='Pinned 24-hour "HH:MM" start, or null if flexible.',
    )
    priority: Priority = Field(default="medium")


class RemoveTask(BaseModel):
    """Delete the task with this id."""

    op: Literal["remove"] = "remove"
    id: int = Field(description="Id of an existing task, taken from the board.")


class MoveTask(BaseModel):
    """Pin an existing task to a new clock time."""

    op: Literal["move"] = "move"
    id: int = Field(description="Id of an existing task, taken from the board.")
    fixed_start: str = Field(
        description='New pinned start as 24-hour "HH:MM" (e.g. 2pm -> "14:00").'
    )


class SetDuration(BaseModel):
    """Change how long an existing task takes."""

    op: Literal["set_duration"] = "set_duration"
    id: int = Field(description="Id of an existing task, taken from the board.")
    duration_minutes: int = Field(description="New duration in minutes.", gt=0)


Op = Annotated[
    AddTask | RemoveTask | MoveTask | SetDuration,
    Field(discriminator="op"),
]


class OpList(BaseModel):
    """Top-level schema handed to Ollama's ``format`` parameter.

    Ollama constrains to a single root object, so the batch of ops is wrapped
    here. One user turn may imply several ops ("drop the gym and move the
    dentist to 4"), so this is always a list.
    """

    ops: list[Op] = Field(
        description="Every edit implied by the user's message, in order."
    )


class PlannerState(BaseModel):
    """The long-lived conversation state: the board plus the id counter.

    This is the single thing persisted between runs. ``next_id`` is a monotonic
    counter owned by the deterministic layer so ids are never reused, even across
    deletions.
    """

    tasks: list[Task] = Field(default_factory=list)
    next_id: int = 1


class ScheduledBlock(BaseModel):
    """A task placed on the timeline by the deterministic scheduler."""

    name: str
    start: time
    end: time
    kind: Literal["fixed", "flexible"]


class Schedule(BaseModel):
    """The finished plan plus anything the scheduler could not place.

    Failures are carried as data (not raised) so the scheduler stays a pure,
    fully testable function.
    """

    blocks: list[ScheduledBlock] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    unscheduled: list[str] = Field(default_factory=list)
