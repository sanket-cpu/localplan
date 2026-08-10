"""Deterministic scheduling engine — zero AI.

Takes validated tasks and produces a concrete time-blocked plan. It places
fixed appointments first (refusing and reporting when two overlap), then fills
flexible tasks into the remaining gaps by priority. All time arithmetic lives
here; the model never touches anything in this file.
"""

from datetime import time

from .models import Schedule, ScheduledBlock, Task

# The only configuration Milestone 1 has. Promote to a config module the day
# there is actually something to configure.
WORK_START = time(9, 0)
WORK_END = time(17, 0)

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _to_minutes(t: time) -> int:
    """Minutes since midnight."""
    return t.hour * 60 + t.minute


def _to_time(minutes: int) -> time:
    """Inverse of :func:`_to_minutes`."""
    return time(minutes // 60, minutes % 60)


def _parse_hhmm(value: str) -> time | None:
    """Parse a "HH:MM" string. Returns None if it is not a valid clock time."""
    try:
        hh, mm = value.strip().split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def build_schedule(tasks: list[Task]) -> Schedule:
    """Turn understood tasks into a concrete, time-blocked schedule.

    Pure function: same tasks in, same schedule out. Overlapping fixed tasks are
    refused and reported (not auto-resolved); flexible tasks that do not fit the
    remaining gaps are reported as unscheduled.
    """
    schedule = Schedule()

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
        placed_fixed.append((start_min, end_min, task.name))

    placed_fixed.sort()

    # Detect overlaps between adjacent fixed tasks -> refuse and report.
    for (a_start, a_end, a_name), (b_start, b_end, b_name) in zip(
        placed_fixed, placed_fixed[1:]
    ):
        if b_start < a_end:
            schedule.conflicts.append(
                f'"{a_name}" ({_to_time(a_start):%H:%M}-{_to_time(a_end):%H:%M}) '
                f'overlaps "{b_name}" '
                f"({_to_time(b_start):%H:%M}-{_to_time(b_end):%H:%M})"
            )

    for start_min, end_min, name in placed_fixed:
        schedule.blocks.append(
            ScheduledBlock(
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
                    ScheduledBlock(
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
