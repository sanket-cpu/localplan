"""Tests for persistence.

Every test passes an explicit ``tmp_path``. The module default is
``Path.home()/.localplan/state.json`` — a test that forgets would clobber the
developer's real board.
"""

from localplan.models import PlannerState, Task
from localplan.store import load_state, save_state


def test_round_trip_preserves_the_board(tmp_path):
    path = tmp_path / "state.json"
    original = PlannerState(
        tasks=[Task(id=1, name="Gym", duration_minutes=60, fixed_start="09:00")],
        next_id=2,
    )
    save_state(original, path)
    restored, problem = load_state(path)
    assert problem is None
    assert restored == original


def test_missing_file_yields_an_empty_board(tmp_path):
    state, problem = load_state(tmp_path / "nothing.json")
    assert state == PlannerState()
    assert problem is None


def test_non_ascii_task_names_survive_a_round_trip(tmp_path):
    # Without encoding="utf-8" this depends on the platform locale and breaks
    # on Windows (cp1252/cp932).
    path = tmp_path / "state.json"
    save_state(
        PlannerState(tasks=[Task(id=1, name="設計レビュー ☕", duration_minutes=30)]),
        path,
    )
    restored, problem = load_state(path)
    assert problem is None
    assert restored.tasks[0].name == "設計レビュー ☕"


def test_corrupt_file_is_quarantined_rather_than_raised(tmp_path):
    # This runs before the CLI prints anything, so raising here crashed every
    # launch with no way to reach `clear`.
    path = tmp_path / "state.json"
    path.write_text('{"tasks": [{"name": "x", "dur', encoding="utf-8")
    state, problem = load_state(path)
    assert state == PlannerState()
    assert problem is not None
    assert (tmp_path / "state.corrupt.json").exists()
    assert not path.exists()


def test_schema_incompatible_file_is_quarantined(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        '{"tasks": [{"name": "x", "duration_minutes": -5}], "next_id": 1}',
        encoding="utf-8",
    )
    state, problem = load_state(path)
    assert state == PlannerState()
    assert problem is not None


def test_save_leaves_no_temp_file_behind(tmp_path):
    path = tmp_path / "state.json"
    save_state(PlannerState(), path)
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_save_does_not_destroy_the_previous_file_on_a_failed_write(tmp_path):
    # The atomic rename means a good file is only ever replaced wholesale.
    path = tmp_path / "state.json"
    save_state(PlannerState(tasks=[Task(id=1, name="Keep", duration_minutes=30)]), path)
    before = path.read_text(encoding="utf-8")
    save_state(PlannerState(tasks=[Task(id=1, name="Replace", duration_minutes=30)]), path)
    assert path.read_text(encoding="utf-8") != before
    restored, problem = load_state(path)
    assert problem is None
    assert restored.tasks[0].name == "Replace"
