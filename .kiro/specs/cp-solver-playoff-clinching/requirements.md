# Requirements Document

## Introduction

A Constraint Programming (CP) solver that determines whether an NFL team has mathematically clinched or been eliminated from playoff contention. Unlike the existing Monte Carlo-based clinching solver (which estimates probabilities and enumerates scenarios after week 14), the CP solver uses constraint propagation and backtracking search to provide deterministic, provably correct clinch/elimination answers — potentially available earlier in the season.

The solver models every remaining game outcome as a variable (win/loss/tie), encodes NFL tiebreaker rules as constraints, and asks the solver whether any assignment of outcomes exists where the target team makes (or misses) the playoffs. If no such assignment exists, the team is clinched (or eliminated).


## ✅ Architecture Rework Completed

The solver was rewritten from scratch with a pure constraint-based architecture. No callbacks, no enumeration — just infeasibility checks.

### Final Architecture (3 Tiers)

**Tier 1: Arithmetic fast-paths (instant, handles ~75% of teams)**
- Clinch: team's min wins > 8th team's max wins → clinched
- Elimination: team's max wins < 7th team's min wins AND can't win division → eliminated
- Division-aware: won't falsely eliminate division winners with low win totals

**Tier 2: Division clinch (instant)**
- Team's min wins > all division rivals' max wins → guaranteed division winner → clinched

**Tier 3: CP-SAT constraint model (0.01-0.1s per team)**
- Builds a single model with all conference game outcome variables
- Models division winners explicitly (one winner per division via constraints)
- H2H-aware: if team lost decided H2H to a rival, needs strictly more wins to win division
- Wild card modeled correctly: counts only non-division-winners as competitors for 3 spots
- Clinch: "Can 7+ teams match/beat target with a division rival among them?" INFEASIBLE → clinched
- Elimination: "Can team win division OR get wild card?" INFEASIBLE → eliminated
- Zero remaining games: bypasses model entirely, uses standings engine directly

### Performance

- 0.3s for all 32 teams (sequential)
- ~0.1s with caching (instant on repeat visits)
- No timeouts, no inconclusive results for normal cases

### Known Limitations

- Conservative for same-wins tiebreaker cases beyond H2H (shows "alive" when MC might show ~100% or ~0%)
- H2H tiebreaker only applied when decided (one team leads AND no future H2H games remain)
- Division record, conference record, SoV/SoS tiebreakers not modeled as constraints

## Glossary

- **CP_Solver**: The constraint programming solver module that determines clinch/elimination status using Google OR-Tools CP-SAT.
- **Clinch**: A team has clinched when no possible combination of remaining game outcomes can prevent the team from making the playoffs.
- **Elimination**: A team is eliminated when no possible combination of remaining game outcomes can result in the team making the playoffs.
- **Remaining_Game**: Any game in weeks after the cutoff week whose outcome has not been fixed.
- **Outcome_Variable**: A CP-SAT integer variable representing the result of a remaining game (0 = home win, 1 = away win, 2 = tie).
- **Standings_Engine**: The existing `compute_standings` and `determine_playoff_bracket` functions that apply NFL tiebreaker rules to produce playoff seedings.
- **Contender**: A same-conference team that is not yet mathematically eliminated from playoff contention.
- **Magic_Number**: The number of additional wins (or opponent losses) needed for a team to clinch, derived from the CP solver's analysis.
- **Frontend**: The Bootstrap 5 web UI served by the Python HTTP server.
- **API_Server**: The Python HTTP server that exposes REST endpoints for the frontend.

## Requirements

### Requirement 1: Clinch Detection

**User Story:** As a user, I want to know whether a team has mathematically clinched a playoff spot, so that I can see definitive playoff status regardless of remaining game outcomes.

#### Acceptance Criteria

1. WHEN a clinch check is requested for a team, THE CP_Solver SHALL model each Remaining_Game as an Outcome_Variable with domain {0, 1, 2} representing home win, away win, and tie respectively, where a Remaining_Game is any game scheduled in a week strictly greater than the cutoff_week regardless of its actual game status.
2. WHEN the CP_Solver searches for an assignment where the target team misses the playoffs, THE CP_Solver SHALL use the Standings_Engine to compute full conference standings and validate that the assignment produces a valid 7-seed playoff bracket for the target team's conference.
3. WHEN no assignment exists where the target team finishes outside the top 7 seeds in its conference playoff bracket, THE CP_Solver SHALL report the team as clinched by returning a clinched status of true.
4. WHEN at least one assignment exists where the target team finishes outside the top 7 seeds in its conference playoff bracket, THE CP_Solver SHALL report the team as not clinched by returning a clinched status of false.
5. IF the specified team is not a recognized NFL team, THEN THE CP_Solver SHALL reject the clinch check request and return an error indicating the team is unknown.

