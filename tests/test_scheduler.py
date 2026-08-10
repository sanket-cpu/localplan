"""Tests for the deterministic scheduler.

The scheduler is pure Python, so everything here uses hardcoded Task objects
and NO model calls. This is where correctness of the time math is proven.
"""

from datetime import time

from localplan.models import Task
from localplan.scheduler import build_schedule


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
