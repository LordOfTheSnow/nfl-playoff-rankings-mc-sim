# Implementation Plan: NFL Schedule Grid

## Overview

Implement a league-wide schedule grid view that displays all 32 NFL teams as rows and weeks 1–18 as columns, with each cell showing the opponent abbreviation (with "@" for away games, "BYE" for bye weeks) and scores for completed/in-progress games. This spans a new backend API endpoint (`GET /api/schedule-grid`), a new frontend view module (`schedule-grid.js`), router integration, navigation link, and CSS styles.

## Tasks

- [x] 1. Add team abbreviation mapping to backend
  - [x] 1.1 Add `TEAM_ABBREVIATIONS` dictionary to `src/nfl_teams.py`
    - Add mapping of all 32 team names to their uppercase abbreviations (e.g., "Bills" → "BUF", "49ers" → "SF")
    - Add a helper function `get_team_abbreviation(team: str) -> str | None` for lookup
    - _Requirements: 6.3_

- [x] 2. Implement backend API endpoint
  - [x] 2.1 Implement `_build_schedule_grid` helper function in `src/server.py`
    - Create a pure function that transforms a list of `Game` objects into the grid JSON structure
    - Initialize 32 team entries with 18-element `weeks` arrays (all null)
    - For each game, populate both the home team and away team entries with opponent abbreviation, home/away flag, status, and scores from each team's perspective
    - Skip postponed/cancelled games (leave as null/bye)
    - Sort team entries alphabetically by abbreviation
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 2.2 Implement `_handle_get_schedule_grid` handler in `src/server.py`
    - Register the handler for `GET /api/schedule-grid` in the `do_GET` method
    - Retrieve games from cache using `server.cache.get_games(server.season_year)`
    - Return 404 with JSON error if no games are cached
    - Call `_build_schedule_grid` and return 200 with JSON response on success
    - _Requirements: 6.1, 6.2, 6.7_

  - [x] 2.3 Write property test for `_build_schedule_grid` (backend)
    - **Property 5: Backend grid transformation structural guarantees**
    - Generate random game lists (0–272 games, random teams/weeks/statuses/scores)
    - Verify: exactly 32 entries, each with exactly 18 week slots
    - Verify: non-null slots have correct field types (opponent string, home boolean, valid status)
    - Verify: completed/in-progress games with source scores include integer team_score and opponent_score
    - Verify: weeks with no game are null
    - Use hypothesis with `@settings(max_examples=100)`
    - **Validates: Requirements 6.1, 6.3, 6.4, 6.5, 6.6**

- [x] 3. Checkpoint - Backend endpoint verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Add frontend API method and navigation
  - [x] 4.1 Add `getScheduleGrid()` method to `frontend/js/api.js`
    - Add function that calls `GET /api/schedule-grid` via the existing `request()` helper
    - Return the parsed JSON response
    - _Requirements: 2.1_

  - [x] 4.2 Add navigation link to `frontend/index.html`
    - Add `<li class="nav-item"><a class="nav-link" href="#schedule-grid">Schedule</a></li>` after "Standings" and before "Statistics" in the navbar
    - _Requirements: 1.3_

  - [x] 4.3 Register route in `frontend/js/app.js`
    - Add `"schedule-grid"` to the `knownRoutes` array
    - Add case in the `route()` switch to call `renderScheduleGrid(contentEl)`
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

