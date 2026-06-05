# Requirements Document

## Introduction

A web application with a Python backend and an HTML/JavaScript frontend that uses Monte Carlo simulations to predict the outcome of an NFL season. The user starts the application from the command line, which launches a local web server. The browser-based UI allows users to trigger data fetching, configure and run simulations, and view playoff probability results interactively. The backend fetches schedule, results, and live game data from ESPN's public (undocumented) JSON API, caches it locally, and runs simulations to determine all possible playoff ranking scenarios for NFL teams based on the league's official standings and tiebreaker rules.

**Data Source:** All NFL data is sourced from ESPN's public JSON API (no authentication required). This is an undocumented, unofficial API that may change without notice. Key endpoints include the scoreboard API (`site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`), standings API (`site.api.espn.com/apis/v2/sports/football/nfl/standings`), and teams API (`site.api.espn.com/apis/site/v2/sports/football/nfl/teams`).

## Glossary

- **Simulator**: The core Monte Carlo simulation engine that runs repeated random trials to estimate playoff outcome probabilities
- **Data_Client**: The component responsible for fetching season schedule, game results, and live game data from ESPN's public JSON API endpoints
- **Cache**: The local persistence layer (file-based or database) that stores previously fetched data to avoid redundant network requests
- **Season_Schedule**: The complete list of NFL regular season games including dates, matchups, and venues
- **Game_Result**: The final outcome of a completed game including scores for both teams
- **Running_Game**: A game currently in progress with live score data
- **Scenario**: A unique combination of remaining game outcomes that produces a specific playoff ranking
- **Playoff_Ranking**: The ordered position of teams that qualifies or seeds them for the playoffs
- **Simulation_Run**: A single trial within the Monte Carlo simulation where all remaining games are resolved randomly
- **Web_UI**: The browser-based HTML/JavaScript frontend through which users interact with the application
- **Web_Server**: The Python HTTP server that serves the frontend static files and exposes REST API endpoints for the Web_UI to consume
- **API**: The set of REST endpoints provided by the Web_Server that the Web_UI calls to trigger data fetching, run simulations, and retrieve results
- **Frontend**: The HTML, CSS, and JavaScript files served to the browser that render the interactive user interface
- **Team_Strength**: A numerical rating derived from a team's game results weighted by the strength of opponents faced (strength of schedule), calculated iteratively until convergence, used to weight game outcome probabilities in the simulation
- **Conference**: One of the two major groupings of NFL teams (AFC or NFC), each containing 16 teams across 4 divisions
- **Division**: A grouping of 4 NFL teams within a conference (East, North, South, West), where the team with the best record earns a playoff spot as Division_Champion
- **Wild_Card**: One of the 3 non-division-champion teams per conference that qualifies for the playoffs based on best remaining conference record
- **Division_Champion**: The team with the best won-lost-tied record in its division, earning an automatic playoff berth and seeded 1-4 in its conference
- **Seed**: A team's position (1 through 7) in the conference playoff bracket, determining home-field advantage and first-round matchups
- **Bye**: The first-round exemption granted to the number 1 seed in each conference, allowing that team to skip the Wild Card Round
- **Standings_Engine**: The component responsible for computing NFL standings, applying tiebreaker procedures, and determining playoff qualification and seeding
- **ESPN_API**: ESPN's public, undocumented JSON API that provides NFL schedule, scores, standings, and team data without authentication
- **Standings_View**: The frontend page that displays current NFL standings organized by conference and division, showing each team's record and ranking
- **Team_Schedule_View**: The frontend page that displays all games for a selected team, including completed, in-progress, and scheduled games
- **Simulation_Results_View**: The frontend page that displays all possible playoff outcomes after a simulation completes
- **Win_Percentage**: A team's winning percentage calculated as (wins + 0.5 × ties) / total games played, expressed as a decimal between 0.000 and 1.000
- **Games_Behind**: The number of games a team trails the division leader, calculated as ((leader wins - team wins) + (team losses - leader losses)) / 2
- **Cutoff_Week**: The week number (1 through 18) up to which game results are used as fixed inputs for the simulation; games scheduled in weeks after the Cutoff_Week are treated as unplayed and simulated regardless of whether actual results exist in the Cache

