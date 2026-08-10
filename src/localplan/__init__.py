"""Localplan CLI — the Fork B (multi-turn) entry point.

Orchestration and presentation only. Each turn:

  read a line -> hand board + line to the AI boundary (produce_ops) ->
  hand the ops to the deterministic applier (apply_ops) -> persist ->
  reschedule (build_schedule) -> print.

No model calls, no time math, and no mutation logic live here. `clear` and
`export` are handled locally without touching the model.
"""

import sys
from pathlib import Path

from .apply import apply_ops
from .export import to_markdown
from .extract import produce_ops
from .models import PlannerState, Schedule
from .scheduler import build_schedule
from .store import load_state, save_state

EXPORT_PATH = Path("plan.md")


def _render(schedule: Schedule) -> str:
    lines: list[str] = []
    if schedule.blocks:
        lines.append("Your day:")
        for block in schedule.blocks:
            tag = "" if block.kind == "fixed" else "  (flexible)"
            lines.append(
                f"  {block.start:%H:%M}-{block.end:%H:%M}  {block.name}{tag}"
            )
    else:
        lines.append("Nothing scheduled.")

    if schedule.conflicts:
        lines.append("")
        lines.append("Conflicts (not resolved):")
        lines.extend(f"  ! {c}" for c in schedule.conflicts)

    if schedule.unscheduled:
        lines.append("")
        lines.append("Could not fit:")
        lines.extend(f"  - {name}" for name in schedule.unscheduled)

    return "\n".join(lines)


def _show(state: PlannerState) -> None:
    """Reschedule the current board and print it."""
    print(_render(build_schedule(state.tasks)))
    print()


def main() -> None:
    state = load_state()
    print(
        "Localplan — describe your day, then refine it turn by turn.\n"
        "Commands: 'clear' resets, 'export' writes plan.md, empty line or "
        "'quit' exits.\n"
    )
    if state.tasks:
        print("Picking up where you left off:")
        _show(state)

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text or text.lower() == "quit":
            break

        command = text.lower()
        if command == "clear":
            state = PlannerState()
            save_state(state)
            print("Cleared. Describe a new day.\n")
            continue
        if command == "export":
            EXPORT_PATH.write_text(to_markdown(build_schedule(state.tasks)))
            print(f"Exported to {EXPORT_PATH}\n")
            continue

        def _tick(_chunk: str) -> None:
            sys.stdout.write(".")
            sys.stdout.flush()

        sys.stdout.write("planning")
        sys.stdout.flush()
        ops = produce_ops(text, state.tasks, on_progress=_tick)
        sys.stdout.write("\r\033[K")  # clear the progress line

        state, problems = apply_ops(state, ops)
        save_state(state)

        _show(state)
        for problem in problems:
            print(f"  ! {problem}")
        if problems:
            print()
