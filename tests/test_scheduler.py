"""Tests for the deterministic scheduler.

The scheduler is pure Python, so everything here uses hardcoded Task objects
and NO model calls. This is where correctness of the time math is proven.
"""

from datetime import time

from localplan.models import Task
from localplan.planner.scheduler import build_schedule


def test_single_fixed_task_is_placed():
    schedule = build_schedule(
        [Task(name="Call", duration_minutes=30, fixed_start="15:00")]
    )
    assert schedule.conflicts == []
    assert len(schedule.blocks) == 1
    block = schedule.blocks[0]
    assert block.start == time(15, 0)
    assert block.end == time(15, 30)
    assert block.kind == "fixed"


def test_flexible_task_fills_gap_after_fixed():
    schedule = build_schedule(
        [
            Task(name="Standup", duration_minutes=30, fixed_start="09:00"),
            Task(name="Report", duration_minutes=60),
        ]
    )
    assert schedule.unscheduled == []
    report = next(b for b in schedule.blocks if b.name == "Report")
    # First gap after the 09:00-09:30 standup.
    assert report.start == time(9, 30)
    assert report.end == time(10, 30)
    assert report.kind == "flexible"


def test_overlapping_fixed_tasks_are_reported_not_resolved():
    schedule = build_schedule(
        [
            Task(name="Call A", duration_minutes=60, fixed_start="15:00"),
            Task(name="Call B", duration_minutes=60, fixed_start="15:30"),
        ]
    )
    assert len(schedule.conflicts) == 1
    # Both blocks are still present — refuse and report, never silently drop.
    assert len(schedule.blocks) == 2


def test_priority_orders_flexible_tasks():
    schedule = build_schedule(
        [
            Task(name="Low thing", duration_minutes=60, priority="low"),
            Task(name="High thing", duration_minutes=60, priority="high"),
        ]
    )
    # High priority takes the earliest slot.
    first = schedule.blocks[0]
    assert first.name == "High thing"
    assert first.start == time(9, 0)


def test_task_that_does_not_fit_is_unscheduled():
    schedule = build_schedule(
        [Task(name="Marathon", duration_minutes=10 * 60)]  # 10h > 8h workday
    )
    assert schedule.blocks == []
    assert schedule.unscheduled == ["Marathon"]


# --- End-of-day boundary ----------------------------------------------------
#
# _to_time builds a datetime.time, which cannot represent an hour >= 24. Any
# fixed task ending past midnight used to raise ValueError out of build_schedule
# — and because main() persists before rendering, the poisoned task crashed
# every subsequent startup before the input loop, with no way to reach `clear`.


def test_fixed_task_past_midnight_is_reported_not_raised():
    schedule = build_schedule(
        [Task(name="Sleep", duration_minutes=480, fixed_start="23:00")]
    )
    assert schedule.blocks == []
    assert len(schedule.conflicts) == 1
    assert "does not fit in the day" in schedule.conflicts[0]


def test_fixed_task_ending_exactly_at_midnight_is_placed():
    schedule = build_schedule(
        [Task(name="Wind down", duration_minutes=30, fixed_start="23:30")]
    )
    assert schedule.conflicts == []
    assert schedule.blocks[0].start == time(23, 30)
    assert schedule.blocks[0].end == time(0, 0)


def test_full_day_fixed_task_is_refused():
    # Would otherwise render as a meaningless "00:00-00:00".
    schedule = build_schedule(
        [Task(name="Forever", duration_minutes=24 * 60, fixed_start="00:00")]
    )
    assert schedule.blocks == []
    assert len(schedule.conflicts) == 1


def test_long_flexible_task_is_unscheduled_not_raised():
    schedule = build_schedule([Task(name="Epic", duration_minutes=100_000)])
    assert schedule.unscheduled == ["Epic"]


# --- Overlap detection ------------------------------------------------------


def test_long_task_swallowing_later_tasks_reports_every_overlap():
    # Comparing only adjacent pairs after sorting reported A/B and missed A/C,
    # leaving C double-booked inside A with no warning.
    schedule = build_schedule(
        [
            Task(name="A", duration_minutes=180, fixed_start="09:00"),
            Task(name="B", duration_minutes=30, fixed_start="10:00"),
            Task(name="C", duration_minutes=30, fixed_start="11:00"),
        ]
    )
    assert len(schedule.conflicts) == 2
    assert any('"A" (09:00-12:00) overlaps "C"' in c for c in schedule.conflicts)


def test_chained_overlaps_compare_against_furthest_end():
    # B extends past A, so C must be reported against B, not A.
    schedule = build_schedule(
        [
            Task(name="A", duration_minutes=60, fixed_start="09:00"),
            Task(name="B", duration_minutes=90, fixed_start="09:30"),
            Task(name="C", duration_minutes=30, fixed_start="10:30"),
        ]
    )
    assert len(schedule.conflicts) == 2
    assert any('"B" (09:30-11:00) overlaps "C"' in c for c in schedule.conflicts)


def test_unparseable_time_is_reported_and_other_tasks_still_schedule():
    # HHMM_PATTERN rejects this at the AI boundary, so the only way a bad time
    # reaches the scheduler is a hand-edited state.json. model_construct skips
    # validation to reproduce exactly that — this branch is defence in depth,
    # not dead code.
    broken = Task.model_construct(
        id=1, name="Broken", duration_minutes=30, fixed_start="not a time",
        priority="medium",
    )
    schedule = build_schedule([broken, Task(name="Fine", duration_minutes=60)])
    assert schedule.conflicts == ['Broken: unrecognized time "not a time"']
    assert [b.name for b in schedule.blocks] == ["Fine"]
