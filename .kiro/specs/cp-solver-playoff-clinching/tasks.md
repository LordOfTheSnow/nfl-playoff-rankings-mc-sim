# Implementation Plan: CP Solver for Playoff Clinching/Elimination

## Overview

Implement a CP-SAT based clinching/elimination solver using Google OR-Tools that determines whether NFL teams have mathematically clinched or been eliminated from playoff contention. The solver uses a hybrid approach: CP-SAT for arithmetic constraints and the existing standings engine for tiebreaker validation. Implementation includes the core solver module, cache integration, REST API endpoints, and frontend badge rendering.

## Tasks

- [x] 1. Set up dependency and project configuration
  - [x] 1.1 Add OR-Tools optional dependency to pyproject.toml
    - Add `[cp]` extras group with `ortools>=9.9`
    - Add `ortools>=9.9` to the existing `[dev]` extras group
    - _Requirements: 12.1, 12.2_

- [x] 2. Implement core CP solver module
  - [x] 2.1 Create `src/cp_solver.py` with data models and entry points
    - Implement `ClinchStatus` enum, `CPSolverResult` dataclass, `CPSolverConfig` dataclass
    - Implement `solve_clinch()` function signature with OR-Tools availability guard
    - Implement `solve_clinch_all()` function signature with parallel processing
    - Import guard: `try: from ortools.sat.python import cp_model` with `ORTOOLS_AVAILABLE` flag
    - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.1, 2.3, 2.4, 7.1, 7.5, 12.1, 12.2_

  - [x] 2.2 Implement record group generator
    - Implement `_generate_record_bounds()` that enumerates all (W, L, T) tuples for remaining games
    - Given N remaining games for target team, produce (N+1)(N+2)/2 distinct records
    - _Requirements: 3.1, 4.1, 4.2, 4.3_

  - [x] 2.3 Implement CP-SAT model builder
    - Implement `_build_cpsat_model()` that creates IntVars for each remaining game (domain {0,1,2})
    - Add constraints for win/loss/tie arithmetic per team: total_wins = fixed_wins + sum(game wins)
    - Add W+L+T = 17 constraint for each team
    - Add target team record forcing constraint
    - Add simple dominance bounds to prune teams that can't reach 7th place by wins alone
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2_

  - [x] 2.4 Implement PlayoffValidator callback
    - Create `PlayoffValidator` class as CP-SAT solution callback
    - Extract game outcomes from CP-SAT variable assignments
    - Call `compute_standings()` + `determine_playoff_bracket()` on each feasible assignment
    - Check if target team is in/out of playoff bracket
    - Support both clinch-check mode (search for team-misses) and elimination-check mode (search for team-makes)
    - _Requirements: 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 5.3, 5.4, 6.1, 6.2, 6.3, 6.4_

  - [x] 2.5 Implement solver orchestration and status determination
    - Wire record group generator → model builder → validator into `solve_clinch()`
    - Implement clinch check logic: for every record group, search for assignment where team misses
    - Implement elimination check logic: for every record group, search for assignment where team makes
    - Implement time limit enforcement with partial results on timeout
    - Implement magic number derivation from record group analysis
    - Implement `INCONCLUSIVE` status when solver times out
    - Reuse `identify_contenders` and `get_relevant_games` from `clinching.py`
    - _Requirements: 1.3, 1.4, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 7.1, 7.2, 7.3, 7.4, 9.5, 11.1, 11.2_

  - [x] 2.6 Implement bulk solver (`solve_clinch_all`)
    - Process all 32 teams using multiprocessing Pool
    - Individual team failures should not affect other teams
    - Group results by conference, sort alphabetically
    - _Requirements: 8.7, 8.8, 9.1, 9.2, 9.3, 9.4_

- [x] 3. Checkpoint - Ensure core solver tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement cache integration
  - [x] 4.1 Add `cp_solver_cache` table to `src/cache.py`
    - Add `CREATE TABLE IF NOT EXISTS cp_solver_cache` with (team, cutoff_week, season) PK
    - Add `store_cp_result()` method to serialize and store CPSolverResult as JSON
    - Add `get_cp_result()` method to retrieve and deserialize cached result
    - Add `invalidate_cp_cache()` method to delete all rows for a given season
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [ ]* 4.2 Write property tests for cache round-trip and invalidation
    - **Property 8: Cache Round-Trip**
    - **Property 9: Cache Invalidation**
    - **Validates: Requirements 13.1, 13.2, 13.3, 13.4**