## Requirements

### Requirement 1: Fetch Season Schedule from ESPN API

**User Story:** As a user, I want the application to fetch the full NFL season schedule from ESPN's JSON API, so that I have an up-to-date list of all games in the season.

#### Acceptance Criteria

1. WHEN the user requests season data, THE Data_Client SHALL fetch the complete NFL regular season schedule by calling the ESPN scoreboard API endpoint (`site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard`) with the appropriate week (1 through 18) and seasontype (2 for regular season) parameters for the specified season year
2. WHEN a season schedule is fetched, THE Data_Client SHALL extract the following fields from the JSON response for each game: date (in ISO 8601 format, YYYY-MM-DD), home team name, away team name, and game status (one of: "scheduled", "in-progress", "completed", "postponed", or "cancelled")
3. IF the ESPN API is unreachable or returns an HTTP error after a connection timeout of 30 seconds, THEN THE Data_Client SHALL report an error message to the user that includes the HTTP status code (if available) and the URL that failed
4. IF the ESPN API response schema has changed and expected fields are missing from the JSON response, THEN THE Data_Client SHALL report a schema error message to the user that identifies which data field could not be found in the response
5. IF some weeks in the schedule are successfully fetched but others fail, THEN THE Data_Client SHALL return the successfully fetched games and include a warning indicating the count of weeks that could not be retrieved

### Requirement 2: Fetch Game Results from ESPN API

**User Story:** As a user, I want the application to fetch completed NFL game results from ESPN's JSON API, so that the simulation uses accurate historical outcomes.

#### Acceptance Criteria

1. WHEN the user requests game results for a specified week or date range, THE Data_Client SHALL fetch scores and outcomes for all completed NFL games by calling the ESPN scoreboard API endpoint with the appropriate week, seasontype, or dates parameters within 30 seconds
2. WHEN game results are fetched, THE Data_Client SHALL extract the team names, final score for both teams, the points scored by each team, and the winner (or tie) for each completed game from the JSON response
3. IF a game has not yet been completed, THEN THE Data_Client SHALL mark the game as pending and exclude it from completed results
4. IF the Data_Client fails to retrieve data from the ESPN API due to network error, timeout, or unexpected response schema, THEN THE Data_Client SHALL return an error indication specifying the failure reason without returning partial or stale results
5. WHEN game results are fetched, THE Data_Client SHALL also extract the points scored by each team for each completed game to enable tiebreaker calculations that require point differentials

### Requirement 3: Fetch Running Games from ESPN API

**User Story:** As a user, I want the application to fetch live NFL game data from ESPN's JSON API, so that the simulation can account for games currently in progress.

#### Acceptance Criteria

1. WHEN the user requests live game data, THE Data_Client SHALL fetch current scores and game state for all NFL games currently in progress by calling the ESPN scoreboard API endpoint within 30 seconds
2. WHEN live game data is fetched, THE Data_Client SHALL extract the home team name, away team name, each team's current score, the game clock remaining, and the current quarter for each running game from the JSON response
3. IF no games are currently in progress, THEN THE Data_Client SHALL return an empty result set without error
4. IF the ESPN API is unreachable or returns a non-success HTTP response, THEN THE Data_Client SHALL return an error indication specifying that live data could not be retrieved, without crashing

### Requirement 4: Local Data Caching

**User Story:** As a user, I want previously fetched data to be stored locally and reused, so that the application avoids redundant network requests and runs faster on repeated use.

#### Acceptance Criteria

