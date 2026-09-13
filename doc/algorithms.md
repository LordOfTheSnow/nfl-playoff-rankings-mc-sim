# Algorithms

[← Back to README](../README.md) | [Technical Details](technical.md)

This document describes the core algorithms powering the NFL Monte Carlo Playoff Ranking Simulator.

## Team Strength Ratings

The simulator computes team strength using an iterative strength-of-schedule algorithm. Ratings reflect not just win percentage, but the quality of opponents beaten.

### Algorithm Overview

```
┌─────────────────────────────────────────────────────────┐
│  1. Initialize ratings from win percentages (avg = 1.0) │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  2. Compute new ratings:                                │
│     rating = Σ(opp_rating for wins) / Σ(all opp_rating) │
│     (ties count as half credit)                         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  3. Normalize so league average = 1.0                   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  4. Relaxation: blend 50% new + 50% previous            │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  5. Converged? (max |new − old| < 0.001)                │
│         │ NO                        │ YES               │
│         ▼                           ▼                   │
│     Go to step 2              Apply Bayesian dampening  │
└─────────────────────────────────────────────────────────┘
```

### Iterative Computation

1. Initialize all teams with win-percentage-based ratings (normalized to average 1.0)
2. For each iteration:
   - Compute each team's new rating as a weighted win ratio: wins against strong opponents count more than wins against weak ones
   - Rating = (sum of opponent ratings for wins) / (sum of all opponent ratings)
   - Ties contribute half credit
3. Normalize ratings so the league average stays at 1.0
4. Apply relaxation: blend 50% new ratings with 50% previous ratings to prevent oscillation
5. Check convergence: if max |new - old| < 0.001, stop

The relaxation step is critical. Without it, the interdependent ratings form feedback loops (beating a strong team raises your rating, which raises theirs for having played you) that cause oscillation rather than convergence.

### Bayesian Dampening

After convergence, ratings are dampened toward the league average (1.0) based on sample size:

```
dampened = (games / (games + K)) * raw_rating + (K / (games + K)) * 1.0
```

With K=8 (default):

| Games Played | Weight on Calculated | Weight on Average | Effect |
|:---:|:---:|:---:|---|
| 2 | 20% | 80% | Mostly regression to mean |
| 8 | 50% | 50% | Equal blend |
| 17 (full season) | 68% | 32% | Mostly earned rating |

This prevents unrealistic extreme ratings early in the season when a 2-0 start against weak opponents could otherwise produce inflated playoff probabilities.

### Output

Ratings are normalized so the average across all teams is 1.0. A rating of 1.5 means that team is estimated to be 50% stronger than average; 0.7 means 30% weaker. These ratings are used as inputs to the Monte Carlo simulation to set win probabilities for unplayed games.

---

## Cutoff Week

`cutoff_week` is the boundary between "real results" and "simulated outcomes": for a given request, `_partition_games` (`src/simulator.py`) fixes every game in week 1..`cutoff_week` whose status is `COMPLETED` to its real result, and simulates everything else — games not yet decided within those weeks, plus every game in a week beyond `cutoff_week` regardless of status. This is a per-game check, not a per-week one: a cutoff week can be (and usually is) only partially played, and the games in it that already happened are still used as real results.

### Auto-detection

When a request omits `cutoff_week`, `_auto_detect_cutoff_week` (`src/simulator.py`) resolves it to **the highest week number containing at least one `COMPLETED` game** (0 if none has completed yet). It doesn't require the whole week to be finished — the per-game partitioning above already handles a mixed week correctly, so auto-detection just needs to reach that week at all. This is what lets a single already-decided week-1 game feed into that week's simulation immediately, rather than being ignored until all of that week's games are final.

This is the single shared implementation used everywhere a cutoff needs to be auto-detected: the simulator itself, and the `GET /api/cp-clinch/{team}`, `GET /api/cp-clinch-all`, `GET /api/clinch-estimate`, and `POST /api/clinching-scenarios` endpoints when they're called without an explicit `cutoff_week`.

`GET /api/status` exposes this resolved value as `auto_cutoff_week`, plus a `completed_per_week` breakdown (completed-game count per week) — together these let the frontend show what "Auto" will actually simulate at, and preview exactly how many games that implies, without duplicating the auto-detection logic itself. This is distinct from `weeks_completed` (a count of weeks that are *entirely* finished), which is a separate, coarser stat.

---

## Tie Probability Estimation

Each simulated game is a strength-weighted win/loss draw (see `_simulate_game_standalone` in `src/simulator.py`) — the model has no notion of a score margin, so a tie can't fall out of it on its own. A small slice of the random roll is reserved for "tie" before the win/loss split is computed, controlled by `tie_probability`.

