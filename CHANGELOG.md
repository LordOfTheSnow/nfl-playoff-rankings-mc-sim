# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.2] - 2026-09-25

### Fixed
- Docker: clicking "Fetch" did not pick up games that completed after the schedule was last cached. `Cache.is_fresh()` treated any week whose games were all stored as `scheduled` within the last 24 hours as fresh — so a week fetched (as all-scheduled) earlier the same day would never be re-fetched, even after games in it finished. The fix: a `scheduled` game whose `game_date` is today or in the past is always treated as stale and re-fetched from ESPN, regardless of the 24-hour TTL. Games scheduled for a future date still use the TTL as before. Standalone runs were unaffected because they start with an empty cache for upcoming weeks, which always triggers a live fetch

## [1.1.1] - 2026-09-21

### Fixed
- Division standings order and the division champion were still wrong early in the season when teams had played different numbers of games: `GET /api/standings`'s `_division_tiebreak_sort` and `determine_playoff_bracket` (`standings.py`) grouped teams as "tied" by win percentage alone, so a 1-0 team and a 2-0 team (both 1.000) went through the tiebreaker cascade together and the 1-0 team could win on e.g. strength of victory — shown as the first row and division champion even though `games_behind` correctly named the 2-0 team the leader. Teams are now only tied when win percentage *and* win-loss margin match (`_standing_tie_key`, shared by both places and by the no-games fallback sort `_sort_teams_by_record`), so 2-0 ranks ahead of 1-0 and 0-0 ahead of 0-1, while genuine ties such as 1-1 vs 2-2 still go to the tiebreakers. This also replaces the earlier special case that ranked not-yet-played teams ahead of winless played teams. Only partial-season states are affected; once every team has played the same number of games nothing changes, so simulation results are unaffected. The 1.1.0 entry on `games_behind` below fixed only that column, not the row order

## [1.1.0] - 2026-09-21

### Added
- **Standalone HTML export** (new `#export` page, `src/export.py`): downloads the current Standings, Statistics, Schedule Grid, per-team pages and — optionally — the latest simulation result as self-contained HTML in the live app's "Modernist" style, either as a single page (`POST /api/export/page`) or as a ZIP bundle with an index and one page per section and team (`POST /api/export/bundle`). The export reuses the live JSON handlers rather than recomputing anything, and logos are inlined/bundled so the files work offline. See [API Reference](doc/api.md)
- "Data-driven ratings" reliability indicator under the "Results" line of the Simulations page and in the HTML export (single page's Simulation section and the bundle's `simulations.html`), e.g. "Data-driven ratings: 11% — Very low · 1 of 272 games played (0.4%)". It is the share of the league's team ratings that is based on played games rather than the league-average prior (mean over all 32 teams of the Bayesian dampening weight `n / (n + K)`), labelled Very low (< 25%) / Low (< 40%) / Moderate (< 55%) / Good. Heuristic reliability indicator, not a statistical confidence interval; most useful early in the season, when ratings are mostly regressed to average. New `data_driven_pct` and `data_confidence` fields on `GET /api/simulate/status/{job_id}`'s `result` (`doc/api.md`, `doc/algorithms.md`); older results without them simply omit the line
- ZIP bundle export: every page except `index.html` itself (the 4 section pages, previously missing one; team pages already had it) now has a "← Back to index" link
- Export's "Season data" card (season/cutoff, weeks/games loaded) now appears at the top of every page in both export modes — single page and every page of the bundle, including team pages — instead of only being shown nested under the Simulation section (and therefore missing entirely whenever no simulation was included in the export). Its "N games × M iterations = X" figure is folded in as a fifth "Game simulations" stat tile (only shown when a simulation was actually included) instead of being left as an orphaned standalone line below the card
- Standalone HTML export (single page and every page of the ZIP bundle) starts with the live app's header: a dark nav bar with the NFL logo and the "NFL PLAYOFF RANKINGS SIM" brand (linking back to `index.html` in the bundle), plus the "independent project not affiliated with the NFL" disclaimer strip. `nfl.png` is embedded/copied alongside the team and conference logos
- Standalone HTML export (single page and every page of the ZIP bundle) ends with a footer, divided from the page content by a horizontal rule: "Created by nfl-playoff-rankings-mc-sim v{version} on {YYYY-MM-DD HH:MM} UTC±HH:MM. — View on GitHub" (server-local time with numeric UTC offset, e.g. `2026-09-20 17:05 UTC+02:00`; resolved once per export, so every page of a bundle shows the same timestamp) linking to the project's repo (opens in a new tab), with an inlined GitHub icon so the export stays fully self-contained