- [x] 5. Implement schedule grid view module
  - [x] 5.1 Create `frontend/js/schedule-grid.js` with `renderScheduleGrid` function
    - Implement the main render function that fetches data and renders the table
    - Call `App.showLoading()` before fetch, `App.hideLoading()` in success/error paths
    - On API error, call `App.showError()` with error message or fallback "Failed to load schedule grid."
    - Define `TEAM_ABBREVIATIONS` mapping for cell display
    - Render HTML table with `schedule-grid` CSS class, Bootstrap `table table-bordered` classes
    - Render `<thead>` with 19 columns: "TEAM" + weeks "1"–"18", each `<th>` with `scope="col"`
    - Render `<tbody>` with 32 rows sorted alphabetically by team abbreviation
    - Each team row: first cell has `scope="row"`, team logo (28×28 img), abbreviation text, and `<a>` link to `#team/<team_name>` (URI-encoded)
    - Each week cell: "BYE" with `text-muted` class for null entries; opponent abbreviation with "@" prefix for away games; no prefix for home games
    - For completed games with scores: render score "TeamScore-OpponentScore" below opponent abbreviation at smaller font; wrap cell in link to `#team/<team_name>`
    - For in-progress games with scores: render score "TeamScore-OpponentScore (r)" below opponent abbreviation at smaller font; wrap cell in link to `#team/<team_name>`
    - For scheduled games: display only opponent abbreviation, no score, no link
    - For completed/in-progress games with missing scores: display only opponent abbreviation, no score, no link
    - Add script tag for `schedule-grid.js` in `index.html` before `</body>`
    - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 5.1, 5.4, 5.5, 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 5.2 Add schedule-grid CSS styles to `frontend/css/styles.css`
    - Add `.schedule-grid` table styles with font-size ≤ 0.75rem and cell padding ≤ 0.25rem
    - Add container `overflow-x: auto` for viewports < 1280px
    - Ensure all 19 columns fit without horizontal scrolling at ≥ 1280px
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 6. Checkpoint - Frontend rendering verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Frontend property tests
  - [x] 7.1 Write property test for grid structural invariants
    - **Property 1: Grid table structural invariants**
    - Generate random valid schedule grid API responses (32 teams, 18 weeks each)
    - Verify rendered table has 1 thead row with 19 th elements (each with scope="col")
    - Verify rendered table has 32 tbody rows each with 19 td elements, first td has scope="row"
    - Use fast-check with `{ numRuns: 100 }`
    - **Validates: Requirements 3.1, 3.2, 3.8**

  - [x] 7.2 Write property test for cell content (home/away/bye)
    - **Property 2: Cell content matches game type**
    - Generate random weekly entries (null, home=true, home=false)
    - Verify: null → "BYE" with text-muted class; home=true → abbreviation without "@"; home=false → abbreviation prefixed with "@"
    - Use fast-check with `{ numRuns: 100 }`
    - **Validates: Requirements 3.5, 3.6, 3.7, 5.5**

  - [x] 7.3 Write property test for alphabetical sort order
    - **Property 3: Alphabetical sort order invariant**
    - Generate teams in random order
    - Verify rendered rows are sorted ascending by abbreviation
    - Use fast-check with `{ numRuns: 100 }`
    - **Validates: Requirements 3.3**

  - [x] 7.4 Write property test for team column rendering
    - **Property 4: Team column rendering (logo, abbreviation, link)**
    - Generate random team entries
    - Verify each TEAM cell contains: img with width=28 height=28, uppercase abbreviation text, anchor with href `#team/<URI-encoded team_name>`
    - Use fast-check with `{ numRuns: 100 }`
    - **Validates: Requirements 3.4, 4.1, 4.3**

  - [x] 7.5 Write property test for score display rules
    - **Property 6: Score display rules by game status**
    - Generate entries with random statuses and scores
    - Verify: completed + scores → "TeamScore-OpponentScore" displayed + cell is link; in-progress + scores → "TeamScore-OpponentScore (r)" + cell is link; scheduled → no score, no link
    - Use fast-check with `{ numRuns: 100 }`
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

- [x] 8. Final checkpoint - All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The backend uses Python (existing server.py pattern) and frontend uses vanilla JavaScript (no framework)
- The existing `TEAM_LOGO_IDS` mapping in standings.js is reused for logo file resolution
- The `TEAM_ABBREVIATIONS` mapping is defined both backend (nfl_teams.py) and frontend (schedule-grid.js) for display purposes

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "4.1", "4.2"] },
    { "id": 2, "tasks": ["2.2", "4.3"] },
    { "id": 3, "tasks": ["2.3", "5.1"] },
    { "id": 4, "tasks": ["5.2"] },
    { "id": 5, "tasks": ["7.1", "7.2", "7.3", "7.4", "7.5"] }
  ]
}
```