1. WHEN data is fetched from the ESPN API, THE Cache SHALL persist the data locally along with a UTC timestamp recording when the data was fetched
2. IF the user requests data that exists in the cache and the cached data is still valid according to its TTL policy, THEN THE Cache SHALL return the locally stored data without making a network request
3. IF cached data for a game whose status indicates it is completed exists, THEN THE Cache SHALL treat that cached entry as valid indefinitely without expiration
4. IF cached data for the season schedule exists and the cached entry's timestamp is older than the configured time-to-live (default: 24 hours), THEN THE Cache SHALL fetch fresh data from the ESPN API and update the cached entry
5. IF cached data for a game with status "in-progress" exists and the cached entry's timestamp is older than 60 seconds, THEN THE Cache SHALL fetch fresh data from the ESPN API and update the cached entry
6. THE Cache SHALL store a UTC timestamp with each cached entry to determine data freshness
7. IF the user requests data that does not exist in the cache, THEN THE Cache SHALL fetch the data from the ESPN API, persist it locally with a timestamp, and return the result
8. IF a cache refresh is triggered and the network request to the ESPN API fails, THEN THE Cache SHALL return the stale cached data and indicate that the data may be outdated

### Requirement 5: Monte Carlo Simulation Engine

**User Story:** As a user, I want the application to run Monte Carlo simulations on remaining NFL games, so that I can see the probability distribution of playoff outcomes.

#### Acceptance Criteria

1. WHEN the user triggers a simulation, THE Simulator SHALL resolve all remaining unplayed games by assigning each game's winner (or tie) based on the competing teams' Team_Strength ratings independently per trial, across the configured number of trials
2. WHEN a simulation completes, THE Simulator SHALL calculate the final standings for each trial by ranking teams according to the NFL's official standings and tiebreaker rules (as defined in Requirement 10) using both completed results and simulated outcomes for that trial
3. WHEN a simulation completes, THE Simulator SHALL compute the probability of each team finishing in each playoff seeding position (1 through 7 per conference) as the number of trials in which the team finished in that position divided by the total number of trials
4. THE Simulator SHALL use completed game results as fixed inputs that do not change between trials
5. THE Simulator SHALL allow the user to configure the number of simulation trials with a minimum of 100 and a maximum of 1,000,000 (default: 10,000)
6. IF the user provides a trial count that is less than 100 or greater than 1,000,000 or is not a positive integer, THEN THE Simulator SHALL reject the input and indicate that the value must be a positive integer between 100 and 1,000,000
7. WHEN resolving a simulated game, THE Simulator SHALL assign a configurable probability of the game ending in a tie (default: 0.5%), with the remaining probability split between the two teams proportionally to their respective Team_Strength ratings
8. WHEN the simulation encounters a game with status "in-progress", THE Simulator SHALL treat that game as an unplayed game and simulate it from scratch based on Team_Strength ratings, without using the current live score to influence outcome probabilities
9. THE Simulator SHALL accept an optional Cutoff_Week parameter (integer 1 through 18) that specifies the last week whose completed game results are used as fixed inputs for the simulation
10. WHEN a Cutoff_Week is specified, THE Simulator SHALL treat all games in weeks 1 through the Cutoff_Week that have status "completed" as fixed inputs, and treat all games in weeks after the Cutoff_Week as unplayed games to be simulated regardless of their actual status in the Cache
11. IF no Cutoff_Week is specified, THEN THE Simulator SHALL default to the latest week number in which all games have status "completed" as the Cutoff_Week
12. IF the user provides a Cutoff_Week value that is less than 1 or greater than 18 or is not a positive integer, THEN THE Simulator SHALL reject the input and indicate that the value must be a positive integer between 1 and 18
13. WHEN calculating Team_Strength ratings with a Cutoff_Week specified, THE Simulator SHALL use only completed game results from weeks 1 through the Cutoff_Week as inputs to the rating calculation

### Requirement 6: Playoff Scenario Analysis

**User Story:** As a user, I want to see all possible scenarios that determine NFL playoff rankings, so that I can understand what outcomes matter for each team.

#### Acceptance Criteria