### Requirement 2: Elimination Detection

**User Story:** As a user, I want to know whether a team has been mathematically eliminated from playoff contention, so that I can see when a team's season is effectively over.

#### Acceptance Criteria

1. WHEN an elimination check is requested for a team, THE CP_Solver SHALL model each Remaining_Game as an Outcome_Variable with domain {0, 1, 2} and search for any assignment of Outcome_Variables where the target team makes the playoffs.
2. WHEN the CP_Solver searches for an assignment where the target team makes the playoffs, THE CP_Solver SHALL use the Standings_Engine to validate that the assignment produces a valid playoff bracket containing the target team.
3. WHEN no assignment exists where the target team appears in a valid playoff bracket, THE CP_Solver SHALL report the team as eliminated.
4. WHEN at least one assignment exists where the target team appears in a valid playoff bracket, THE CP_Solver SHALL report the team as not eliminated.

### Requirement 3: Early-Season Availability

**User Story:** As a user, I want clinch/elimination analysis available before week 14, so that I can track playoff status throughout more of the season.

#### Acceptance Criteria

1. THE CP_Solver SHALL accept any cutoff week from 1 through 18 without a hard gate restriction.
2. WHEN the number of Remaining_Games exceeds a configurable threshold (default: 13, valid range: 1 to 50), THE CP_Solver SHALL apply constraint propagation and pruning to reduce the search space before exhaustive search.
3. WHEN the number of Remaining_Games is at or below the configurable threshold, THE CP_Solver SHALL perform exhaustive enumeration and return a complete result.
4. IF the CP_Solver cannot determine a result within the configurable time limit (default: 30 seconds, valid range: 1 to 300 seconds), THEN THE CP_Solver SHALL return an indeterminate status indicating the time limit was reached, along with the cutoff week and team name that were requested.
5. IF the cutoff week is outside the range 1 through 18, THEN THE CP_Solver SHALL reject the request with an error message indicating the valid range.

### Requirement 4: Wins-and-Losses Constraint Encoding

**User Story:** As a developer, I want the solver to correctly model win/loss/tie arithmetic from game outcomes, so that team records are always consistent with game results.

#### Acceptance Criteria

1. THE CP_Solver SHALL derive each team's total wins as the sum of wins from completed games in weeks less than or equal to cutoff_week plus the count of Outcome_Variables resolved to that team winning in games where that team is a participant.
2. THE CP_Solver SHALL derive each team's total losses as the sum of losses from completed games in weeks less than or equal to cutoff_week plus the count of Outcome_Variables resolved to that team losing in games where that team is a participant.
3. THE CP_Solver SHALL derive each team's total ties as the sum of ties from completed games in weeks less than or equal to cutoff_week plus the count of Outcome_Variables resolved as ties in games where that team is a participant.
4. THE CP_Solver SHALL ensure that for every team, wins plus losses plus ties equals the total number of games in which that team participates (as home or away) across all weeks of the season.
5. WHEN an Outcome_Variable is resolved to a winner, THE CP_Solver SHALL assign exactly one win to the winning team and exactly one loss to the losing team for that game.
6. WHEN an Outcome_Variable is resolved as a tie, THE CP_Solver SHALL assign exactly one tie to each of the two participating teams for that game.

### Requirement 5: Division Winner Constraints

**User Story:** As a developer, I want the solver to model division winner selection so that the top team in each division is correctly identified under any scenario.

#### Acceptance Criteria

1. THE CP_Solver SHALL encode that each of the 8 NFL divisions (4 per conference) has exactly one division winner selected from among the 4 teams belonging to that division.
2. WHEN determining the division winner, THE CP_Solver SHALL ensure the division winner has a win percentage greater than or equal to every other team in the same division.
3. IF two or more teams in a division have equal win percentages, THEN THE CP_Solver SHALL delegate tiebreaker resolution to the Standings_Engine, which returns a deterministic total ordering of the tied teams, and the CP_Solver SHALL assign the division winner as the first team in that ordering.
4. IF all teams in a division have zero games played (win percentage 0.0 for all), THEN THE CP_Solver SHALL still assign exactly one division winner for that division via tiebreaker delegation to the Standings_Engine.

### Requirement 6: Wild Card Constraints

**User Story:** As a developer, I want the solver to model wild card selection so that the three wild card spots per conference are filled correctly.

