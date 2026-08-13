"""AI boundary: raw user text + current board -> validated edit ops.

The ONLY module that talks to the model. Fork B changes what crosses the wire in
both directions:

* IN  — not just the user's line, but the *current board* (each task with its id).
  The model needs to see what exists so it can reference the right task when the
  user says "the gym" or "that report thing". Resolving a fuzzy phrase to a
  specific id is language understanding — the model's job.
* OUT — a list of edit `Op`s (add / remove / move / set_duration), never a task
  list. The model decides *what* to change; deterministic code (`apply.py`) does
  the changing.

It understands language; it never schedules, never does arithmetic, and never
mints an id — it may only reference ids that appear on the board it was shown.
"""

from collections.abc import Callable

from ollama import chat

from .models import OpList, Op, Task

MODEL = "qwen3.5:9b"

_SYSTEM_PROMPT = """\
You edit a user's day plan. Each turn you receive the CURRENT BOARD (the tasks
that already exist, each with a numeric id) and a new message from the user. You
translate that message into a list of edit operations.

Your ONLY job is to understand what the user wants and record it as operations.
You must NOT schedule, order, or do any arithmetic beyond converting durations.

Operations:
- add: create a new task. Give name, duration_minutes, optional fixed_start,
  priority. Do NOT give an id — the system assigns it.
- remove: delete an existing task. Give its id from the board.
- move: pin an existing task to a new clock time. Give its id and fixed_start.
- set_duration: change how long an existing task takes. Give its id and
  duration_minutes.

Rules:
- When the board is empty, everything the user mentions is an "add".
- To change, move, or remove a task, find it on the board and use its id. NEVER
  invent an id and NEVER use an id that is not on the board.
- If the user refers to a task loosely ("the gym", "that report"), match it to
  the task on the board it most likely means, and use that id.
- duration_minutes: convert any stated duration to minutes ("2 hours" -> 120).
- fixed_start: 24-hour "HH:MM" ("3pm" -> "15:00"). For "add", leave it null if
  the user gave no time. Never invent a time.
- priority: user's wording ("urgent", "important" -> high; "whenever", "if I
  have time" -> low). Default to medium.
- Emit an empty list of ops if the user's message asks for no change.
"""


def _render_board(tasks: list[Task]) -> str:
    """Render the current board as text the model can reference by id.

    This is the new *input* Fork B feeds the model each turn. Without it the
    model could not resolve "the gym" to a specific id.
    """
    if not tasks:
        return "CURRENT BOARD: (empty)"
    lines = ["CURRENT BOARD:"]
    for t in tasks:
        when = f"fixed at {t.fixed_start}" if t.fixed_start else "flexible"
        lines.append(
            f"  [id={t.id}] {t.name} — {t.duration_minutes} min, "
            f"{when}, priority {t.priority}"
        )
    return "\n".join(lines)


def _require_all(schema: object) -> object:
    """Recursively mark every object's properties as ``required``.

    Ollama's constrained decoding follows the JSON schema literally, and Pydantic
    marks any field with a default — like the ``op`` discriminator — as optional.
    The model then drops ``op`` on later array elements and the discriminated
    union has no tag to switch on (``union_tag_not_found``). Forcing every
    property required makes the model always emit the discriminator (and every
    other key), which is exactly what constrained decoding needs. This rewrites
    only the schema handed to the model; result validation still uses the real
    Pydantic types, so the Python-side defaults remain for ergonomics.
    """
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            schema["required"] = list(schema["properties"])
        for value in schema.values():
            _require_all(value)
    elif isinstance(schema, list):
        for item in schema:
            _require_all(item)
    return schema


def _drop_patterns(schema: object) -> object:
    """Recursively strip ``pattern`` constraints from a JSON schema.

    Ollama compiles the schema into a sampling grammar, and that compiler has no
    regex support: a single ``pattern`` anywhere fails the entire request with
    ``failed to parse grammar`` (HTTP 400). The constraint is not lost — it is
    still enforced Python-side when the response is validated against the real
    Pydantic types — it just cannot be enforced *during* generation, so a
    malformed time surfaces as a rejected turn instead of an impossible one.

    Same lesson as :func:`_require_all`: the schema Pydantic emits and the schema
    Ollama can compile are not the same document.
    """
    if isinstance(schema, dict):
        schema.pop("pattern", None)
        for value in schema.values():
            _drop_patterns(value)
    elif isinstance(schema, list):
        for item in schema:
            _drop_patterns(item)
    return schema


# Built once: the hardened schema Ollama is constrained to. Both transforms are
# about what the grammar compiler can accept, not about what the data means.
_OPS_SCHEMA = _drop_patterns(_require_all(OpList.model_json_schema()))


def produce_ops(
    text: str,
    tasks: list[Task],
    on_progress: Callable[[str], None] | None = None,
) -> list[Op]:
    """Send the board + user text to the model and return validated edit ops.

    Streams the response so the caller can show live progress via ``on_progress``
    (called with each token chunk). Latency is kept low by disabling the model's
    reasoning pass (``think=False``) and keeping it warm between turns.

    Raises pydantic.ValidationError if the assembled output does not match the
    schema (constrained decoding makes this rare).
    """
    board = _render_board(tasks)
    buffer: list[str] = []
    for part in chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{board}\n\nUSER MESSAGE:\n{text}"},
        ],
        format=_OPS_SCHEMA,
        options={"temperature": 0},
        think=False,
        keep_alive="30m",
        stream=True,
    ):
        chunk = part.message.content
        if chunk:
            buffer.append(chunk)
            if on_progress is not None:
                on_progress(chunk)

    return OpList.model_validate_json("".join(buffer)).ops