### Default: empirical estimate

Rather than a fixed guess, `tie_probability` defaults to an estimate derived from real game data, pooled from two sources:

1. **Prior complete seasons** — every season in the cache with no games still SCHEDULED or IN_PROGRESS (a POSTPONED/CANCELLED game, e.g. a suspended-and-never-resumed game, counts the season as over too — it just contributes no game/tie count of its own, since it has no score). Pooled across *all* such seasons (not just the two most recent) since NFL ties are rare (~0.5%) and a small sample is dominated by noise. Persisted in the `tie_stats` SQLite table (`Cache.store_tie_stats`/`get_tie_stats`) and recomputed whenever new data is fetched (`POST /api/fetch-data`) or the active season changes (`POST /api/set-season`) — see `compute_prior_seasons_tie_pool` in `src/simulator.py`.
2. **The active season's own completed games, truncated at `cutoff_week`** — added in live per request, never including games beyond the cutoff. This matters for retroactively simulating an already-finished season at an earlier cutoff: only that season's games through the cutoff count, not the full season.

The two are combined as `(prior_ties + current_ties) / (prior_games + current_games)` — see `resolve_tie_probability` in `src/simulator.py`. At least 2 complete prior seasons must be cached before the estimate is trusted; otherwise `tie_probability` falls back to a hardcoded 0.5% (`DEFAULT_TIE_PROBABILITY`).

The active season is excluded from its own persisted pool (step 1) specifically so its cutoff-truncated contribution (step 2) isn't double-counted or leaked past the cutoff.

### Override

Both `POST /api/simulate` and `POST /api/clinching-scenarios` accept an explicit `tie_probability` (0.0-1.0), overriding the empirical estimate entirely — exposed as the Tie Probability slider on the Simulations page, next to Noise. `GET /api/status`'s `default_tie_probability` field reports what the empirical estimate currently resolves to, so the frontend can seed the slider with it.

---

## Clinching Scenarios Solver

When viewing simulation results, clicking a team with playoff probability between 0% and 100% shows a "Clinching Scenarios" button. This computes all minimal sets of game-outcome conditions that guarantee the team a playoff spot. Available after week 14 only.

### Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. Identify contenders (same-conference, not eliminated)         │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. Prune to relevant games (at least one contender involved)     │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. Group by target team's own remaining record (e.g., 3-1, 2-2)  │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. For each possible record, find qualifying universes:          │
│                                                                  │
│    ┌───────────────────────────┐  ┌────────────────────────────┐ │
│    │ other games ≤ 13?         │  │ other games > 13?          │ │
│    │ → Full enumeration        │  │ → Strength-weighted MC     │ │
│    │   (3^N outcomes)          │  │   (10,000 trials/combo)    │ │
│    └───────────────────────────┘  └────────────────────────────┘ │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ 5. Reduce to strictly minimal condition sets                     │
│    (every condition is necessary — removing any one breaks it)   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│ 6. Deduplicate and sort by fewest conditions first               │
└──────────────────────────────────────────────────────────────────┘
```

### How to Read the Results

- Results are grouped by the team's possible finish (e.g., "Finish 3-1" means the team wins 3 and loses 1 of their remaining games)
- Each scenario within a group lists the specific other-game outcomes required
- **Fewer conditions = simpler path** — scenarios are sorted simplest first
- **"No path to playoffs"** means no combination of other results can save the team with that record
- **"Clinches regardless"** means the team's own record alone is enough, no matter what else happens

### Limitations

- Only available after week 14 (hard gate) — earlier in the season the game space is too large for useful results
- When Monte Carlo sampling is used (> 13 relevant games), results may not be exhaustive
- Ties are included as possible outcomes, which increases the combinatorial space

---

## CP Solver — Mathematical Clinching & Elimination

The CP solver uses [Google OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver) to determine whether an NFL team has **mathematically clinched** or been **mathematically eliminated** from playoff contention. Unlike the Monte Carlo simulation (which estimates probabilities) or the clinching scenarios solver (which enumerates paths after week 14), the CP solver provides deterministic, provably correct answers — available from week 1 onward.

### What It Answers

| Status | Meaning |
|---|---|
| **Clinched** | No possible combination of remaining game outcomes can prevent this team from making the playoffs |
| **Eliminated** | No possible combination of remaining game outcomes can result in this team making the playoffs |
| **Alive** | Neither clinched nor eliminated — the team's fate still depends on future results |

### The Hybrid Approach

NFL tiebreakers are deeply conditional (head-to-head, common games, strength of victory, division/conference record, net points — roughly 11 steps). Encoding them as linear constraints would be impractical. Instead the solver uses a hybrid strategy:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CP-SAT + Standings Hybrid                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────┐    ┌──────────────────────────────────┐  │
│  │     CP-SAT Layer          │    │     Standings Engine Layer       │  │
│  │                           │    │                                  │  │
│  │  • Win/loss/tie counts    │    │  • Full tiebreaker logic         │  │
│  │  • Record bounds          │    │  • Head-to-head records          │  │
│  │  • Simple dominance       │    │  • Common games                  │  │
│  │  • W + L + T = 17         │    │  • Strength of victory/schedule  │  │
│  │  • Constraint propagation │    │  • Net points                    │  │
│  │                           │    │  • compute_standings()           │  │
│  │  Prunes impossible        │    │  • determine_playoff_bracket()   │  │
│  │  combinations FAST        │    │  Validates actual bracket result │  │
│  └─────────────┬─────────────┘    └───────────────┬──────────────────┘  │
│                │                                   │                     │
│                └──────────────┬────────────────────┘                     │
│                               │                                         │
│                               ▼                                         │
│                    ┌─────────────────────┐                              │
│                    │ Clinched / Eliminated│                              │
│                    │ / Alive             │                              │
│                    └─────────────────────┘                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

1. **CP-SAT handles the arithmetic** — win/loss/tie counts, record bounds, and simple dominance relationships are modeled as integer constraints.
2. **The existing standings engine handles tiebreakers** — for each candidate assignment that passes CP-SAT filtering, the full `compute_standings()` + `determine_playoff_bracket()` pipeline validates whether the target team actually makes or misses the bracket.
3. **Best of both worlds** — CP-SAT's constraint propagation prunes impossible record combinations early, while the standings engine handles the complex conditional logic that constraints can't express.

### Why It's Fast (3.4 x 10^30 -> 28ms)

At cutoff week 14, there are 64 remaining games. Brute-force enumeration would require checking 3^64 ~ 3.4 x 10^30 possible outcome combinations. The solver finishes in tens of milliseconds through three key techniques:

#### 1. Record Group Decomposition

```
                    Target team has 4 remaining games
                                  │
                    ┌─────────────┼─────────────────┐
                    │             │                  │
                    ▼             ▼                  ▼
              ┌──────────┐ ┌──────────┐       ┌──────────┐
              │ 4-0-0    │ │ 3-1-0    │  ...  │ 0-4-0    │
              │ (1 combo)│ │ (4 combo)│       │ (1 combo)│
              └──────┬───┘ └──────┬───┘       └──────┬───┘
                     │            │                   │
                     ▼            ▼                   ▼
              Solve: "Given    Solve: "Given      Solve: "Given
              10-7 finish,     9-8 finish,        6-11 finish,
              any assignment   any assignment     any assignment
              of 60 other      of 60 other        of 60 other
              games where      games where        games where
              team misses?"    team misses?"      team misses?"
```

Instead of exploring the full outcome space, the solver decomposes by the target team's possible final record. With 4 remaining games, there are only 15 possible final records (the formula is (N+1)(N+2)/2). Each record becomes a separate, tractable subproblem.

#### 2. CP-SAT Constraint Propagation

Each subproblem has ~64 game variables (domain {0,1,2}). CP-SAT doesn't enumerate them — it propagates constraints:
- **W + L + T = 17** for every team arithmetically locks many variables
- **Target team record is fixed** — e.g., Panthers must finish 10-7-0, so their 4 game outcomes are heavily constrained
- **Dominance bounds** prune teams that can't possibly reach 7th place by wins alone

Through arc consistency and domain reduction, OR-Tools eliminates vast swaths of the search space without generating a single solution. Many record groups are proved INFEASIBLE instantly via propagation alone.

#### 3. Early Termination

The solver needs exactly **one witness** to answer each question:
- **Elimination check**: finds one assignment where the team makes playoffs -> not eliminated (stop)
- **Clinch check**: finds one assignment where the team misses playoffs -> not clinched (stop)

In practice, most teams are resolved in 1-2 record groups out of 15+.

### Real Example

| Metric | Value |
|---|---|
| Season 2025, cutoff week 16 | All 32 teams |
| Remaining games per team | 2 (32 total conference games) |
| Brute-force space | 3^32 ~ 1.85 x 10^15 |
| Total solve time | 0.3 seconds |
| Method | 2 CP-SAT Solve() calls per team, pure infeasibility |

### API Endpoints

- `GET /api/cp-clinch/{team}?cutoff_week=N&time_limit=S` — single team clinch/elimination status
- `GET /api/cp-clinch-all?cutoff_week=N` — all 32 teams, grouped by conference