#### Acceptance Criteria

1. THE CP_Solver SHALL encode that each conference has exactly 3 wild card playoff spots filled by non-division-winners, selected from the 12 non-division-winner teams in the conference.
2. THE CP_Solver SHALL ensure that each wild card team has a win percentage strictly greater than every non-playoff non-division-winner team in the same conference, unless two or more teams have equal win percentages at the wild card boundary, in which case the Standings_Engine determines ranking.
3. IF two or more wild-card-eligible teams have equal win percentages and are competing for the same wild card spot, THEN THE CP_Solver SHALL delegate to the Standings_Engine with the complete Outcome_Variable assignment to determine which team(s) earn the wild card spot(s).
4. WHEN the Standings_Engine returns a ranking for tied wild card contenders, THE CP_Solver SHALL use that ranking to select which teams fill the wild card spots and SHALL accept the Standings_Engine result as authoritative for that assignment.

### Requirement 7: Solver Time Limit

**User Story:** As a user, I want the solver to return within a reasonable time even for complex mid-season scenarios, so that the application remains responsive.

#### Acceptance Criteria

1. THE CP_Solver SHALL accept a time limit parameter (integer, range 1 to 300 seconds inclusive) with a default of 30 seconds.
2. WHEN the solver's elapsed wall-clock time exceeds the configured time limit, THE CP_Solver SHALL terminate the search and return a result containing whichever record groups have been fully processed up to that point, with the remaining record groups omitted.
3. WHEN the solver terminates due to the time limit, THE CP_Solver SHALL set the result's `exhaustive` field to False and include a non-empty `error` string indicating the timeout occurred and how many record groups were completed out of the total.
4. WHEN the solver completes all record groups and finds a definitive answer (clinched or eliminated) before the time limit, THE CP_Solver SHALL return immediately without waiting for the time limit to expire.
5. IF the provided time limit value is less than 1 or greater than 300, THEN THE CP_Solver SHALL reject the request and return an error indicating the allowed range.

### Requirement 8: REST API Endpoint

**User Story:** As a frontend developer, I want a REST API endpoint for clinch/elimination status, so that the UI can display definitive playoff status for each team.

#### Acceptance Criteria

1. THE API_Server SHALL expose a `GET /api/cp-clinch/{team}` endpoint that accepts a team abbreviation as a path parameter, and optional `cutoff_week` (integer, 1–18) and `time_limit` (integer, 1–300 seconds, default 30) query parameters.
2. WHEN the endpoint is called, THE API_Server SHALL invoke the CP_Solver for the specified team and return a JSON response containing: clinch status (clinched, eliminated, or alive), elimination status, solve time in milliseconds, number of solver variables, and whether the result is conclusive or timed out.
3. IF the team abbreviation is invalid, THEN THE API_Server SHALL return HTTP 400 with an error response containing the invalid value and the list of valid team abbreviations.
4. IF `cutoff_week` is omitted, THEN THE API_Server SHALL default to the latest fully completed week based on cached game data.
5. IF `cutoff_week` or `time_limit` is outside its valid range or not a valid integer, THEN THE API_Server SHALL return HTTP 400 with an error response indicating the accepted range.
6. IF no game data has been fetched for the current season, THEN THE API_Server SHALL return HTTP 409 with an error response indicating that data must be fetched first.
7. THE API_Server SHALL expose a `GET /api/cp-clinch-all` endpoint that returns clinch/elimination status for all 32 teams in a single JSON response, with each team entry containing the same fields as the single-team endpoint.
8. WHEN the bulk endpoint is called, THE API_Server SHALL process teams in parallel using available CPU cores, and IF the solver fails or times out for individual teams, THEN the response SHALL include those teams with their respective error or timeout status rather than failing the entire request.

### Requirement 9: Conference-Wide Status Summary

**User Story:** As a user, I want to see clinch/elimination status for all teams in a conference at once, so that I can understand the full playoff picture.

#### Acceptance Criteria

1. WHEN the bulk status endpoint is called, THE CP_Solver SHALL return results grouped by conference (AFC and NFC), with each conference containing results for all 16 teams sorted by team abbreviation alphabetically.
2. THE CP_Solver SHALL include for each team: clinch status (one of: clinched, eliminated, alive, or inconclusive), the number of solver variables as an integer, and the solve time as an integer in milliseconds.
3. IF the CP_Solver terminates due to the time limit for a given team, THEN THE CP_Solver SHALL report that team's status as inconclusive and still include the solver variable count and elapsed solve time.
4. WHEN a team is clinched, THE CP_Solver SHALL additionally report the team's minimum possible seed as an integer in the range 1 to 7.
5. WHEN a team is alive (not clinched, not eliminated, not inconclusive), THE CP_Solver SHALL additionally report the Magic_Number as a positive integer. IF the Magic_Number cannot be derived because the solver timed out or no single wins-needed threshold guarantees clinching, THEN THE CP_Solver SHALL omit the Magic_Number field from that team's result.