### Changed
- Both export downloads now share one naming scheme, `nfl-playoff-rankings-mc-sim-export-<season>` plus extension (`.zip` for the bundle, `.html` for the single page; previously `nfl-export-<season>.zip`/`.html`). The bundle name is set by the server's `Content-Disposition` header, the single page's by the frontend (`export.js`)
- Standalone HTML export (single page and the bundle's `index.html`) no longer has the all-caps "NFL PLAYOFF RANKINGS SIM Export — {year}" heading under the page header: the nav bar already shows the brand and the Season data card shows the season. The browser tab `<title>` of those two pages is now the full name, "NFL Playoff Rankings Monte Carlo Simulator — {year} Export", instead of all-caps
- Unified the project's naming, which had drifted across the repo, package, and UI into four variants. There is now one slug, one full name, and one short name:
  - **Slug `nfl-playoff-rankings-mc-sim`** (matches the GitHub repo, GHCR image, and Docker container): the Python package name in `pyproject.toml`/`uv.lock` was `nfl-monte-carlo-simulator`. The `importlib.metadata` lookups in `server.py` and `export.py` follow, so the export footer now reads "Created by nfl-playoff-rankings-mc-sim v…". Re-run `pip install -e ".[dev]"` in an existing checkout so the installed package metadata picks up the new name (until then the version shows as "unknown")
  - **Full name "NFL Playoff Rankings Monte Carlo Simulator"**: README title, browser tab `<title>`, `--help` text, `doc/` headers, and all module/JS/CSS docstrings (previously a mix of "NFL Monte Carlo Playoff Simulator" and "NFL Monte Carlo Playoff Ranking Simulator")
  - **Short name "NFL PLAYOFF RANKINGS SIM"**: nav bar brand and standalone export header/title (previously "NFL MONTE CARLO PLAYOFF SIM")
  - `pyproject.toml` description is now "Monte Carlo simulation of NFL playoff rankings — seeding probabilities with full tiebreaker rules"
- ZIP bundle export nests every file under a single `export/` folder instead of scattering 38+ files loose at the ZIP's top level; all internal links are relative, so nothing else changed
- The "Data-driven ratings" hint under the Results line now explains itself on a second line ("Data-driven ratings = the share of a team's strength rating that comes from its own played games, averaged over all teams; the rest is assumed to be league average"), instead of a sentence that read as describing the "games played" percentage

### Fixed
- ZIP bundle export's `index.html` team directory rendered small (13px text, 18px logos) with each logo sitting on the text baseline, so logos looked shifted up against the names. Team links there are now 16px with 24px logos, vertically centred on the name (new `.mdn-index-team` modifier in `styles.css`)
- Division standings' `games_behind` leader selection (`_compute_games_behind`, `standings.py`) broke ties on win percentage by fewest games played, which is backwards for teams tied at 100% — e.g. a 1-0 team with a bye week could outrank a 2-0 team with the better actual record, showing the 2-0 team as `-0.5` games behind the 1-0 team instead of being the division leader itself. Tiebreak changed to most wins, then fewest losses, which still correctly handles the original edge case this logic exists for (a 0-0 bye-week team isn't outranked by a 0-1 team that's played and lost)
- Standalone HTML export's Schedule Grid rendered each game as a single line (`W 26–14 @ LAC`), unlike the live app's two-line cell (opponent, then score, no W/L/T letter) — `export.py`'s `_grid_cell` now matches `schedule-grid.js` exactly
- Standalone HTML export's Seeding Probabilities matrix had no per-cell color heatmap at all (plain white cells), where the live app tints each cell by probability (`simulation.js`'s `_seedTint`) — ported bucket-for-bucket as `_seed_tint` in `export.py`
- Playoff Probabilities and Seeding Probabilities tables (both the live Simulations page and the export) rendered the AFC and NFC tables as two independent `<table>` elements with `table-layout: auto`, so each table's Team column auto-sized to that conference's own longest team name — e.g. NFC's "Buccaneers"/"Commanders" made its Team column wider than AFC's, shifting every column after it out of alignment between the two tables. Both tables now use `table-layout: fixed` with explicit per-column widths (`simulation.js`, mirrored in `export.py`), so AFC and NFC always render pixel-identical column positions regardless of team-name length

## [1.0.3] - 2026-09-15

### Fixed
- Division standings could rank a team that had played and lost every game (e.g. 0-1) ahead of teams that hadn't played yet (0-0) in the same division — including marking it division champion and giving it a playoff seed — because both compute to the same 0.0% win percentage, and the early-season strength-of-schedule tiebreaker step treated that as a real, resolvable tie based on a single game. `standings.py`'s tiebreaker grouping (`_sort_with_tiebreakers`) and its `games_behind` leader selection (`_compute_games_behind`) now treat "hasn't played" separately from "played and winless" instead of running the full tiebreaker cascade across both; the same fix was applied to `server.py`'s separate display-only tiebreaker sort (`_division_tiebreak_sort`) used by `GET /api/standings`
- Standings legend and tiebreaker-badge tooltip described the "Alpha" (alphabetical) fallback as if it were an official NFL tiebreaker rule; it's actually a display-only fallback used when `server.py`'s reimplementation can't resolve a tie — the real final NFL tiebreaker is a coin toss, already implemented correctly in `standings.py`'s `_step_coin_toss`. Wording now makes clear "Alpha" isn't an official rule
- `GET /api/standings`'s `_division_tiebreak_sort` tagged a lone not-yet-played team (0-0-0) with the "Alpha" tiebreaker badge even when it wasn't actually tied with — or compared against — any other team, since it was the only team in the "unplayed" bucket ranked ahead of a played-and-winless team (e.g. 0-1-0). "Alpha" is now only shown when 2+ teams are genuinely tied at 0-0-0 and need alphabetical resolution
- `GET /api/statistics`'s `longest_win_streak`/`longest_lose_streak` picked a single team via first-occurrence-wins iteration order (`ALL_TEAMS`) whenever multiple teams shared the longest streak — common early in the season, e.g. every team that won its lone week-1 game showing a 1-game streak, with only the alphabetically/divisionally-first one ever surfaced and the rest silently discarded. Both fields are now arrays listing every team tied for the longest streak, each keeping its own week range; `statistics.js`'s streak row renders all of them (logo, name, week range per team, wrapping as needed) instead of just one. **Breaking API change**: these fields changed shape from a single object to an array of objects
- Simulations/Standings "Season data" header (`buildSeasonDataCell`, shared by both pages) showed "Auto cutoff — week 18" (the full season length) instead of "week 0" at the very start of a season with no completed weeks — `status.weeks_completed || status.weeks_fetched || 0` treated the legitimate `weeks_completed === 0` as falsy and fell through to `weeks_fetched` (weeks with schedule data loaded, not completed). Display-only bug; the actual auto-cutoff resolution used by `POST /api/simulate` was already correct. Fixed by using `??` instead of `||`
- Auto-detected `cutoff_week` (`_auto_detect_cutoff_week`, `src/simulator.py`) only accepted a week once *every* game in it was `COMPLETED`, otherwise falling back further back (to 0 if nothing qualified) — so a partially-played week's already-decided games were silently ignored and re-simulated as if unplayed until the entire week finished, worse the further into the season this happened (e.g. a mid-week auto simulation in week 10 with 8 of 16 games already final would ignore all 8). A manually-specified `cutoff_week` was unaffected — `_partition_games` already fixed completed games and simulated the rest on a per-game basis within any given week. Auto-detection now resolves to the highest week with *at least one* completed game, matching that same per-game partitioning. Four separate inline reimplementations of the old (and, in two cases, differently-fallback-valued) auto-detect logic in `server.py` (`GET /api/cp-clinch/{team}`, `GET /api/cp-clinch-all`, `GET /api/clinch-estimate`, `POST /api/clinching-scenarios`) were consolidated to call the one shared, fixed function. `GET /api/status` now also exposes the resolved value as `auto_cutoff_week` and a `completed_per_week` per-week breakdown, so `standings.js`'s "Auto cutoff — week N" header and `simulation.js`'s "games to simulate" preview counter (which previously always showed "0 games to simulate" under Auto, since it treated the cutoff as the last week of the season) reflect the real cutoff instead of guessing
- A simulation's "impact games" ranking step (`Simulator._compute_all_impact_games`, run after the main Monte Carlo pass to pick each team's top 5 swing games) dominated total run time by orders of magnitude relative to what the UI's iteration count implied — e.g. a 100-iteration/week-1 run measured at 184.6s wall time, of which 184.4s (99.9%) was this step, since it re-runs the full standings/tiebreaker engine roughly `teams x games-per-team x 2 x impact_iterations` times with every team still alive and a full schedule left. Cut to 85.9s (and much further for mid/late-season runs, see below) by: skipping teams whose main-simulation result is already unanimous (0% or 100%) rather than analyzing their now-irrelevant remaining games; lowering the per-pair sample size cap from 200 to 50 (this ranking was already an approximation, only ever used to order a team's top 5 games); and dispatching parallel work as a flat list of individual (team, game) pairs instead of one indivisible unit per team, so `num_workers` load-balances evenly instead of idling behind whichever team has the most games left. See "Impact Games & Background Jobs" in `doc/algorithms.md`