1. WHEN a simulation completes, THE Simulator SHALL identify all distinct playoff ranking outcomes observed across simulation runs, where a distinct outcome is a unique assignment of teams to seeding positions 1 through 7 within each conference (14 total playoff spots)
2. WHEN a simulation completes, THE Simulator SHALL report the probability of each team making the playoffs as a percentage with 1 decimal place precision, calculated as the number of simulation runs in which the team qualified for one of the 7 playoff spots in its conference divided by the total number of simulation runs
3. WHEN a simulation completes, THE Simulator SHALL report the probability distribution of seeding positions 1 through 7 for each team within its conference, expressed as a percentage with 1 decimal place precision for each position
4. WHEN the user requests scenario details for a specific team, THE Simulator SHALL display up to 5 remaining games whose outcomes produce the largest change in that team's playoff probability, ranked from highest impact to lowest
5. IF a simulation completes with fewer than 100 runs, THEN THE Simulator SHALL indicate that the reported probabilities have low confidence due to insufficient sample size

### Requirement 7: Web-Based Results Presentation

**User Story:** As a user, I want simulation results, current standings, and team schedules presented in an interactive web interface, so that I can explore the full state of the NFL season and playoff probabilities visually in my browser.

#### Acceptance Criteria

1. WHEN simulation results are available, THE Web_UI SHALL display a summary table showing each team's probability of making the playoffs, grouped by conference (AFC and NFC) and sorted by probability in descending order within each conference
2. WHEN simulation results are available, THE Web_UI SHALL display a seeding probability matrix showing each team's chance at each seed position (1 through 7), with teams as rows and seed positions as columns, grouped by conference
3. THE Web_UI SHALL format probabilities as percentages with one decimal place precision (e.g., "45.3%")
4. WHEN the user selects a detailed view, THE Web_UI SHALL display the top 50 most likely distinct playoff bracket scenarios and their associated probabilities
5. IF two or more teams have equal playoff probability, THEN THE Web_UI SHALL sort those teams alphabetically by team name
6. WHEN simulation results are available, THE Web_UI SHALL provide a visual chart (bar chart or heatmap) showing the seeding probability distribution for each team within a selected conference
7. WHEN the user clicks on a team in the results view, THE Web_UI SHALL display that team's scenario details including the top 5 highest-impact remaining games
8. WHEN season data has been fetched, THE Web_UI SHALL display a Standings_View showing current NFL standings organized by conference (AFC and NFC) and within each conference by division (East, North, South, West), with each team's won-lost-tied record and Win_Percentage
9. WHEN the user selects a team from the Standings_View or any team listing, THE Web_UI SHALL navigate to the Team_Schedule_View displaying all games for that team in the current season

### Requirement 8: Web Application Server

**User Story:** As a user, I want to start the application from the command line and access it through my web browser, so that I can interact with the simulation through a rich graphical interface.

#### Acceptance Criteria

1. WHEN the user executes the start command from the command line, THE Web_Server SHALL start an HTTP server on a configurable port (default: 8080) and serve the Frontend files
2. WHEN the Web_Server starts successfully, THE Web_Server SHALL print the local URL (e.g., "http://localhost:8080") to the terminal so the user knows where to access the application
3. THE Web_Server SHALL expose a REST API endpoint to trigger fetching and updating NFL season data from the ESPN JSON API via the Data_Client, returning a JSON response indicating the number of games fetched upon completion
4. THE Web_Server SHALL expose a REST API endpoint to run the Monte Carlo simulation, accepting a JSON request body with an optional iteration count parameter that defaults to 10,000 iterations when not specified and an optional cutoff_week parameter (integer 1 through 18) that defaults to the latest fully completed week when not specified, and returning simulation results as JSON
5. THE Web_Server SHALL expose a REST API endpoint to retrieve cached data status (last fetch time, number of games cached) as a JSON response
6. THE Web_Server SHALL accept a command-line parameter to specify the NFL season year for simulation
7. IF the user provides an invalid command-line parameter at startup, THEN THE Web_Server SHALL display a usage help message with available options and exit with a non-zero exit code
8. IF a REST API request fails due to a network error or the ESPN API being unavailable, THEN THE API SHALL return an appropriate HTTP error status code (5xx) with a JSON error body indicating the failure reason
9. IF the simulation API is called and no cached data exists for the specified season year, THEN THE API SHALL return HTTP 409 Conflict with a JSON error body indicating that data must be fetched first
10. THE Web_Server SHALL serve all Frontend static files (HTML, CSS, JavaScript) from a configured directory without requiring an external web server
11. THE Web_Server SHALL expose a REST API endpoint to retrieve current standings (computed from cached game data) as a JSON response, including each team's won-lost-tied record, Win_Percentage, and division/conference grouping
12. THE Web_Server SHALL expose a REST API endpoint to retrieve a specific team's schedule (all games for that team including completed, in-progress, and scheduled games) as a JSON response

