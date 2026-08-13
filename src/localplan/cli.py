"""Localplan CLI — subcommands, with an interactive `plan` session.

CLAUDE.md's shape: one entry point, subcommands. Planning itself is multi-turn:
`localplan plan` opens an interactive session where you refine your day line by
line, and the board persists between sessions. The other subcommands are
one-shot:

  plan            open the interactive planning session (refine turn by turn)
  plan "<text>"   run a single turn non-interactively, then exit (scripts/evals)
  clear           reset the board to empty
  export [path]   write the current plan as Markdown (default plan.md)
  eval run        run the eval harness sweep    (Layer 5 — not built yet)
  eval report     regenerate charts from CSVs   (Layer 5 — not built yet)

Orchestration only: no model calls, no time math, and no mutation logic live
here; those belong to extract.py, planner/, and store.py. "Refuse and report,
never crash" reaches out here too — a dead Ollama daemon, a truncated response,
or a read-only disk costs a turn, never the session or a traceback.
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from .export import to_markdown
from .extract import produce_ops
from .models import PlanResult, PlannerState
from .planner import apply_ops, build_schedule
from .store import load_state, save_state

DEFAULT_EXPORT_PATH = Path("plan.md")

# Cap the progress indicator well inside any sane terminal. Past this it stops
# growing: dots that wrap to a second row cannot be erased by a single-line
# clear, and would pile up above the plan.
_PROGRESS_WIDTH = 60


class _Progress:
    """A single-line "planning..." indicator that cleans up after itself.

    Silent when stdout is not a TTY, so piping does not litter the capture with
    dots or escape bytes. Clears with spaces rather than an ANSI erase for the
    same reason.
    """

    def __init__(self, label: str = "planning") -> None:
        self._live = sys.stdout.isatty()
        self._width = len(label)
        if self._live:
            sys.stdout.write(label)
            sys.stdout.flush()

    def tick(self, _chunk: str) -> None:
        if self._live and self._width < _PROGRESS_WIDTH:
            sys.stdout.write(".")
            sys.stdout.flush()
            self._width += 1

    def clear(self) -> None:
        if self._live:
            sys.stdout.write("\r" + " " * self._width + "\r")
            sys.stdout.flush()


def _render(schedule: PlanResult) -> str:
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


def _write_export(path: Path, state: PlannerState) -> int:
    """Write the current plan to a Markdown file.

    Shared by the interactive `export` command and the `export` subcommand.
    """
    try:
        path.write_text(
            to_markdown(build_schedule(state.tasks)), encoding="utf-8"
        )
    except OSError as exc:
        print(f"  ! could not write {path}: {exc}")
        return 1
    print(f"Exported to {path}")
    return 0


def _run_turn(state: PlannerState, text: str) -> PlannerState:
    """One AI turn: understand -> apply -> persist -> reschedule -> print.

    Returns the new board (unchanged if the turn failed at the AI boundary).
    Failures are printed and swallowed, never raised, so the session keeps going
    and a one-shot `plan "..."` still exits cleanly. This is the one place a turn
    can fail for reasons outside this program's control, so the indicator is
    cleared before the message lands — never on a half-erased progress line.
    """
    progress = _Progress()
    error: str | None = None
    ops = []
    try:
        ops = produce_ops(text, state.tasks, on_progress=progress.tick)
    except KeyboardInterrupt:
        error = "cancelled"
    except ValidationError:
        error = "could not read the model's reply — try rephrasing"
    except Exception as exc:  # dead daemon, missing model, socket error
        error = f"model unavailable: {exc}"
    finally:
        progress.clear()

    if error is not None:
        print(f"  ! {error}\n")
        return state

    state, problems = apply_ops(state, ops)
    try:
        save_state(state)
    except OSError as exc:
        problems.append(f"plan not saved: {exc}")

    _show(state)
    for problem in problems:
        print(f"  ! {problem}")
    if problems:
        print()
    return state


def _interactive() -> int:
    """The multi-turn planning session, reached by `localplan plan`.

    Each line is one turn; `clear`, `export`, `quit`, and an empty line are
    handled locally without touching the model.
    """
    state, load_problem = load_state()
    print(
        "Localplan — describe your day, then refine it turn by turn.\n"
        "Commands: 'clear' resets, 'export' writes plan.md, empty line or "
        "'quit' exits.\n"
    )
    if load_problem:
        print(f"  ! {load_problem}\n")
    if state.tasks:
        print("Picking up where you left off:")
        _show(state)

    while True:
        try:
            text = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        command = text.lower()
        if not text or command == "quit":
            break
        if command == "clear":
            state = PlannerState()
            try:
                save_state(state)
            except OSError as exc:
                print(f"  ! could not clear the board: {exc}\n")
                continue
            print("Cleared. Describe a new day.\n")
            continue
        if command == "export":
            _write_export(DEFAULT_EXPORT_PATH, state)
            print()
            continue

        state = _run_turn(state, text)
    return 0


def cmd_plan(text: str | None) -> int:
    """`plan` with no text opens the interactive session; `plan "..."` runs a
    single turn against the persisted board and exits.
    """
    if text is None:
        return _interactive()

    state, load_problem = load_state()
    if load_problem:
        print(f"  ! {load_problem}")
    _run_turn(state, text)
    return 0


def cmd_clear() -> int:
    """Reset the persisted board to empty."""
    try:
        save_state(PlannerState())
    except OSError as exc:
        print(f"  ! could not clear the board: {exc}")
        return 1
    print("Cleared. The board is empty.")
    return 0


def cmd_export(path: Path) -> int:
    """Write the current plan to a Markdown file."""
    state, _ = load_state()
    return _write_export(path, state)


def cmd_eval(subcommand: str) -> int:
    """Layer 5 (the eval harness) is intentionally last in the build order and
    is not built yet. The subcommand exists so the CLI shape matches CLAUDE.md;
    it reports honestly rather than pretending to run.
    """
    print(f"  ! eval {subcommand} is not implemented yet (Layer 5 — eval harness)")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="localplan",
        description=(
            "Local-first planner: the model reads your words, deterministic "
            "Python does everything else."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser(
        "plan",
        help="open the interactive planning session (or run one turn with text)",
    )
    p_plan.add_argument(
        "text",
        nargs="?",
        default=None,
        help="optional single request; omit it to refine turn by turn",
    )

    sub.add_parser("clear", help="reset the board to empty")

    p_export = sub.add_parser("export", help="write the current plan as Markdown")
    p_export.add_argument(
        "path",
        nargs="?",
        default=str(DEFAULT_EXPORT_PATH),
        help=f"output file (default: {DEFAULT_EXPORT_PATH})",
    )

    p_eval = sub.add_parser("eval", help="eval harness (Layer 5 — not built yet)")
    eval_sub = p_eval.add_subparsers(dest="eval_command", required=True)
    p_eval_run = eval_sub.add_parser("run", help="run the eval sweep")
    p_eval_run.add_argument("--config", help="path to the eval config file")
    eval_sub.add_parser("report", help="regenerate charts from CSVs")

    args = parser.parse_args(argv)

    if args.command == "plan":
        return cmd_plan(args.text)
    if args.command == "clear":
        return cmd_clear()
    if args.command == "export":
        return cmd_export(Path(args.path))
    if args.command == "eval":
        return cmd_eval(args.eval_command)
    return 2  # unreachable: subparsers are required
