# Clinching Solver: Duplicated Game-Simulation Logic

[← Back to README](../README.md) | [Algorithms](algorithms.md) | [Technical Details](technical.md)

**Status:** Investigation complete, fix not yet implemented. Logged for a future session
(see the README `## ToDo` entry). No functional bug was found — this is a maintainability /
drift-risk finding, not a correctness incident.

## Summary

`src/clinching.py`'s Monte Carlo sampling path (used when the clinching solver falls back
from exhaustive enumeration) reimplements the exact same per-game outcome algorithm that
already exists in `src/simulator.py`, as an independent, hand-copied function. This surfaced
while adding the shared `noise` parameter to the clinching solver (see `CHANGELOG.md` /
recent commits): the clinching solver's own noise handling had been silently ignoring
whatever the user configured on the Simulations page, because it read from a private module
constant instead of the shared setting. The same investigation found a second, still-unfixed
instance of the identical problem: **tie probability**.

## Finding 1: Two independent `TIE_PROBABILITY` constants (unfixed)

| | Location | Value | User-configurable? |
|---|---|---|---|
| Main simulator | `src/simulator.py:72`, `SimulationConfig.tie_probability` | `0.005` (default) | **No** — not read from the `POST /api/simulate` request body anywhere in `src/server.py`. Always the dataclass default. |
| Clinching solver | `src/clinching.py:60`, `TIE_PROBABILITY` | `0.005` | **No** — module-level constant, no parameter threads into it at all. |

Both currently hold the identical literal `0.005`, so today the two solvers *happen* to
agree. But they are two independently-maintained numbers standing in for the same
real-world assumption (the empirical NFL tie rate), with no shared source of truth. If
either value is ever tuned — e.g. `tie_probability` becomes a real, user-facing
`/api/simulate` parameter, the same way `noise` now is — the two solvers would silently
diverge again, exactly the class of bug just fixed for `noise` (see Finding 2 for why this
one is a bit more than a one-line constant fix).

**User's framing (worth preserving verbatim for the next session):** *"I always thought a
tie is just a possible outcome of a simulation"* — i.e. the expectation is that tie
probability should fall naturally out of the per-game outcome model (strength-weighted
win/loss draw), not be injected as a separate, independently-tuned constant bolted onto the
side of it. That's a legitimate design question beyond just deduplicating two `0.005`
literals — see the recommendation below.

## Finding 2: Duplicated per-game outcome function

The actual root cause of Finding 1 is that `clinching.py` does not call into `simulator.py`
at all for its sampling — it maintains a full second copy of the algorithm:

- `src/clinching.py:314`, `_simulate_game_outcome(game, strengths, noise)` — uses the
  **global `random` module** directly (`random.random()`, `random.lognormvariate(...)`),
  reads `TIE_PROBABILITY` from its own module constant.
- `src/simulator.py:207`, `_simulate_game_standalone(home_team, away_team, strengths,
  tie_prob, noise, rng)` — takes an **explicit `rng: random.Random` parameter**, and
  `tie_prob`/`noise` are passed in from `SimulationConfig` rather than hardcoded.

Both implement the identical math:

```python
roll = <random draw>
if roll < tie_prob:
    return tie
home_strength *= <log-normal jitter by noise>
away_strength *= <log-normal jitter by noise>
home_win_prob = home_strength / (home_strength + away_strength)
threshold = tie_prob + (1 - tie_prob) * home_win_prob
return home if roll < threshold else away
```

Any future change to this algorithm (home-field advantage, a different noise
distribution, a different tie model, a bug fix) has to be made **twice**, in two files, with
no test or type system flagging a missed spot. This is the real fix the two hardcoded
constants are a symptom of.

## Investigated and ruled out: multiprocessing RNG correlation

While investigating *why* `clinching.py` might have its own copy instead of reusing
`simulator.py`'s function, the leading hypothesis was that `simulator.py`'s explicit
`rng: random.Random(seed)`-per-worker exists because `clinching.py`'s bare use of the
global `random` module inside `multiprocessing.Pool` workers (`_process_team_record_batch`,
dispatched via `Pool(processes=num_workers).map(...)`, no `Pool` context specified) could
produce **correlated random sequences across forked workers** — a classic multiprocessing
footgun (child processes inherit the parent's RNG state at fork time).

**This was verified empirically and ruled out.** CPython's `random` module protects against
exactly this, unconditionally, for every process that forks (confirmed in
`/usr/lib/python3.14/random.py:1008-1009`):

```python
if hasattr(_os, "fork"):
    _os.register_at_fork(after_in_child=_inst.seed)
```

Every forked child (via `os.fork`, `multiprocessing.Pool` with `fork` *or* `forkserver`)
automatically reseeds the global `random` instance from fresh OS entropy immediately after
forking. Verified with a standalone repro script: 4 `Pool` workers × 3 runs, under both the
system default `forkserver` start method and an explicit `fork` context — always 4/4
independent sequences, zero collisions. `clinching.py`'s reliance on the bare global
`random` module is safe. `simulator.py`'s explicit per-worker `random.Random(seed)` is not
compensating for a bug that exists elsewhere in this codebase — it's just a more explicit
pattern that predates or doesn't rely on that stdlib guarantee.

**Why this matters for the fix below:** consolidating the two implementations does not need
to preserve `simulator.py`'s explicit-`rng` calling convention for correctness reasons. It's
still fine to keep it (it makes the RNG dependency visible in the function signature, which
is good practice independent of the fork question) — just noting that "the fork-safety
concern" isn't a constraint the consolidation has to route around.

## Recommendation for next session

1. **Minimum fix:** delete `clinching.py`'s private `_simulate_game_outcome` and
   `TIE_PROBABILITY`/`SAMPLING_NOISE` constants; have `clinching.py`'s sampling call
   `simulator.py`'s `_simulate_game_standalone` (or a renamed, shared export of it) directly,
   passing `noise` (already threaded through as of this session) and `tie_probability`
   through the same call chain. One implementation, one constant, used by both solvers.
2. **Where to source `tie_probability` from:** decide whether it stays a fixed constant
   (moved to one shared location, e.g. `simulator.py`'s module scope or a small shared
   `constants.py`) or becomes a real parameter — the user's framing above ("a tie is just a
   possible outcome") suggests the expectation is the former is fine *as long as it's not
   duplicated*, not that it necessarily needs a UI control. Worth a quick product decision
   before implementing, since exposing it as a control (like `noise`) is a bigger scope than
   just deduplicating it.
3. **Mechanical concerns to check during implementation:**
   - `clinching.py` currently imports nothing from `simulator.py`; confirm no circular
     import (`simulator.py` does not currently import from `clinching.py`, so this should be
     one-directional and safe, but verify).
   - `_simulate_game_standalone` requires an explicit `rng: random.Random` instance;
     `clinching.py`'s worker function (`_process_team_record_batch`) would need to construct
     one per worker (e.g. `random.Random()` unseeded — safe per the fork investigation above
     — or seeded for reproducibility if that's ever wanted for tests).
   - Re-run `tests/test_clinching_tiebreakers.py` (uses real 2024 season data) after the
     change to confirm scenario output is unaffected.
