"""Tests for Markdown export. Pure PlanResult -> str, so no model and no I/O."""

from localplan.export import to_markdown
from localplan.models import Task
from localplan.planner.scheduler import build_schedule


def test_empty_schedule_renders_a_placeholder():
    assert "_Nothing scheduled._" in to_markdown(build_schedule([]))


def test_blocks_render_with_times_and_a_flexible_tag():
    md = to_markdown(
        build_schedule(
            [
                Task(name="Standup", duration_minutes=30, fixed_start="09:00"),
                Task(name="Report", duration_minutes=60),
            ]
        )
    )
    assert "**09:00–09:30** Standup" in md
    assert "_(flexible)_" in md
    assert md.endswith("\n")


def test_conflicts_and_unscheduled_get_their_own_sections():
    md = to_markdown(
        build_schedule(
            [
                Task(name="A", duration_minutes=60, fixed_start="10:00"),
                Task(name="B", duration_minutes=60, fixed_start="10:30"),
                Task(name="Huge", duration_minutes=10 * 60),
            ]
        )
    )
    assert "## Conflicts (not resolved)" in md
    assert "## Could not fit" in md
    assert "- Huge" in md