### Added
- Standings legend now explains the `TIEBREAKER` column and lists all tiebreaker codes (H2H, Div, Conf, SoV, SoS, Pts, Alpha) with their meaning, rather than only being explained via a per-badge hover tooltip
- `POST /api/simulate` now starts in the background and returns a `job_id` immediately instead of blocking for the run's full duration; new `GET /api/simulate/status/{job_id}` polls progress (current phase and a done/total count) and the eventual result, and new `POST /api/simulate/cancel/{job_id}` requests a best-effort stop (already-dispatched work finishes rather than being killed outright — typically lands within a second or two). The Simulations page's "Running simulation…" spinner now shows the real phase and progress (e.g. "Ranking impact games… (312/876)") via polling, and a new Cancel button next to Simulate stops a run early. Running the simulation in a background thread means a `ProcessPoolExecutor` pool can now be created while other request-handling threads are concurrently active (e.g. status polls arriving mid-run) — `src/simulator.py`'s multiprocessing context switched from `fork` to `forkserver` accordingly, since forking a multi-threaded process is a well-known way to deadlock the child (observed as progress silently freezing mid-run, with Cancel then unable to do anything either, since the stuck thread never reaches the check). `forkserver` avoids that by always forking from a dedicated, single-threaded template process, at effectively no measured cost to run time. Polling `GET /api/simulate/status/{job_id}` every ~600ms would otherwise flood the server's access log with an identical line per poll tick for however long a run takes — `NFLRequestHandler.log_message` now skips just that one path pattern; every other request still logs as before. **Breaking API change**: `POST /api/simulate` responds `202 {job_id, status}` instead of the simulation result directly — see [API Reference](doc/api.md)

## [1.0.2] - 2026-08-14

### Fixed
- Pre-2021 seasons (16 games/17 weeks) were assumed to be 17 games/18 weeks throughout: `expected_total`/`expected_games_per_season` (`GET /api/status`, `GET /api/system-info`), the Cutoff Week dropdowns (`standings.js`, `simulation.js`), and the Schedule Grid's column layout (`_build_schedule_grid`, `schedule-grid.js`) all hardcoded the modern season shape instead of deriving it from the loaded schedule — a fully-loaded, fully-completed 2020 season showed "17 / 18 weeks loaded", "256 / 272 games (94%)", and a false league-wide "BYE" column for the nonexistent week 18. Also affected several `cutoff_week` validation bounds (`POST /api/simulate`, `GET /api/cp-clinch`, `GET /api/cp-clinch-all`, `POST /api/clinching-scenarios`, `GET /api/standings`, and the CP solver's own `solve_clinch`), which silently accepted an out-of-range `cutoff_week` like 18 for a 17-week season, and the Settings page's per-season completeness table (`GET /api/system-info`'s `database.seasons`), which applied one global expected-games constant across every cached season regardless of each one's real shape. Fixed by deriving season length from the highest week number present in the cached schedule (`derive_season_weeks`) rather than a hardcoded or year-keyed constant — self-correcting for any future season-length change, since ESPN's schedule fetch already returns the full season's game "hull" (including future scheduled games) on first fetch
- Clinching scenarios' "only available after week 14" gate (`POST /api/clinching-scenarios`, `GET /api/clinch-estimate`, `compute_clinching_scenarios`) was a fixed absolute week rather than "N weeks remaining before the season ends" — for a pre-2021 17-week season, this incorrectly blocked clinching scenarios through week 13 (which should already be available) and left a nonsensical week-18 upper bound. Now expressed as `season_weeks - MIN_WEEKS_REMAINING_FOR_CLINCHING` (`min_cutoff_week_for_clinching`), gating at week 13 for a 17-week season and scaling automatically if the NFL ever changes season length again

