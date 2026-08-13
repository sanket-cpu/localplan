# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this project is

Localplan is a local-first CLI planning assistant built on an offline small
language model (via Ollama). The core claim under test:

> An LLM can be trusted to parse intent and narrate results, but not to
> compute anything. Deterministic Python owns all arithmetic. The eval
> harness exists to measure whether that boundary actually holds — across
> models, quant levels, and adversarial inputs — not to produce a leaderboard.

Everything in this repo serves that claim. If a proposed change doesn't
serve the planner, the trust boundary, or the eval harness that measures it,
it's out of scope — flag it rather than building it.

**Current state: partially built.** Some layers below may be stubbed,
incomplete, or missing entirely — don't assume anything is finished because
it's described here. See "Current build status" for what's actually done.
This file describes the full intended build, not just the eval harness.

## Current build status

Source of truth for what's actually implemented. Update this section
whenever a layer's status changes — don't let it drift from the code.

| Layer | Status | Notes |
|---|---|---|
| 0. Contracts (Pydantic models) | **complete** | Built as an *ops* design: `Op`/`OpList`, `Task`, `PlannerState`, `ScheduledBlock`, `Schedule` in `models.py`. Does **not** use the `PlanRequest`/`TimeBlock`/`Conflict`/`PlanResult` names this doc specifies — the shape diverges, not just the names. |
| 1. Intent extraction (LLM → `PlanRequest`) | **complete** | `extract.py` — the only module importing `ollama`. Emits validated edit **ops**, not a `PlanRequest`. Grammar-constrained JSON via Ollama's `format`. |
| 2. Deterministic planner | **complete** | `planner/` package: `apply.py` (op-applier) + `scheduler.py` (time/conflict math). 52 passing unit tests, zero model calls. |
| 3. Narration (LLM) | **not started** | No LLM narration layer exists. Output is rendered deterministically by `cli.py` / `export.py`. This is the trust-boundary centerpiece in this doc — currently absent. |
| 4. Numeric validator | **not started** | Not built. Depends on Layer 3 existing first. |
| CLI entry point | **complete** | Multi-turn REPL in `cli.py`, **not** the single-shot `localplan plan/eval` subcommand shape this doc specifies. |
| 5. Eval harness | **not started** | Not built. README lists an eval set as the next roadmap item. |

Before doing any work in a session, check this table against the actual
code (not against memory of a past session) and correct it if it's stale.

## Architecture — five layers, hard walls between them

1. **Contracts** — every object crossing a layer boundary is a validated
   Pydantic model (`PlanRequest`, `Task`, `TimeBlock`, `Conflict`,
   `PlanResult`). Nothing crosses a boundary as a raw dict.
2. **Intent extraction (LLM)** — natural language → `PlanRequest`.
   Grammar-constrained JSON via Ollama's schema support.
3. **Planner (pure Python, zero LLM calls)** — date/duration arithmetic,
   ordering, conflict detection, capacity checks. Fully unit-tested.
   **No model output ever enters this layer's logic.**
4. **Narration (LLM)** — `PlanResult` → prose. The model's only job is to
   describe values that already exist in its input. It does not compute.
5. **Numeric validator** — every numeric token in the narration must trace
   back to a value in `PlanResult`. Unaccounted-for numbers → reject →
   retry → fail gracefully if retries are exhausted.

Layer 3 and Layer 5 are the trust boundary made physical. Treat their
correctness as the top priority in any change — a bug there invalidates the
project's central claim, not just a feature.

## Tech stack

- Python, `uv` for environment/dependency management
- Pydantic v2 for all cross-layer contracts
- Ollama (local), models tracked by explicit tag + digest, not `latest`
- Click or argparse for the CLI (pick one, stay consistent)
- pytest for unit tests, separate from the eval harness
- pandas/matplotlib (or plain csv + matplotlib) for eval reporting — no
  notebooks committed, only scripts that regenerate figures from CSV

## CLI shape

Single entry point, subcommands, no interactive-only flows:

```
localplan plan "<request text>"        # run the pipeline end to end
localplan eval run --config <path>     # run the eval harness sweep
localplan eval report                  # regenerate charts from CSVs
```

Config (model, quant tag, temperature, retry limit, keep_alive) lives in a
YAML/TOML file, not hardcoded flags scattered through the code. Every eval
run writes hardware, OS, and Ollama version into the output row —
reproducibility is a requirement, not a nice-to-have.

## Build order — core app before eval harness

The eval harness (Layer 5) measures the app; it can't be built or trusted
before the app it measures actually works. Build in this order, and don't
jump ahead to a later phase while an earlier one is still ☐ partial in the
status table above:

1. **Contracts (Layer 0).** Finalize `PlanRequest`, `Task`, `TimeBlock`,
   `Conflict`, `PlanResult` before writing logic that depends on them.
   Changing a contract later invalidates everything built on top of it.
2. **Planner (Layer 2), end to end, with unit tests.** This must be
   genuinely correct before anything else matters — see the build
   boundary section below. `pytest` must pass here before moving on.
3. **CLI entry point wired to the planner directly**, no LLM yet. Confirm
   `localplan plan` works on a hardcoded or manually-constructed
   `PlanRequest` before any model is in the loop.
4. **Intent extraction (Layer 1).** LLM → `PlanRequest`, grammar-constrained
   JSON via Ollama, Pydantic validation on the output.
5. **Narration (Layer 3).** `PlanResult` → prose.
6. **Numeric validator (Layer 4).** Reject/retry loop on top of narration.
7. **Eval harness (Layer 5).** Only once 1–6 are ☐ complete. Building the
   harness against a half-finished app produces numbers that measure bugs,
   not model behavior — don't do it out of order even under time pressure.

If asked to work on the eval harness while an earlier phase is still
partial, say so explicitly rather than proceeding.

## Build boundary — read this before touching these files

Some parts of this repo are intentionally hand-designed by the repo owner
as the core intellectual contribution of the project. For files under the
paths below, do not silently invent or change the underlying logic,
thresholds, or judgment calls. Implement what's specified, ask when a
judgment call isn't yet specified, and flag any change to existing logic
rather than applying it silently:

- `planner/` — the deterministic arithmetic and conflict-detection logic
  itself (not the Pydantic class boilerplate around it)
- `validator/` — the numeric-extraction and match/tolerance logic that
  decides what counts as a fabricated number
- `evals/fixtures/` — the 40 test cases and their gold answers
- `evals/scoring/` — the semantic-match and fabrication-match thresholds

Everywhere else — CLI plumbing, the Ollama HTTP wrapper, CSV writers,
chart scripts, Pydantic field syntax once the schema is decided — build
freely and move fast. That code should still be explainable on request,
but it isn't where the project's judgment lives.

## Eval harness conventions

- Fixture split: ~18 normal, ~12 edge (DST, midnight boundary, zero
  duration, impossible/empty input), ~10 adversarial (prompts that tempt
  the model into doing arithmetic itself — the highest-value category,
  do not water these down)
- Metrics in four tiers, always reported separately, never collapsed into
  one score:
  1. Syntactic validity (schema match)
  2. Semantic field accuracy
  3. Numeric fidelity (fabrication rate) — the headline metric
  4. Operational (TTFT, decode tok/s, memory, retries, cold vs warm) —
     pull from Ollama's native fields (`prompt_eval_count`,
     `prompt_eval_duration`, `eval_count`, `eval_duration`), never derive
     from wall-clock timing
- Report effective p95 latency *including* retries, not just per-call
  latency
- Include a nondeterminism check: N=5 identical calls at temperature 0,
  logged as a distinct metric, not swept under "variance"
- Randomize/interleave run order across a long sweep; include warmup runs
  before recording — do not let thermal throttling silently corrupt
  later rows in a sweep

## Testing

- `planner/` and `validator/` get ordinary pytest unit tests with known
  inputs/outputs — these must pass before any eval work is trusted
- Eval harness runs are not unit tests — don't conflate the two, and don't
  let eval flakiness block `pytest`

## What not to do

- Don't add planning features beyond what already exists. Scope is frozen
  during the eval-harness build.
- Don't let the LLM touch Layer 3 logic under any framing, including
  "just double-checking the math."
- Don't build a provider-agnostic or multi-app benchmarking framework.
  This harness measures Localplan, not LLMs in general.
- Don't commit notebooks as the source of truth for a figure — scripts
  only, regenerable from committed CSVs.
- Don't claim determinism anywhere (README, docstrings, comments) — temp-0
  Ollama output is not guaranteed identical across runs; report the
  measured nondeterminism rate instead.

## Session start checklist

1. Check the "Current build status" table against the actual code (grep
   for stubs/TODOs, check what has tests, run the CLI manually) — don't
   trust the table if it looks stale, and correct it before proceeding.
2. Work on the earliest ☐ partial or ☐ not started layer in the build
   order, not whatever seems most interesting — don't skip ahead to the
   eval harness while earlier layers are incomplete.
3. Confirm `pytest` passes on `planner/` and `validator/` before adding
   eval code on top of them.
4. Check which Ollama model tags are actually pulled and what quant they
   resolve to (`ollama show <model>`) — do not assume a tag is
   unquantized.
5. If touching anything under the build-boundary paths above, summarize
   the intended change and confirm before writing it.
6. Before ending the session, update the status table for any layer whose
   state changed.