- [x] 5. Implement REST API endpoints
  - [x] 5.1 Add `GET /api/cp-clinch/{team}` endpoint to `src/server.py`
    - Parse team from path, optional `cutoff_week` and `time_limit` query params
    - Validate team name (400 if invalid), cutoff_week range 1-18, time_limit range 1-300
    - Check OR-Tools availability (503 if not installed)
    - Check game data exists (409 if no data)
    - Auto-detect cutoff_week if omitted (latest fully completed week)
    - Check cache before running solver; store result after solving
    - Serialize `CPSolverResult` to JSON response
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 12.3, 12.4, 13.1, 13.2_

  - [x] 5.2 Add `GET /api/cp-clinch-all` endpoint to `src/server.py`
    - Accept optional `cutoff_week` and `time_limit` query params
    - Invoke `solve_clinch_all()` with parallel processing
    - Group results by conference (AFC/NFC), sort alphabetically
    - Include clinch status, solve_time_ms, num_variables, minimum_seed, magic_number per team
    - Return partial results if individual teams fail/timeout
    - _Requirements: 8.7, 8.8, 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 5.3 Add cache invalidation to `POST /api/fetch-data` handler
    - After successful game data fetch, call `invalidate_cp_cache()` for the active season
    - _Requirements: 13.3, 13.4_

- [x] 6. Checkpoint - Ensure API endpoints work correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement frontend integration
  - [x] 7.1 Add clinch/elimination badge rendering to standings view
    - Fetch `/api/cp-clinch-all` when standings are displayed
    - Render inline badge next to team name: green "Clinched", red "Eliminated", grey "Inconclusive"
    - Use existing Bootstrap 5 badge classes (`.badge.bg-success`, `.badge.bg-danger`, `.badge.bg-secondary`)
    - Graceful degradation: if endpoint returns error or 503, render standings without badges
    - _Requirements: 10.1, 10.2, 10.3, 10.5, 10.6_

  - [x] 7.2 Add popover with solver details on badge click
    - On badge click, show Bootstrap popover with solve_time_ms and num_variables
    - Handle interaction between CP solver badges and existing clinching scenario controls
    - Show scenario paths button alongside CP badge when both available (cutoff >= week 14)
    - Hide scenario paths button when cutoff < 14 (only CP badge visible)
    - _Requirements: 10.4, 11.3, 11.4, 11.5_

- [ ] 8. Implement property-based tests
  - [ ]* 8.1 Write property test for arithmetic consistency
    - **Property 1: Win/Loss/Tie Arithmetic Consistency**
    - For any assignment, W+L+T=17 for all teams
    - Use hypothesis strategies for generating valid game lists and outcome assignments
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

  - [ ]* 8.2 Write property test for outcome variable correctness
    - **Property 2: Outcome Variable Correctness**
    - Win → +1W for winner, +1L for loser; Tie → +1T for each team
    - **Validates: Requirements 4.5, 4.6**

  - [ ]* 8.3 Write property test for division winner invariant
    - **Property 3: Division Winner Invariant**
    - Each division has exactly 1 winner with best win%
    - **Validates: Requirements 5.1, 5.2**

  - [ ]* 8.4 Write property test for wild card selection invariant
    - **Property 4: Wild Card Selection Invariant**
    - Each conference has exactly 3 non-division-winner wild cards
    - **Validates: Requirements 6.1, 6.2**

  - [ ]* 8.5 Write property test for clinch correctness (round-trip)
    - **Property 5: Clinch Correctness (Round-Trip)**
    - If clinched, no counter-example exists in exhaustive search
    - Use small 4-team mini-conference for tractable exhaustive verification
    - **Validates: Requirements 1.3, 1.4**

  - [ ]* 8.6 Write property test for elimination correctness (round-trip)
    - **Property 6: Elimination Correctness (Round-Trip)**
    - If eliminated, no witness exists in exhaustive search
    - Use small 4-team mini-conference for tractable exhaustive verification
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 8.7 Write property test for invalid input rejection
    - **Property 7: Invalid Input Rejection**
    - Bad team names, out-of-range cutoff_week and time_limit always produce errors
    - **Validates: Requirements 1.5, 3.5, 7.5**

  - [ ]* 8.8 Write property test for bulk response structure
    - **Property 10: Bulk Response Structure**
    - 32 teams, grouped AFC/NFC (16 each), sorted alphabetically, required fields present
    - **Validates: Requirements 9.1, 9.2**

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The CP solver depends on OR-Tools being installed (`pip install -e ".[cp]"`)
- The solver reuses `identify_contenders` and `get_relevant_games` from `clinching.py` — no modification to that module
- Frontend gracefully degrades when OR-Tools is not installed (no badges, no errors)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4"] },
    { "id": 4, "tasks": ["2.5"] },
    { "id": 5, "tasks": ["2.6", "4.1"] },
    { "id": 6, "tasks": ["4.2", "5.1"] },
    { "id": 7, "tasks": ["5.2", "5.3"] },
    { "id": 8, "tasks": ["7.1"] },
    { "id": 9, "tasks": ["7.2"] },
    { "id": 10, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.7", "8.8"] },
    { "id": 11, "tasks": ["8.5", "8.6"] }
  ]
}
```