## [1.0.1] - 2026-08-13

### Fixed
- CP solver (`_build_cpsat_model`/`_build_ranking_model`) hardcoded every team's total season games to 17, correct only for 2021+ seasons. For any earlier season (16 games/17 weeks, e.g. 2020) the resulting CP-SAT model was vacuously infeasible for every team regardless of actual records — `clinched_division`/`clinched_homefield` came back `True` for every team still alive, including multiple teams in the same division simultaneously (e.g. both Titans and Colts, or every AFC/NFC division leader, shown as "#1 SEED" at once). The constraint was already redundant with the per-game outcome constraints it duplicated, so it's simply removed rather than made season-aware
- ESPN team name resolution (`_resolve_team_name`) didn't recognize Washington's historical names (`"Washington"`, `"Washington Football Team"`, `"Washington Redskins"` — used for the 2020 and 2021 seasons before the 2022 Commanders rebrand) or older relocated franchises' historical city names (`"Oakland Raiders"`, `"San Diego Chargers"`, `"St. Louis Rams"`). Since `compute_standings()` silently drops any game where either team's name isn't recognized, every Washington game vanished from *both* participants' win/loss totals for 2020/2021 — e.g. the Giants' real 2020 record (5-10-0) displayed as 3-10-0, understating their ceiling enough to make a team with a *worse* real record (Eagles) show as more clearly alive than they did

## [1.0.0] - 2026-08-13

Full "Modernist" redesign of every page (flat red-on-white style, Bootstrap removed entirely), a restructured Simulations flow, empirical tie-probability estimation, a new Settings / Info diagnostics page, and a round of documentation and test-coverage cleanup.

### Added
- **Settings / Info page** (`#settings`, `GET /api/system-info`): SQLite cache metadata (per-season completeness, file size), runtime environment (CPU, Python, platform, multiprocessing method), the last 20 ESPN fetch attempts with failures flagged, and lifetime run counters (games simulated, clinching resolver evaluations) with a **Reset** button (`POST /api/reset-counters`) to zero them
- **Simulations page** (`#simulations`, replacing "Results"/`#results`) now owns the whole simulation lifecycle — season status, Iterations/Cutoff/Noise/Workers/Tie Probability controls, and results. Standings keeps only the cutoff field and a "Go to Simulations →" hand-off; `#results`/`#simulate` redirect here
- **Empirical tie-probability estimation**: `tie_probability` now defaults to the observed tie rate pooled across every complete prior season, falling back to the hardcoded 0.5% default with fewer than 2 seasons of history. Exposed as a Tie Probability slider (with a reset-to-estimate button) and as `tie_probability` on `POST /api/simulate`/`POST /api/clinching-scenarios`; `GET /api/status` gains `default_tie_probability` to seed it
- `noise` parameter on `POST /api/clinching-scenarios` so the clinching solver's sampling path honors the same Noise setting as the main simulation, instead of a hardcoded value
- Score Margin Distribution card on the Statistics page, backed by a new `margin_distribution` field in `GET /api/statistics`
- Shared, app-level cutoff-week state (`App.getCutoffWeek()`/`setCutoffWeek()`, `localStorage` key `sim-cutoff`) used by both Standings and Simulations; changing it invalidates any existing simulation results
- `doc/api.md` (full endpoint reference), `doc/algorithms.md` (ratings, clinching solver, CP solver), and `doc/technical.md` (parallel simulation architecture, solver performance export) — README trimmed down to intro/screenshots/setup/usage/Docker, with cross-links between all doc files
- Expanded test coverage ahead of release: HTTP-layer tests for tie-probability validation and threading through `/api/simulate`/`/api/clinching-scenarios`/`/api/status`, and frontend tests for the Workers/Tie Probability persistence, reset behavior, and the clinching panel's enumeration-vs-sampling hint copy

### Changed
- Every page — Standings, Team Detail, Simulations (formerly Results), Statistics, Schedule Grid, and the Solver Timing History dialog — redesigned in a flat "Modernist" style (dense ledger tables, zero corner radius, Archivo type, red accent); the Bootstrap CDN dependency, its classes, and the legacy `--color-*`/`--radius-*`/`--shadow-*` CSS tokens are gone
- Postponed/cancelled games (e.g. the suspended 2022 Week 17 Bills @ Bengals game) are now shown distinctly instead of appearing as a phantom bye week, on both Schedule Grid and Team Detail
- Default per-game Noise value raised from 0.20 to 0.34 across the main simulation, clinching solver, and the Simulations Noise slider, to better reflect real NFL variance
- Clinching solver's separate "Sampling iterations" control removed — reuses the shared Iterations value, same as it already did for Workers
- `nfl_teams.get_team_division`/`get_team_conference` use a precomputed reverse-lookup dict instead of a linear scan, cutting combined `compute_standings`/`determine_playoff_bracket` per-call cost ~23% (see `doc/technical.md` for the profiling breakdown)
- Simulations page's control row now spreads Iterations/Cutoff/Noise/Tie Probability/Workers/Simulate/Fetch-data across the available width instead of clustering to the right, with a fixed visual separator from the Season Data cell; Standings' Fetch data/Go to Simulations buttons realigned with the Cutoff dropdown
- Tooltip popovers no longer washed out by an ancestor element's `opacity`
- Various smaller consistency fixes: Seed Distribution cell borders restored, tag font size bumped for legibility, "CLINCHED" tag styling made visually distinct from "ELIMINATED", clinching scenario grammar ("Browns win" not "Browns wins"), README screenshots updated throughout
- README overhauled ahead of 1.0.0: Features list brought up to date (Team Detail, Schedule Grid, Statistics, Settings/Info with its Reset button, Docker), the growing screenshot collection split out into a new `doc/screenshots.md` gallery (Statistics and Schedule Grid screenshots added) with just one hero shot left inline, and the page-by-page Schedule Grid/Team Detail write-ups removed now that `doc/api.md` and the gallery cover them; Disclaimer section now notes results are probabilistic estimates used at the reader's own risk

