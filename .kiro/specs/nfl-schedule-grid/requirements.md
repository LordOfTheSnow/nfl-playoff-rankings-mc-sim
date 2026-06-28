# Requirements Document

## Introduction

The NFL Schedule Grid feature adds a league-wide schedule overview to the NFL Monte Carlo Playoff Simulator frontend. Inspired by ESPN's schedule grid, it displays all 32 NFL teams as rows and weeks 1–18 as columns, with each cell showing the opponent abbreviation (prefixed with "@" for away games) or "BYE" for bye weeks. This provides a compact, at-a-glance view of the entire NFL season schedule, complementing the existing per-team schedule detail view.

## Glossary

- **Schedule_Grid**: A tabular view component that renders all 32 NFL teams as rows and NFL regular-season weeks 1–18 as columns, with each cell displaying the opponent abbreviation for that team's game in that week.
- **Team_Abbreviation**: A short identifier for an NFL team (e.g., "ARI", "BUF", "KC") used in grid cells and the team column.
- **Away_Indicator**: The "@" character prefixed to an opponent abbreviation to indicate the team plays at the opponent's venue in that week.
- **Bye_Cell**: A grid cell displaying "BYE" to indicate the team has no game scheduled in that week.
- **Schedule_Grid_API**: The backend API endpoint that returns the full league schedule data in a format suitable for rendering the schedule grid.
- **Router**: The existing hash-based SPA routing system in app.js that maps URL fragments to view render functions.
- **Game_Score**: The score of a completed or in-progress game displayed as "TeamScore-OpponentScore" from the perspective of the row team (e.g., "20-13" means the row team scored 20 and their opponent scored 13).

## Requirements

### Requirement 1: Schedule Grid Navigation

**User Story:** As a user, I want to access the schedule grid from the main navigation bar, so that I can quickly view the league-wide schedule.

#### Acceptance Criteria

1. THE Router SHALL recognize the hash route `#schedule-grid` and render the Schedule_Grid view.
2. WHEN the user navigates to `#schedule-grid`, THE Router SHALL invoke the Schedule_Grid render function with the main content container.
3. THE Navigation_Bar SHALL display a "Schedule" link with href `#schedule-grid`, rendered as a `nav-link` element within the `navbar-nav` list, positioned after the "Standings" link and before the "Statistics" link.
4. WHEN the `#schedule-grid` route is active, THE Navigation_Bar SHALL apply the `active` CSS class and `aria-current="page"` attribute to the "Schedule" `nav-link` element, and SHALL remove the `active` class and `aria-current` attribute from all other `nav-link` elements.
5. WHEN the user navigates to a route other than `#schedule-grid`, THE Navigation_Bar SHALL remove the `active` class and `aria-current` attribute from the "Schedule" link.

### Requirement 2: Schedule Grid Data Retrieval

**User Story:** As a user, I want the schedule grid to load data from the backend API, so that I see up-to-date schedule information.

#### Acceptance Criteria

1. WHEN the Schedule_Grid view is rendered, THE Schedule_Grid SHALL request schedule data from the Schedule_Grid_API endpoint `GET /api/schedule-grid`.
2. WHEN the Schedule_Grid_API returns data successfully, THE Schedule_Grid SHALL dismiss the loading indicator and render the grid table using the returned data.
3. IF the Schedule_Grid_API returns an error, THEN THE Schedule_Grid SHALL dismiss the loading indicator and display an error message using the existing App.showError notification mechanism; if the API response does not include an error message, the display SHALL use the fallback text "Failed to load schedule grid."
4. WHILE the Schedule_Grid is fetching data, THE Schedule_Grid SHALL display the loading indicator using App.showLoading.

### Requirement 3: Schedule Grid Table Structure

**User Story:** As a user, I want to see all 32 teams and their weekly opponents in a compact table, so that I can quickly compare schedules across the league.

#### Acceptance Criteria

1. THE Schedule_Grid SHALL render an HTML table with a `<thead>` containing one header row and a `<tbody>` containing 32 data rows, one for each NFL team.
2. THE Schedule_Grid SHALL render 19 columns: one "TEAM" header column followed by columns labeled "1" through "18" representing each regular-season week.
3. THE Schedule_Grid SHALL sort team rows alphabetically by Team_Abbreviation in ascending order (A–Z).
4. THE Schedule_Grid SHALL display each team's logo as a 28×28 pixel image followed by the Team_Abbreviation text in the "TEAM" column.
5. WHEN a team has a home game in a given week, THE Schedule_Grid SHALL display the opponent's Team_Abbreviation in that cell without any prefix.
6. WHEN a team has an away game in a given week, THE Schedule_Grid SHALL display the opponent's Team_Abbreviation prefixed with the Away_Indicator "@".
7. WHEN a team has no game in a given week, THE Schedule_Grid SHALL display "BYE" in that cell.
8. THE Schedule_Grid SHALL render week column headers with `scope="col"` attributes and TEAM column cells with `scope="row"` attributes for accessibility.