### Requirement 10: Frontend Integration

**User Story:** As a user, I want to see clinch/elimination indicators in the standings view, so that I get a quick visual summary of each team's playoff fate.

#### Acceptance Criteria

1. WHEN clinch/elimination data is available from the `GET /api/cp-clinch-all` endpoint, THE Frontend SHALL display a badge inline with the team name in each standings row indicating "Clinched", "Eliminated", or no badge for alive teams.
2. WHEN a team is clinched, THE Frontend SHALL display the badge using the existing success color token (green).
3. WHEN a team is eliminated, THE Frontend SHALL display the badge using the existing accent color token (red).
4. WHEN the user clicks a clinched or eliminated badge, THE Frontend SHALL show a popover containing the solve time in milliseconds and the variable count used by the solver.
5. IF the CP_Solver returns an inconclusive result due to timeout, THEN THE Frontend SHALL display a grey "Inconclusive" badge.
6. IF the `GET /api/cp-clinch-all` endpoint returns an error (HTTP 503, network failure, or non-success status), THEN THE Frontend SHALL render the standings without any clinch/elimination badges and without displaying an error notification to the user.

### Requirement 11: Integration with Existing Clinching Solver

**User Story:** As a developer, I want the CP solver to coexist with the existing enumeration/MC clinching solver, so that users can access both deterministic status and detailed scenario paths.

#### Acceptance Criteria

1. THE CP_Solver SHALL be implemented as a separate Python module that imports from but does not modify the existing `clinching.py` module's public interface or internal logic.
2. THE CP_Solver SHALL reuse the existing `identify_contenders` and `get_relevant_games` functions from the clinching module for game partitioning, passing the same `team`, `all_games`, and `cutoff_week` parameters.
3. WHEN both the CP solver result and the existing clinching solver result are available for a team, THE Frontend SHALL display the CP solver's clinch/elimination badge alongside a separate control (button or link) to view the existing solver's detailed scenario paths.
4. IF the existing clinching solver is unavailable for a team (cutoff week is before week 14), THEN THE Frontend SHALL display only the CP solver's clinch/elimination status without the scenario paths control.
5. IF the CP solver is unavailable (OR-Tools not installed) but the existing solver has results, THEN THE Frontend SHALL display the existing solver's scenario paths without the CP solver badge.

### Requirement 12: Google OR-Tools Dependency

**User Story:** As a developer, I want the CP solver to use Google OR-Tools CP-SAT as the solving backend, so that the implementation leverages a proven, high-performance constraint solver.

#### Acceptance Criteria

1. THE CP_Solver SHALL use the `ortools` Python package (specifically `ortools.sat.python.cp_model`) as its constraint solving backend.
2. THE CP_Solver SHALL be implemented such that `ortools` is declared as an optional dependency (pip extras group) — all non-CP-solver endpoints SHALL remain fully operational when `ortools` is not installed.
3. IF `ortools` is not installed or fails to import, THEN THE API_Server SHALL return a JSON response with HTTP status 503 and a body containing an error message indicating that OR-Tools is required, for any request to the `/api/cp-clinch/{team}` or `/api/cp-clinch-all` endpoints.
4. IF `ortools` is not installed or fails to import, THEN THE API_Server SHALL still start successfully and serve all other endpoints without error within 5 seconds of startup.

### Requirement 13: Result Caching

**User Story:** As a user, I want solver results to be cached so that repeated queries for the same team and week return instantly.

#### Acceptance Criteria

1. WHEN a clinch/elimination query completes successfully, THE CP_Solver SHALL store the result in a cache keyed by the tuple (team, cutoff_week, season).
2. IF a cached result exists for the requested (team, cutoff_week, season) tuple, THEN THE API_Server SHALL return the cached result without re-running the solver, within 100 milliseconds of receiving the request.
3. WHEN the API_Server completes a new game-data fetch for a season, THE API_Server SHALL invalidate all cached CP solver results for that season before returning the fetch response.
4. IF a cached result has been invalidated and the same (team, cutoff_week, season) query is received, THEN THE API_Server SHALL re-run the solver and cache the new result before responding.