### Requirement 9: Team Strength Rating

**User Story:** As a user, I want the simulation to determine each team's strength by evaluating the quality of opponents they have played against, so that a win against a strong team counts more than a win against a weak team and game outcome probabilities reflect meaningful performance differences.

#### Acceptance Criteria

1. WHEN a simulation is triggered, THE Simulator SHALL calculate a Team_Strength rating for each team using a strength-of-schedule-weighted algorithm where each game result is weighted by the opponent's Team_Strength rating
2. WHEN calculating Team_Strength, THE Simulator SHALL weight wins against opponents with high Team_Strength ratings more heavily than wins against opponents with low Team_Strength ratings
3. WHEN calculating Team_Strength, THE Simulator SHALL weight losses against opponents with low Team_Strength ratings as more damaging to the team's rating than losses against opponents with high Team_Strength ratings
4. WHEN calculating Team_Strength ratings, THE Simulator SHALL use an iterative computation that recalculates all team ratings repeatedly until the ratings converge (the maximum change in any team's rating between iterations is less than 0.001), resolving the circular dependency where each team's strength depends on the strength of its opponents
5. IF the iterative Team_Strength calculation does not converge within 100 iterations, THEN THE Simulator SHALL use the ratings from the final iteration and log a warning indicating that convergence was not achieved
6. WHEN resolving a simulated game between two teams, THE Simulator SHALL weight the probability of each team winning proportionally to their respective Team_Strength ratings, so that a stronger team has a higher probability of winning than a weaker team
7. WHEN two teams with equal Team_Strength ratings are matched, THE Simulator SHALL assign each team a 50% probability of winning that game
8. IF a team has no completed games in the current season, THEN THE Simulator SHALL assign that team a default Team_Strength rating equal to the league-wide average strength
9. WHEN Team_Strength ratings are calculated, THE Simulator SHALL use only completed game results from the current season as inputs to the rating calculation
10. WHEN simulation results are displayed, THE Web_UI SHALL provide an option to show each team's calculated Team_Strength rating alongside the playoff probabilities

### Requirement 10: NFL Standings and Tiebreaker Rules

**User Story:** As a user, I want the simulation to apply the official NFL standings and tiebreaker rules, so that playoff qualification and seeding accurately reflect how the NFL determines its postseason field.

#### Acceptance Criteria

1. THE Standings_Engine SHALL model the NFL's 32 teams organized into 2 conferences (AFC and NFC), each containing 4 divisions (East, North, South, West) of 4 teams each
2. THE Standings_Engine SHALL calculate each team's won-lost-tied record where a tie game counts as one-half win and one-half loss for winning percentage purposes
3. WHEN determining playoff qualification, THE Standings_Engine SHALL select 7 teams from each conference: 4 Division_Champions (the team with the best record in each division) seeded 1 through 4 by overall won-lost-tied record, and 3 Wild_Card teams (the next best records in the conference regardless of division) seeded 5 through 7
4. WHEN two teams in the same division are tied in won-lost-tied percentage, THE Standings_Engine SHALL apply the NFL division tiebreaker steps in order: head-to-head record, division record, record in common games, conference record, strength of victory, strength of schedule, combined ranking in conference points scored and points allowed, combined ranking in all-games points scored and points allowed, net points in common games, net points in all games, net touchdowns in all games, and coin toss (random selection)
5. WHEN two teams from different divisions in the same conference are tied in won-lost-tied percentage for a Wild_Card spot, THE Standings_Engine SHALL apply the NFL conference tiebreaker steps in order: head-to-head record (if applicable), conference record, record in common games (minimum 4 common games), strength of victory, strength of schedule, combined ranking in conference points scored and points allowed, combined ranking in all-games points scored and points allowed, net points in common games, net points in all games, net touchdowns in all games, and coin toss (random selection)
6. WHEN three or more teams are tied, THE Standings_Engine SHALL apply the applicable tiebreaker procedure collectively, and IF one team is eliminated at any step, THE Standings_Engine SHALL restart the tiebreaker procedure from step 1 for the remaining tied teams
7. WHEN determining Division_Champion seeding (seeds 1-4), THE Standings_Engine SHALL rank the 4 Division_Champions by overall won-lost-tied record, applying the conference tiebreaker procedure to break ties between Division_Champions from different divisions
8. THE Standings_Engine SHALL grant the number 1 seed in each conference a first-round Bye, exempting that team from the Wild Card Round
9. WHEN constructing the playoff bracket for the Wild Card Round, THE Standings_Engine SHALL pair seed 2 versus seed 7, seed 3 versus seed 6, and seed 4 versus seed 5, with the higher seed hosting each game
10. WHEN constructing the playoff bracket for the Divisional Round, THE Standings_Engine SHALL re-seed remaining teams so that the number 1 seed (returning from Bye) hosts the lowest remaining seed, and the other two remaining teams play with the higher seed hosting
11. WHEN constructing the Conference Championship bracket, THE Standings_Engine SHALL pair the two remaining teams in each conference with the higher seed hosting
12. THE Standings_Engine SHALL model the Super Bowl as a neutral-site game between the AFC and NFC conference champions
13. WHEN applying tiebreaker steps that require point-based data (points scored, points allowed, net points, net touchdowns) to simulated games, THE Standings_Engine SHALL skip those steps and proceed to the next applicable tiebreaker step, since simulated games produce only win/loss/tie outcomes without point differentials
14. WHEN applying tiebreaker steps that require point-based data to completed (real) games, THE Standings_Engine SHALL use the actual points scored data from the game results

### Requirement 11: Web Frontend

**User Story:** As a user, I want an interactive HTML/JavaScript frontend in my browser, so that I can view current standings, browse team schedules, control simulations, and explore all possible playoff outcomes without using a command line.

#### Acceptance Criteria

1. THE Frontend SHALL provide a control panel allowing the user to trigger data fetching from the ESPN API, configure simulation parameters (season year and trial count), and start a simulation run
2. WHEN a simulation is running, THE Frontend SHALL display a progress indicator to inform the user that the simulation is in progress
3. WHEN the user triggers a data fetch or simulation via the Frontend, THE Frontend SHALL call the corresponding REST API endpoint on the Web_Server and display the response to the user
4. IF an API call returns an error response, THEN THE Frontend SHALL display the error message from the JSON response body in a visible notification area without requiring a page reload
5. THE Frontend SHALL render without requiring any build step or external dependencies beyond the files served by the Web_Server (plain HTML, CSS, and JavaScript)
6. THE Frontend SHALL provide a navigation mechanism allowing the user to switch between the standings view, the control panel view, the team schedule view, and the simulation results view
7. WHEN the user selects a conference filter (AFC or NFC), THE Frontend SHALL filter displayed results to show only teams from the selected conference
8. THE Frontend SHALL be usable on screen widths from 1024 pixels to 1920 pixels without horizontal scrolling or content overflow
9. THE Frontend SHALL provide a standings page that displays current NFL standings grouped by conference (AFC and NFC) and within each conference by division (East, North, South, West), showing each team's wins, losses, ties, and Win_Percentage
10. THE Frontend SHALL provide a team detail page that displays all games for a selected team, showing completed games with final scores, in-progress games with current scores and game clock, and scheduled games with date and opponent
11. THE Frontend SHALL provide a simulation controls section with a numeric input field for the number of simulation rounds (constrained to 100 through 1,000,000), a week selector control (dropdown or slider) allowing the user to choose the Cutoff_Week (1 through 18) with the default set to the latest week where all games are completed, and a "Run Simulation" button to initiate the simulation
12. WHEN a simulation completes, THE Frontend SHALL display a simulation results page showing the top 50 most likely distinct playoff bracket scenarios observed during the simulation, including each team's playoff probability and seeding distribution
13. WHEN the user clicks on a team name in the standings page, THE Frontend SHALL navigate to the team detail page for that team
14. WHEN the user changes the Cutoff_Week selector, THE Frontend SHALL display a label indicating which week is selected and that games after the selected week will be simulated

### Requirement 12: Standings Display

**User Story:** As a user, I want to see the current NFL standings organized by conference and division, so that I can understand each team's position in the league before and after running simulations.

#### Acceptance Criteria

1. WHEN season data has been fetched, THE Web_UI SHALL display a standings table for each of the 8 divisions (AFC East, AFC North, AFC South, AFC West, NFC East, NFC North, NFC South, NFC West), grouped under their respective conference heading
2. THE Web_UI SHALL display the following columns for each team in the standings table: team name, wins, losses, ties, Win_Percentage (formatted as a 3-decimal value, e.g., ".750"), and Games_Behind the division leader
3. THE Web_UI SHALL sort teams within each division by Win_Percentage in descending order, with the division leader (highest Win_Percentage) listed first
4. IF two or more teams in the same division have equal Win_Percentage, THEN THE Web_UI SHALL sort those teams alphabetically by team name within the standings display
5. THE Web_UI SHALL visually distinguish the division leader from other teams in each division (e.g., bold text or a highlight indicator)
6. WHEN the user clicks on a team name in the standings table, THE Web_UI SHALL navigate to the Team_Schedule_View for that team
7. THE Web_UI SHALL display the standings data from the most recently fetched season data without requiring a simulation to have been run

### Requirement 13: Team Schedule Display

**User Story:** As a user, I want to view a selected team's full season schedule with game results and upcoming matchups, so that I can see how the team has performed and what games remain.

#### Acceptance Criteria

1. WHEN the user navigates to the Team_Schedule_View for a selected team, THE Web_UI SHALL display all regular season games for that team in chronological order (week 1 through week 18)
2. WHEN displaying a completed game, THE Web_UI SHALL show the week number, opponent name, whether the game was home or away, the final score for both teams, and the result (win, loss, or tie) for the selected team
3. WHEN displaying an in-progress game, THE Web_UI SHALL show the opponent name, whether the game is home or away, the current score for both teams, the current quarter, and the game clock remaining
4. WHEN displaying a scheduled game, THE Web_UI SHALL show the week number, opponent name, whether the game is home or away, and the scheduled date and time
5. THE Web_UI SHALL visually distinguish between completed games, in-progress games, and scheduled games using distinct styling (e.g., different background colors or status indicators)
6. THE Web_UI SHALL display a summary header showing the selected team's name, current won-lost-tied record, and Win_Percentage
7. THE Web_UI SHALL provide a navigation element to return from the Team_Schedule_View to the Standings_View
8. IF no games exist for the selected team in the fetched data, THEN THE Web_UI SHALL display a message indicating that no schedule data is available for the selected team

### Requirement 14: Internet-Facing Deployment

**User Story:** As a user, I want to deploy the application on a public web server so that I can access it from the internet on any device.

#### Acceptance Criteria

1. THE application SHALL be deployable on a Linux web server and accessible via a public URL over HTTPS
2. THE application SHALL support running behind a reverse proxy (e.g., nginx) that handles TLS termination and forwards requests to the Python backend
3. THE application SHALL bind to a configurable host address (not just localhost) to accept connections from the reverse proxy, using the existing `--port` CLI argument
4. THE application SHOULD include documentation for deployment behind nginx with a sample configuration
5. THE application SHALL NOT expose any secrets, credentials, or internal paths in HTTP responses when accessed from the internet
6. THE application SHOULD support basic access restriction (e.g., HTTP Basic Auth or IP allowlist) to prevent unauthorized public access to the simulation endpoints
7. THE application SHALL serve all static assets (HTML, CSS, JS, images) locally without requiring external CDN access at runtime (team logos are already cached locally)