### Fixed
- Clinching solver used its own hand-copied per-game outcome logic with an independently hardcoded tie probability, which could silently drift from the main simulator's; now shares the same code path and `SimulationConfig` defaults
- Workers slider and the clinching estimate panel could disagree on core count until the slider was touched, understating the time estimate by ~50% (the run itself was always correct)
- Settings / Info's worker-method stats always read "Unknown"; now report simulation's and the clinching resolver's actual multiprocessing methods separately, since they can legitimately differ
- CP solver cache served stale division/homefield clinch status forever for rows cached before those fields existed
- `GET /api/schedule-grid` silently dropped postponed/cancelled games instead of marking them, and Team Detail had no display case for them either
- Clinching solver's cores estimate showed the server's total CPU count instead of the user's configured Workers value
- Standings page could throw on rapid re-renders (e.g. changing cutoff week immediately after load) from a stale deferred callback
- Schedule Grid: clicking a completed game's opponent cell linked back to the row's own team instead of the opponent
- Candidate-details panel's stat row misaligned whenever only some labels carried a tooltip icon

## [0.7.4] - 2026-07-27

### Added
- Clinched Division badge (`y`, green) on standings page — CP solver now detects when a team has mathematically clinched their division title
- Clinched Homefield Advantage badge (`z`, green) on standings page — CP solver now detects when a team has clinched the #1 seed (first-round bye)
- Tiebreaker-aware division/homefield clinch detection using CP-SAT: accounts for head-to-head outcomes between division rivals, detecting clinches 1-2 weeks earlier than a wins-only approach
- Auto-release GitHub Actions workflow: creates a GitHub Release on merge to main when the version in `pyproject.toml` changes, using the PR title as release name and the CHANGELOG section as body
- Docker build chained into release workflow via `workflow_call` (no PAT required)
- `clinched_division` and `clinched_homefield` fields in CP solver API responses
- Solver performance link in README Clinching Scenarios section

### Changed
- Docker publish workflow converted to reusable workflow (`workflow_call` + `workflow_dispatch`), triggered by the release workflow instead of tag push
- Clinch badges use three shades of green: lighter for playoff spot (`x`), medium for division (`y`), standard for homefield (`z`)
- Badge legend updated with all five badge types and matching colors

### Fixed
- CP solver cache did not store/restore `clinched_division` and `clinched_homefield` fields, causing stale cached results to always show `x` instead of `y`/`z`
- Solver performance export test expected plain `---` separator but implementation uses right-aligned `---:` columns

## [0.7.3] - 2026-07-27

### Added
- Solver performance export: "Export Performance Data" button writes timing benchmarks to `doc/solver-performance.md` for cross-platform hardware comparison
- `GET /api/export-solver-performance` endpoint generates compacted performance data from the timing database
- `num_workers` column in `solver_timing` table (with auto-migration for existing databases) — records actual parallelism used per run
- "CPU Cores" in the performance file now reflects the Workers slider setting, enabling benchmarks at different parallelism levels on the same hardware
- Performance factor calculation groups by hardware (cpu_model, cpu_cores) — same hardware always gets factor 1.0; factor only differentiates across platforms
- CPU model detection prefers `/proc/cpuinfo` over `platform.processor()` to avoid generic architecture strings like "x86_64"
- Auto-release GitHub Actions workflow: creates a GitHub Release on merge to main when the version in `pyproject.toml` changes, using the PR title as release name and the CHANGELOG section as body

### Changed
- Clinching solver timing storage includes `num_workers` used for the run
- Solver performance export compacts multiple measurements into one row per unique (CPU Model, CPU Cores, Method) using the median
- Performance file rows sorted by factor ascending, grouped by hardware

## [0.7.2] - 2026-07-25

### Added
- Team record (W-L-T) column in the Playoff Probabilities tables
- Two-pass clinching solver: fast tiebreaker pass followed by full NFL tiebreaker verification when results conflict with Monte Carlo simulation probabilities
- Regression tests for clinching tiebreaker accuracy (Falcons false "no path", Buccaneers false "clinch")

### Fixed
- Clinching solver reported "No path to playoffs" for teams that could qualify only by winning tiebreakers (e.g., Falcons 2024 week 17 with 22% MC probability). Root cause: `_check_universe` used simplified win% + alphabetical tiebreakers which never resolved H2H, division record, or strength of victory
- Clinching solver falsely reported "clinches regardless" for teams that would lose tiebreakers in some universes (e.g., Buccaneers 2024 week 17 at 77% MC probability when losing their final game). Fast tiebreakers placed them ahead alphabetically in ties they'd actually lose
- Minimality reduction in clinching scenarios used fast tiebreakers even when qualifying universes came from the full-tiebreaker pass, producing incorrect all-conditions-necessary scenarios. Now uses full tiebreakers for the necessity check when appropriate
- `total_evals` in solver timing history did not account for additional evaluations from full-tiebreaker retries, causing misleading timing data
- Docker bind mount created `nfl_cache.db` as root, preventing the local Python process from writing to the same database. Container now runs as the host user via `user: "${UID:-1000}:${GID:-1000}"` in compose.yaml

### Changed
- Full-tiebreaker retry limited to top record combinations (within 1 win of best possible finish) to avoid excessive runtime for teams with many remaining games
- Clinching solver `compute_clinching_scenarios()` accepts optional `playoff_probability` parameter to trigger tiebreaker verification only when needed
- Update Bootstrap from 5.3.3 to 5.3.8