### Requirement 4: Team Name Links

**User Story:** As a user, I want to click on a team name in the schedule grid to view that team's detailed schedule, so that I can drill down for more information.

#### Acceptance Criteria

1. THE Schedule_Grid SHALL render each Team_Abbreviation in the "TEAM" column as an HTML anchor (`<a>`) element whose `href` attribute is set to `#team/<team_name>`, where `<team_name>` is the team's full name as returned by the Schedule_Grid_API.
2. WHEN the user clicks a team link in the "TEAM" column, THE Router SHALL navigate to `#team/<team_name>` where `<team_name>` is the team's full name (e.g., "Bills", "Chiefs").
3. IF the team's full name contains URI-unsafe characters (e.g., "49ers"), THEN THE Schedule_Grid SHALL URI-encode the `<team_name>` segment in the link's `href` attribute.

### Requirement 5: Visual Styling and Responsiveness

**User Story:** As a user, I want the schedule grid to be visually consistent with the rest of the application and readable on different screen sizes.

#### Acceptance Criteria

1. THE Schedule_Grid SHALL apply Bootstrap table classes (`table`, `table-bordered`) for consistent styling with the existing application.
2. THE Schedule_Grid SHALL apply reduced font size (no larger than 0.75rem) and minimal cell padding (no more than 0.25rem) so that all 19 columns fit within the viewport without horizontal scrolling on screens 1280px wide or greater.
3. WHILE the viewport width is less than 1280px, THE Schedule_Grid container SHALL apply `overflow-x: auto` to enable horizontal scrolling so that all columns remain accessible without layout breakage.
4. THE Schedule_Grid SHALL apply the `schedule-grid` CSS class to the table element for feature-specific styling.
5. THE Schedule_Grid SHALL display Bye_Cell content with the Bootstrap `text-muted` class to visually differentiate bye weeks from game cells using the application's standard muted text color.

### Requirement 6: Backend API Endpoint

**User Story:** As a developer, I want a backend endpoint that returns schedule data formatted for the grid view, so that the frontend can render the grid efficiently.

#### Acceptance Criteria

1. THE Schedule_Grid_API SHALL respond to `GET /api/schedule-grid` requests with a JSON object containing a list of exactly 32 team schedule entries, one per NFL team.
2. THE Schedule_Grid_API SHALL return data for the current season year as configured on the server.
3. THE Schedule_Grid_API SHALL return each team entry with the team's full name, Team_Abbreviation, and a list of exactly 18 weekly matchup entries ordered by week number (1 through 18).
4. THE Schedule_Grid_API SHALL represent each weekly matchup entry with the opponent Team_Abbreviation, a boolean indicating home or away, and the game status as one of "scheduled", "in-progress", or "completed".
5. WHEN a weekly matchup entry has a status of "completed" or "in-progress", THE Schedule_Grid_API SHALL include the score as two integer fields representing the row team's points and the opponent's points.
6. WHEN a team has a bye in a given week, THE Schedule_Grid_API SHALL represent that weekly matchup entry as a null value in the list.
7. IF no schedule data is available, THEN THE Schedule_Grid_API SHALL return an HTTP 404 response with a JSON error object containing a message indicating that no schedule data exists.

### Requirement 7: Game Score Display in Grid Cells

**User Story:** As a user, I want to see the score of completed or in-progress games directly in the grid cell, so that I can quickly see results without navigating away.

#### Acceptance Criteria

1. WHEN a game in a given week has status "completed", THE Schedule_Grid SHALL display the final score below the opponent abbreviation in the format "TeamScore-OpponentScore" (e.g., "20-13") where TeamScore is the row team's points and OpponentScore is the opponent's points, with the score rendered at a smaller font size than the opponent abbreviation.
2. WHEN a game in a given week has status "in-progress", THE Schedule_Grid SHALL display the current score below the opponent abbreviation in the format "TeamScore-OpponentScore (r)" where the "(r)" suffix indicates the game is still running, with the score rendered at a smaller font size than the opponent abbreviation.
3. WHEN a game in a given week has status "scheduled", THE Schedule_Grid SHALL display only the opponent abbreviation without any score and without a clickable link.
4. WHEN a game cell contains score information (completed or in-progress), THE Schedule_Grid SHALL render the entire cell content (opponent abbreviation and score) as a single clickable link that navigates to the row team's schedule detail page (`#team/<team_name>`) where `<team_name>` is the row team's full name.
5. IF a game has status "completed" or "in-progress" but the score data is unavailable (null or missing), THEN THE Schedule_Grid SHALL display only the opponent abbreviation without a score line, and SHALL NOT render the cell as a clickable link.
