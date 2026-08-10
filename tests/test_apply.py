"""Tests for the deterministic op-applier.

Like the scheduler, ``apply_ops`` is pure Python, so everything here uses
hand-built ops and NO model calls. This is where the correctness of every edit —
and every "the model pointed at nothing" failure — is proven. The whole reason
Fork B was chosen over Fork A is that this logic is reachable by a unit test at
all.
"""

from localplan.apply import apply_ops
from localplan.models import (
    AddTask,
    MoveTask,
    PlannerState,
    RemoveTask,
    SetDuration,
    Task,
)


def test_add_assigns_monotonic_ids():
    state, problems = apply_ops(
        PlannerState(),
        [
            AddTask(name="Standup", duration_minutes=30, fixed_start="09:00"),
            AddTask(name="Report", duration_minutes=120),
        ],
    )
    assert problems == []
    assert [t.id for t in state.tasks] == [1, 2]
    assert state.next_id == 3


def test_input_state_is_not_mutated():
    original = PlannerState(tasks=[Task(id=1, name="Gym", duration_minutes=60)])
    apply_ops(original, [RemoveTask(id=1)])
    # The applier is pure: the state we passed in is untouched.
    assert [t.name for t in original.tasks] == ["Gym"]


def test_remove_existing_deletes_only_that_task():
    start = PlannerState(
        tasks=[
            Task(id=1, name="Gym", duration_minutes=60),
            Task(id=2, name="Report", duration_minutes=120),
        ],
        next_id=3,
    )
    state, problems = apply_ops(start, [RemoveTask(id=1)])
    assert problems == []
    assert [t.name for t in state.tasks] == ["Report"]


def test_remove_missing_id_is_reported_not_raised():
    start = PlannerState(
        tasks=[Task(id=1, name="Gym", duration_minutes=60)], next_id=2
    )
    state, problems = apply_ops(start, [RemoveTask(id=99)])
    # Refuse and report: the board is unchanged, the failure is data.
    assert [t.name for t in state.tasks] == ["Gym"]
    assert problems == ["no task with id 99 to remove"]


def test_move_pins_a_new_start():
    start = PlannerState(
        tasks=[Task(id=1, name="Report", duration_minutes=120)], next_id=2
    )
    state, problems = apply_ops(start, [MoveTask(id=1, fixed_start="14:00")])
    assert problems == []
    assert state.tasks[0].fixed_start == "14:00"


def test_set_duration_changes_only_the_duration():
    start = PlannerState(
        tasks=[Task(id=1, name="Report", duration_minutes=30)], next_id=2
    )
    state, problems = apply_ops(start, [SetDuration(id=1, duration_minutes=180)])
    assert problems == []
    assert state.tasks[0].duration_minutes == 180
    assert state.tasks[0].name == "Report"


def test_batch_of_ops_applies_in_order_and_partial_failures_still_land():
    start = PlannerState(
        tasks=[
            Task(id=1, name="Gym", duration_minutes=60),
            Task(id=2, name="Dentist", duration_minutes=45, fixed_start="15:00"),
        ],
        next_id=3,
    )
    # "drop the gym and move the dentist to 4" plus a dangling reference.
    state, problems = apply_ops(
        start,
        [
            RemoveTask(id=1),
            MoveTask(id=2, fixed_start="16:00"),
            SetDuration(id=99, duration_minutes=10),  # not on the board
        ],
    )
    assert [t.name for t in state.tasks] == ["Dentist"]
    assert state.tasks[0].fixed_start == "16:00"
    assert problems == ["no task with id 99 to reschedule"]
