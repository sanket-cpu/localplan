"""Tests for the AI-boundary contract.

These pin the validation that stops a malformed model response from reaching
the deterministic layer. No model calls.
"""

import pytest
from pydantic import ValidationError

from localplan.models import AddTask, MoveTask, OpList, Task


@pytest.mark.parametrize("value", ["15:00", "00:00", "23:59", "09:30"])
def test_valid_clock_times_are_accepted(value):
    assert MoveTask(id=1, fixed_start=value).fixed_start == value


@pytest.mark.parametrize(
    "value", ["3pm", "25:00", "9:00", "09:60", "", "09:00:00", "noon", "٩:٠٠"]
)
def test_malformed_clock_times_are_rejected(value):
    # Previously "3pm" validated, persisted, and then failed to parse in the
    # scheduler every turn after — the task vanished from the plan for good.
    with pytest.raises(ValidationError):
        MoveTask(id=1, fixed_start=value)


def test_the_same_rule_applies_to_add_and_to_task():
    with pytest.raises(ValidationError):
        AddTask(name="x", duration_minutes=30, fixed_start="3pm")
    with pytest.raises(ValidationError):
        Task(name="x", duration_minutes=30, fixed_start="3pm")


def test_flexible_tasks_may_omit_a_time():
    assert AddTask(name="x", duration_minutes=30).fixed_start is None


@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_durations_are_rejected(value):
    with pytest.raises(ValidationError):
        AddTask(name="x", duration_minutes=value)


def test_op_list_discriminates_on_the_op_tag():
    parsed = OpList.model_validate_json(
        '{"ops": [{"op": "remove", "id": 2},'
        ' {"op": "set_duration", "id": 3, "duration_minutes": 45}]}'
    )
    assert [type(o).__name__ for o in parsed.ops] == ["RemoveTask", "SetDuration"]
