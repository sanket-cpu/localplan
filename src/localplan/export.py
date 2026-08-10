"""Export a finished schedule to Markdown — pure, deterministic, zero deps.

Same data as the terminal render, in a portable format. PDF is the stretch goal;
because this stays a pure ``Schedule -> str`` function, PDF later is just "render
the same blocks a different way" and nothing upstream has to change.
"""

from .models import Schedule


def to_markdown(schedule: Schedule) -> str:
    """Render a schedule as a Markdown document."""
    lines = ["# Your day", ""]

    if schedule.blocks:
        for block in schedule.blocks:
            tag = " _(flexible)_" if block.kind == "flexible" else ""
            lines.append(
                f"- **{block.start:%H:%M}–{block.end:%H:%M}** "
                f"{block.name}{tag}"
            )
    else:
        lines.append("_Nothing scheduled._")

    if schedule.conflicts:
        lines += ["", "## Conflicts (not resolved)", ""]
        lines += [f"- {c}" for c in schedule.conflicts]

    if schedule.unscheduled:
        lines += ["", "## Could not fit", ""]
        lines += [f"- {name}" for name in schedule.unscheduled]

    return "\n".join(lines) + "\n"
