"""Deterministic op-applier — zero AI.

The heart of Fork B. Takes the current board plus the edit ops the model chose
and produces the next board. All mutation lives here, on the trusted side of the
AI boundary: the model decided *what* to do (which id, which verb); this file is
the only thing that actually *does* it.

Pure function, exactly like the scheduler: same state + ops in, same state out.
A dangling reference (an id that isn't on the board) is not an exception — it is
reported as a *problem* string and the remaining ops still apply. Refuse and
report, never crash, never silently drop. Mirrors how ``build_schedule`` carries
conflicts as data.

Note the boundary tell: id *assignment* happens here (a computation), never in
the model. `AddTask` arrives without an id; ``next_id`` stamps one and advances.
"""

from collections.abc import Sequence

from ..models import (
    AddTask,
    MoveTask,
    Op,
    PlannerState,
    RemoveTask,
    SetDuration,
    Task,
)


def _index_of(tasks: list[Task], task_id: int) -> int | None:
    """Position of the task with ``task_id``, or None if it is not on the board."""
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return i
    return None


def apply_ops(
    state: PlannerState, ops: Sequence[Op]
) -> tuple[PlannerState, list[str]]:
    """Apply a batch of ops to the board and return the new state + any problems.

    Pure: the incoming ``state`` is never mutated; a fresh :class:`PlannerState`
    is returned. Ops are applied in order. An op that references an id not on the
    board is skipped and reported (the model picked a task that does not exist);
    every other op in the batch still lands.
    """
    tasks = [t.model_copy() for t in state.tasks]
    # Never trust a counter that has fallen behind the board it belongs to. A
    # stale next_id (hand-edited or partially restored state.json) would mint an
    # id that already exists, and _index_of resolves to the first match — so
    # every later op would silently hit the wrong task.
    next_id = max(state.next_id, max((t.id for t in tasks), default=0) + 1)
    problems: list[str] = []

    for op in ops:
        match op:
            case AddTask():
                tasks.append(
                    Task(
                        id=next_id,
                        name=op.name,
                        duration_minutes=op.duration_minutes,
                        fixed_start=op.fixed_start,
                        priority=op.priority,
                    )
                )
                next_id += 1

            case RemoveTask():
                idx = _index_of(tasks, op.id)
                if idx is None:
                    problems.append(f"no task with id {op.id} to remove")
                else:
                    del tasks[idx]

            case MoveTask():
                idx = _index_of(tasks, op.id)
                if idx is None:
                    problems.append(f"no task with id {op.id} to move")
                else:
                    tasks[idx] = tasks[idx].model_copy(
                        update={"fixed_start": op.fixed_start}
                    )

            case SetDuration():
                idx = _index_of(tasks, op.id)
                if idx is None:
                    problems.append(f"no task with id {op.id} to reschedule")
                else:
                    tasks[idx] = tasks[idx].model_copy(
                        update={"duration_minutes": op.duration_minutes}
                    )

            case _:
                # A new Op variant added to models.py without a branch here
                # would otherwise vanish without a trace, and the CLI would
                # print the unchanged plan as though the edit had landed.
                problems.append(f"unsupported operation {type(op).__name__}")

    return PlannerState(tasks=tasks, next_id=next_id), problems