## [0.7.1] - 2026-07-24

### Added
- Adaptive solver timing: `get_ms_per_eval()` uses historical timing data from cache instead of on-demand benchmarking
- SQLite `solver_timing` table stores per-run timing measurements (rolling window of 50 records)
- `GET /api/solver-timings` endpoint returning timing history with count and average ms/eval
- "Timing History" button and modal in the clinching section showing collected calibration data
- `ClinchingResult.total_evals` field exposing actual evaluation count for external timing computation
- Server stores timing after each successful clinching scenarios response delivery

### Changed
- Clinch estimate endpoint no longer runs explicit `run_benchmark()` — uses adaptive cache-based timing
- Time estimate range multipliers adjusted from 2×–20× to 8×–15× for more realistic predictions
- `estimate_clinching()` accepts optional `cache` parameter for adaptive timing

### Fixed
- Time estimate lower bound was unrealistically optimistic (2× multiplier didn't account for minimality testing overhead)
- Timing modal table used monospace `.numeric` class causing inconsistent font sizes — replaced with plain right-alignment

## [0.7.0] - 2026-07-23

### Added
- CP solver architecture rework: pure constraint-based (no callbacks, no enumeration)
  - Three-tier solver: arithmetic fast-paths → division clinch → CP-SAT constraint model
  - Division-aware elimination: models division winners with H2H tiebreaker constraints
  - Wild card modeled correctly: counts only non-division-winners as competitors
  - Zero remaining games shortcut: uses standings engine directly
  - 0.3s for all 32 teams (was 30-60s+ before)
- Clinching scenarios: user-configurable enumeration threshold slider (5-14 games)
- Clinching scenarios: user-configurable sampling iterations (100-100,000)
- Clinching scenarios: cancel button to abort long-running computations
- Clinching scenarios: time estimate shown as range (accounts for variable post-processing)
- Clinching scenarios: uses same CPU core count as main MC simulation
- Server-side benchmark: measures actual ms/eval on first clinch-estimate request (cached 24h)
- CP solver badges auto-run on standings page load (no manual button needed)
- OR-Tools is now a standard dependency (was optional `[cp]` extra)
- Favicon: Monte Carlo die (SVG)
- Docker: compose.yaml uses directory bind mount (`./data:/data`)

### Fixed
- Critical: `determine_playoff_bracket` did not derive `simulated_game_ids` from `simulated_outcomes` — tiebreaker used actual scores instead of simulated outcomes in MC simulation
- CP solver: false "clinched" when no division rivals in contenders list
- CP solver: false "eliminated" for division winners with fewer wins than 7th-place team
- CP solver: crash on season with no completed games
- Docker: `PlayoffValidator` class crash when OR-Tools not installed
- Clinching scenarios: enumeration threshold configurable (default lowered from 13 to 9)

### Changed
- Clinching scenarios log output shows iterations (sampling) or threshold (enumeration)
- Frontend standings page: CP solver runs automatically, cached results load instantly
- Server: ThreadingMixIn for concurrent requests
- SQLite: `check_same_thread=False` for thread safety

## [0.6.2] - 2026-07-21

### Fixed
- Critical: `determine_playoff_bracket` did not derive `simulated_game_ids` from `simulated_outcomes` — tiebreaker functions used actual game scores instead of simulated outcomes, causing incorrect division winner determination in both MC simulation and CP solver
- MC simulation incorrectly showed 0% playoff probability for teams that could win their division via tiebreaker in simulated scenarios (e.g., Ravens at cutoff week 16)

## [0.6.1] - 2026-07-21

### Changed
- OR-Tools is now a standard dependency (was optional `[cp]` extra)
- `pip install -e .` includes everything needed — no extras required
- Dockerfile uses plain `pip install .` (no `.[cp]` needed)

### Fixed
- CP solver: false "clinched" for all teams when no division rivals in contenders list
- CP solver: false "eliminated" for division winners with fewer wins than 7th-place team (Tier 1b now division-aware)
- CP solver: crash on season with no completed games (returns "alive" for all teams)
- Docker: `PlayoffValidator` class crash when OR-Tools not installed (`cp_model` undefined at module level)
- Docker: compose.yaml uses directory bind mount (`./data:/data`) instead of file mount

## [0.6.0] - 2026-07-21

### Added
- CP-SAT constraint solver for mathematical clinching/elimination detection (Google OR-Tools)
- Pure constraint-based architecture: no callbacks, no enumeration — single Solve() per check
- Three-tier solver: arithmetic fast-paths → division clinch → CP-SAT constraint model
- Division-aware elimination: models division winners explicitly, won't falsely eliminate division winners
- H2H-aware division constraints: accounts for decided head-to-head records in division winner determination
- Wild card modeled correctly: counts only non-division-winners as competitors for 3 spots
- Zero remaining games shortcut: uses standings engine directly (no model needed)
- REST API endpoints: `GET /api/cp-clinch/{team}` and `GET /api/cp-clinch-all`
- Per-team caching in bulk endpoint (instant on repeat visits)
- Frontend clinch/elimination badges on standings view (x=clinched, e=eliminated)
- Hover tooltip on badges showing solve time, remaining games, scenarios checked
- Auto-run on page load with "Computing clinch/elimination…" spinner hint
- SQLite cache for CP solver results with automatic invalidation on data fetch
- Standings page respects cutoff week selector (shows records only through that week)
- OR-Tools as optional dependency (`pip install -e ".[cp]"`)
- Favicon: Monte Carlo die (SVG)
- Legend section on standings page explaining badges and tooltip values
- Server uses ThreadingMixIn for concurrent request handling (CP solver runs in background)

### Fixed
- Playoff bracket tiebreaker resolution now uses full NFL tiebreaker procedure (H2H, division record, conference record, SoV, SoS, net points) instead of alphabetical fallback
- Tiebreaker functions correctly handle simulated game outcomes via module-level `_simulated_winners`
- SQLite `check_same_thread=False` for thread-safe access with ThreadingMixIn
- BrokenPipeError silently handled when client disconnects during CP solver computation

### Performance
- 0.3s for all 32 teams at any cutoff week (sequential, single core)
- Instant for cached results
- No timeouts or inconclusive results under normal conditions

## [0.5.0] - 2026-07-17

### Added

- Clinching scenarios solver (`src/clinching.py`): finds all minimal game-outcome combinations that guarantee a team a playoff spot
  - Hybrid approach: full enumeration (3 outcomes per game) when ≤ 13 relevant games, strength-weighted Monte Carlo sampling (10,000 trials) otherwise
  - Groups results by the team's own remaining record (e.g., 3-1, 2-2, 1-3)
  - Strict minimality: every condition in a scenario is necessary — removing any one breaks the guarantee
  - Parallelized across CPU cores using the existing multiprocessing pattern
  - Hard gate: only available after week 14 (game space too large earlier)
- Preflight estimate endpoint `GET /api/clinch-estimate?team=<name>&cutoff_week=<n>` returns method, relevant game count, and estimated runtime before the user commits to the computation
- Backend endpoint `POST /api/clinching-scenarios` replaces both old path analysis endpoints
- UI: "Clinching Scenarios" button on the simulation results page for teams with 0% < playoff probability < 100%
- UI: spinning status indicator with elapsed timer and descriptive phase messages during computation
- UI: results rendered as collapsible record groups sorted by fewest conditions first

### Changed

- Replaced the old Playoff Path Analysis (Monte Carlo causality-filtered) and Guaranteed Path Solver (combinatorial iterative deepening) with the unified Clinching Scenarios Solver
- Removed `POST /api/analyze-path` and `POST /api/guaranteed-path` endpoints
- Removed `src/elimination.py` module (old guaranteed path solver)
- Removed `Simulator.analyze_path()` method from `src/simulator.py`
- Updated README screenshot and documentation to reflect the new feature
- "Top N Most Likely Playoff Scenarios" section is now collapsible (collapsed by default)
- Disclaimer text moved into the navbar header below the title
- Team logo displayed next to team name in the detail panel heading
- Added spacing between the scenarios section and the team detail panel

### Fixed

- Clinching solver used game status to determine remaining games — failed on completed seasons with a retroactive cutoff week. Now uses week number purely.
- `compute_standings` received only fixed games, causing simulated outcome game_ids to silently fail lookup. Now passes all games so the lookup works correctly.
- False "Clinches regardless" displayed when the minimality check found no single necessary condition (but multi-game flips could still eliminate the team). Now only shown when ALL game-level combinations for a record truly clinch.
- Redundant dominated scenarios shown (e.g., a 3-condition scenario that is a superset of a 1-condition scenario). Post-processing now removes scenarios whose conditions are a strict superset of a simpler scenario.
- False "No path to playoffs" for some records due to testing only one game-level combination per W-L-T record. Now tests all combinations (tiebreakers depend on which specific games are won/lost).
- Sampling used uniform random outcomes, making qualifying universes nearly impossible to find for teams with moderate playoff probability. Now uses strength-weighted sampling (same algorithm as the main simulator).
- Performance: reduced from 100K to 10K MC samples, capped minimality reduction at 200 universes, and deduplicated team records — bringing runtime from hours to ~2 minutes.

## [0.4.0] - 2026-07-14

### Added

- Docker containerization: multi-stage `Dockerfile` (python:3.14-slim builder + runtime), `compose.yaml`, and `docker-entrypoint.py` for running the app in a container
- Named volume support for persistent SQLite database across container restarts
- Season selector dropdown in the navbar allowing runtime season switching without restarting the server
- Backend API endpoint `POST /api/set-season` for changing the active season year at runtime
- Dependabot configuration for automated pip and Docker base image update PRs (`.github/dependabot.yml`)

### Changed

- Container always listens on fixed port 8080 internally; host port mapping via Docker `-p` flag only
- `SEASON` environment variable remains supported as the startup default; UI selector overrides it at runtime
- Removed `PORT` environment variable from Docker setup (unnecessary given Docker port mapping)

## [0.3.0] - 2026-06-28

### Added

- League-wide schedule grid view (`#schedule-grid`) showing all 32 teams × 18 weeks with opponent abbreviations, home/away indicators, bye weeks, and scores for completed games
- Backend API endpoint `GET /api/schedule-grid` serving structured schedule data
- "Schedule" navigation link in the navbar (between Standings and Statistics)
- Team abbreviation mapping and `get_team_abbreviation()` helper in `nfl_teams.py`
- Property-based tests for the schedule grid: 1 backend (hypothesis) + 5 frontend (fast-check)
- "Weeks completed" and "Games completed" stats on the standings page data panel
- Version number in server startup log message
- README screenshot showing the Ravens' playoff path analysis
- Schedule Grid section in README

### Changed

- Standings data panel: split "Weeks" into "Weeks loaded" / "Weeks completed", split "Games" into "Games loaded" / "Games completed (X%)", removed redundant "Scheduled" counter
- Team detail back link now uses `history.back()` instead of always navigating to standings
- Playoff path analysis: team's own games now highlighted with Bootstrap `table-info` class (visible blue) instead of CSS variable that was overridden by Bootstrap table styles
- Slow parallel simulation integration tests marked with `@pytest.mark.slow` and excluded from default test runs (use `pytest -m slow` to run them explicitly)
- Reduced iteration counts in parallel simulation tests for faster execution when run explicitly

### Fixed

- Game cells in schedule grid no longer link to team detail page (no game detail view exists)
- Playoff path blue row highlighting now visible with Bootstrap table classes

## [0.2.1] - 2026-06-27

### Added

- Tooltip on Iterations control explaining trial count and performance tradeoff
- Tooltip on Cutoff Week control explaining how it determines which games are real vs simulated
- Heatmap coloring on team detail seed distribution table for better visual clarity
- `.numeric-inline` CSS class for right-aligned numbers that stay on the same baseline as surrounding text

### Changed

- Standings column "TB" renamed to full "Tiebreaker" header
- Tiebreaker legend updated to list all 7 possible tiebreaker steps (H2H, Div, Conf, SoV, SoS, Pts, Alpha)
- Seeding probability tables (main and team detail) now use `table-bordered` for clearer cell boundaries
- Playoff path buttons wrapped in flex container to prevent full-width stretching
- Path analysis tables use `width:auto` to shrink-fit content instead of spanning full page width
- Week and Confidence columns in path tables right-aligned with `numeric-inline` for proper vertical alignment

### Fixed

- Playoff path "Team must win" and "Required outcomes" tables no longer stretch across full page width
- Week values in path tables now vertically align with other cells (removed monospace font mismatch)
- Confidence percentages in path tables vertically align with row content

## [0.2.0] - 2026-06-27

### Changed

- Migrated frontend from custom ~500-line CSS to Bootstrap 5.3.3 loaded via CDN
- Replaced custom navbar with Bootstrap `navbar navbar-expand-lg navbar-dark sticky-top` component with responsive collapse
- Converted all tables to Bootstrap `table table-striped table-hover` classes
- Converted all form controls to Bootstrap classes (`form-control`, `form-select`, `form-range`, `btn`)
- Converted content panels from custom `.controls-panel` to Bootstrap `card card-body` components
- Replaced custom notification system with Bootstrap `alert alert-danger/info alert-dismissible fade show` with auto-dismiss
- Replaced custom spinner with Bootstrap `spinner-border text-primary` inside a fixed overlay
- Migrated navigation active state to use Bootstrap `active` class and `aria-current="page"`
- Replaced `.hidden`/`.visible` toggles with Bootstrap `d-none` utility class
- Simulation controls layout now uses Bootstrap `row`/`col` grid for responsive arrangement
- Noise and Workers sliders restructured with label on top, slider below, value text underneath
- Reduced `styles.css` from ~500 lines to ~165 non-comment lines of NFL-specific overrides
- Conference filter buttons now use Bootstrap `btn btn-sm btn-primary`/`btn-outline-primary`
- Disclaimer bar now uses dark text on light background for readability, aligned with container
- Version number in navbar styled smaller with improved contrast against dark background

### Added

- Team logo (28×28) displayed next to team name in the schedule view header
- "Team Str" column in team schedule view showing the team's strength rating at each week
- Legend below schedule table explaining "Opp Str" and "Team Str" values
- `.numeric-left` CSS class for left-aligned monospace cells (used in TB column)
- `.control-field` CSS class for vertical stacking of form labels and inputs
- `.playwright-mcp/` added to `.gitignore`

### Fixed

- Cutoff week dropdown text clipping (changed from fixed `width:110px` to `width:auto;min-width:110px`)
- TB column header/cell size and font mismatch with other standings columns
- Standings table vertical alignment inconsistency across columns
- Tiebreaker display now correctly identifies which NFL tiebreaker step resolved the tie (was only showing H2H or Conf, now shows all 7 steps: H2H, Div, Conf, SoV, SoS, Pts, Alpha)

### Technical

- Bootstrap 5.3.3 CSS and JS loaded via jsDelivr CDN (no npm/build tooling required)
- Custom stylesheet retains only: CSS custom properties, conference border colors, division leader highlighting, game result colors, team link styles, fixed column widths, numeric cell styling, progress overlay, logo sizing
- All 7 JS files updated to emit Bootstrap class names in DOM generation

## [0.1.0] - 2025-06-27

### Added

- Monte Carlo simulation engine with configurable iterations (100–1,000,000), cutoff week, game noise, and tie probability
- Parallel simulation across multiple CPU cores using Python multiprocessing (configurable worker count, near-linear speedup)
- Iterative team strength ratings with strength-of-schedule weighting, relaxation damping for convergence, and Bayesian dampening based on sample size
- Full NFL tiebreaker implementation (head-to-head, division/conference record, common games, strength of victory/schedule, point-based steps for real games, coin toss fallback)
- ESPN public JSON API integration for fetching season schedules, game results, and live game data
- Local SQLite caching with TTL policies (completed games never expire, in-progress 60s, scheduled 24h)
- Interactive browser-based UI with hash-based SPA routing (standings, statistics, results views)
- Standings view grouped by conference and division with team logos, records, and games behind
- Team schedule view with completed/in-progress/scheduled game display
- Simulation results: playoff probabilities, seeding probability matrix, top 50 scenarios
- Playoff path analysis with causality filtering (identifies which game outcomes are needed for a team to make playoffs)
- Guaranteed path solver using constraint-based deterministic search
- Simulation controls with persisted settings (iterations, cutoff week, noise, workers stored in localStorage)
- Version display in UI header read from pyproject.toml via importlib.metadata
- Server logging of simulation timing (workers, elapsed time, throughput)

### Technical

- Python 3.11+ with type hints throughout
- No external runtime dependencies beyond httpx (for ESPN API calls)
- Frontend: plain HTML/CSS/JS, no build step, no external CDN dependencies
- Cross-platform: Linux (tested), macOS and Windows (untested, fork/spawn multiprocessing contexts)
- Property-based test strategies using Hypothesis
- 104 unit/integration tests passing

[Unreleased]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.1.1...HEAD
[1.1.2]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.0.3...v1.1.0
[1.0.3]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.4...v1.0.0
[0.7.4]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.3...v0.7.4
[0.7.3]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.6.2...v0.7.0
[0.6.2]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim/releases/tag/v0.1.0
