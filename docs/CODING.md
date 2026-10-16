# Coding rules

The goal is clean code that a human can read without help. Prefer clear names and small functions over comments. Enforce with `uv run ruff check .` and `uv run ruff format .` before finishing any change.

## Comments

Comments are rare and always one line.

1. At most one `#` line, placed directly above the function, class, or statement it describes.
2. Only add a comment when the name and the code cannot say it: a non-obvious reason, a unit, a library quirk, or a financial convention.
3. No trailing comments at the end of a code line.
4. No multi-line comment blocks, no multi-line docstrings, no banner or divider comments.
5. No commented-out code. Delete it; git remembers.
6. No comments that restate the code (`# increment i`).

```python
# sum two numbers
def sum_two(a: float, b: float) -> float:
    return a + b
```

A comment that explains why is worth keeping:

```python
# GTX is post-only, so the strategy can never pay taker fees
hbt.submit_buy_order(0, order_id, price, qty, GTX, LIMIT, False)
```

If a function needs more than one line to explain, it is doing too much or is poorly named. Fix that instead of writing more comment.

## Naming

- `snake_case` for functions, variables, modules; `PascalCase` for classes; `UPPER_CASE` for constants.
- Names say what the thing is, not how it is built: `half_spread_ticks`, not `hs` or `x`.
- Put the unit in the name when it is not obvious: `step_ns`, `horizon_s`, `fee_bps`, `price_tick`.
- Booleans read as questions: `is_filled`, `has_position`.
- No single-letter names except short loop indices and the math symbols documented in plan.md Section 5 (`s`, `q`, `k`, `A`) inside formula code.

## Structure

- One function does one thing. Aim for under about 30 lines; split when it grows.
- Prefer early returns over deep nesting (three levels is the limit).
- No magic numbers. Name them as constants or put them in the config.
- Keep modules focused. Follow the layout in [INFRASTRUCTURE.md](INFRASTRUCTURE.md); do not add top-level folders without updating it.
- No dead code, no unused imports, no speculative abstractions. Build what the current phase needs.
- Three similar lines are better than a premature helper.

## Types and data

- Type-hint every function signature (arguments and return).
- Config and run metadata use pydantic models (`mmlab/config.py`), not loose dicts.
- Tabular data uses Polars. Numeric kernels use NumPy arrays inside Numba.
- Paths use `pathlib.Path`, never string concatenation.
- Timestamps are integer nanoseconds unless a name says otherwise.

## Errors

- Fail loudly. Do not swallow exceptions, and do not add fallbacks that hide a failure.
- Catch an exception only to add context or to write a failed run status, then re-raise.
- Validate inputs at the boundary (config load, file load). Trust internal calls.
- Raise specific exceptions with a message that names the bad value.

## Numba and hftbacktest

- Strategy loops are `@njit`. Keep them free of Python objects, I/O, and pydantic; pass plain numbers and preallocated arrays.
- Do not guess hftbacktest API names. Check the docs or the installed source first (the installed version is in `uv.lock`).
- A backtest object cannot be reused. Build a fresh one per run.
- Always quote post-only (`GTX`) as a market maker.

## Causality and correctness

- Any feature, signal, volatility, or calibration at time `t` uses only data at or before `t`.
- Work in ticks internally; convert to price only at the order boundary.
- A suspiciously good backtest is a bug until proven otherwise (plan.md Section 9 lists the checks).

## Tests

- Every feature ships with a test, written before or together with it.
- Tests live in `tests/`, named `test_<topic>.py`, run with `uv run pytest`.
- Tests are deterministic: fixed seeds, tiny hand-built inputs with known answers.
- The sanity tests in plan.md Section 9 gate each phase.

## Documentation

- Every change updates the documentation in the same commit. The table in [AGENTS.md](../AGENTS.md) lists which file covers what.
- A change is not done until the docs match the code. Do not leave it for later.

## Git

- Small, focused commits with an imperative subject line.
- Never commit `data/`, `runs/`, `.venv/`, or secrets.
- Do not push without the user's approval.
