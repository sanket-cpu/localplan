"""Deterministic scheduling engine — zero AI.

Takes validated tasks and produces a concrete time-blocked plan. It places
fixed appointments first (refusing and reporting when two overlap), then fills
flexible tasks into the remaining gaps by priority. All time arithmetic lives
here; the model never touches anything in this file.
"""

from datetime import time

from ..models import PlanResult, TimeBlock, Task

# The only configuration Milestone 1 has. Promote to a config module the day
# there is actually something to configure.
WORK_START = time(9, 0)
WORK_END = time(17, 0)

MINUTES_PER_DAY = 24 * 60

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _to_minutes(t: time) -> int:
    """Minutes since midnight."""
    return t.hour * 60 + t.minute


def _to_time(minutes: int) -> time:
    """Inverse of :func:`_to_minutes`.

    ``1440`` — midnight closing the day — wraps to ``00:00``, so a task ending
    exactly on the boundary renders as "23:30-00:00". Anything beyond that is
    refused before it reaches here (:func:`build_schedule`), because ``time``
    cannot represent an hour >= 24 and would raise.
    """
    return time(minutes // 60 % 24, minutes % 60)


def _parse_hhmm(value: str) -> time | None:
    """Parse a "HH:MM" string. Returns None if it is not a valid clock time."""
    try:
        hh, mm = value.strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def build_schedule(tasks: list[Task]) -> PlanResult:
    """Turn understood tasks into a concrete, time-blocked schedule.

    Pure function: same tasks in, same schedule out. Overlapping fixed tasks are
    refused and reported (not auto-resolved); flexible tasks that do not fit the
    remaining gaps are reported as unscheduled.
    """
    schedule = PlanResult()

    fixed_tasks = [t for t in tasks if t.fixed_start is not None]
    flexible_tasks = [t for t in tasks if t.fixed_start is None]

    # --- Place fixed tasks (the anchors) ------------------------------------
    placed_fixed: list[tuple[int, int, str]] = []  # (start_min, end_min, name)
    for task in fixed_tasks:
        start = _parse_hhmm(task.fixed_start or "")
        if start is None:
            schedule.conflicts.append(
                f'{task.name}: unrecognized time "{task.fixed_start}"'
            )
            continue
        start_min = _to_minutes(start)
        end_min = start_min + task.duration_minutes
        if end_min > MINUTES_PER_DAY or task.duration_minutes >= MINUTES_PER_DAY:
            # A single-day planner has nowhere to put the overflow, and the
            # clock types cannot express it. Refuse and report, like any other
            # failure here — never let it reach _to_time, which would raise.
            # The duration bound also rejects the degenerate full-day task,
            # which would otherwise render as a meaningless "00:00-00:00".
            schedule.conflicts.append(
                f"{task.name}: {task.duration_minutes} min from "
                f"{start:%H:%M} does not fit in the day"
            )
            continue
        placed_fixed.append((start_min, end_min, task.name))

    placed_fixed.sort()

    # Detect overlaps -> refuse and report. Each task is compared against the
    # furthest-reaching task so far, not merely its predecessor: one long
    # appointment can swallow several later ones, and an adjacent-pairs-only
    # check would report just the first and leave the rest double-booked.
    covering: tuple[int, int, str] | None = None
    for block in placed_fixed:
        start_min, end_min, name = block
        if covering is not None and start_min < covering[1]:
            c_start, c_end, c_name = covering
            schedule.conflicts.append(
                f'"{c_name}" ({_to_time(c_start):%H:%M}-{_to_time(c_end):%H:%M}) '
                f'overlaps "{name}" '
                f"({_to_time(start_min):%H:%M}-{_to_time(end_min):%H:%M})"
            )
        if covering is None or end_min > covering[1]:
            covering = block

    for start_min, end_min, name in placed_fixed:
        schedule.blocks.append(
            TimeBlock(
                name=name,
                start=_to_time(start_min),
                end=_to_time(end_min),
                kind="fixed",
            )
        )

    # --- Compute free gaps within the work window ---------------------------
    work_start = _to_minutes(WORK_START)
    work_end = _to_minutes(WORK_END)

    merged: list[list[int]] = []
    for start_min, end_min, _name in placed_fixed:
        if merged and start_min <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end_min)
        else:
            merged.append([start_min, end_min])

    gaps: list[list[int]] = []
    cursor = work_start
    for start_min, end_min in merged:
        if start_min > cursor:
            gaps.append([cursor, min(start_min, work_end)])
        cursor = max(cursor, end_min)
    if cursor < work_end:
        gaps.append([cursor, work_end])

    # --- Fill flexible tasks by priority (first-fit) ------------------------
    flexible_tasks.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 1))
    for task in flexible_tasks:
        for gap in gaps:
            if gap[1] - gap[0] >= task.duration_minutes:
                start_min = gap[0]
                end_min = start_min + task.duration_minutes
                schedule.blocks.append(
                    TimeBlock(
                        name=task.name,
                        start=_to_time(start_min),
                        end=_to_time(end_min),
                        kind="flexible",
                    )
                )
                gap[0] = end_min  # shrink the gap
                break
        else:
            schedule.unscheduled.append(task.name)

    schedule.blocks.sort(key=lambda b: b.start)
    return schedule
