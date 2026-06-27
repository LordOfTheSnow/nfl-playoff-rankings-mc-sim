/**
 * Team Schedule View for the NFL Monte Carlo Playoff Simulator.
 *
 * Renders a selected team's full season schedule with completed,
 * in-progress, and scheduled games displayed chronologically.
 *
 * Requirements: 7.9, 11.10, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8
 */

"use strict";

/**
 * Render the team schedule view into the given container element.
 *
 * @param {HTMLElement} contentEl - The main content container to render into.
 * @param {string} teamName - The team name to fetch and display schedule for.
 */
async function renderSchedule(contentEl, teamName) {
  if (!contentEl || !teamName) {
    return;
  }

  App.showLoading();

  try {
    const data = await API.getTeamSchedule(teamName);
    App.hideLoading();
    renderScheduleContent(contentEl, data);
  } catch (err) {
    App.hideLoading();
    App.showError(err.message || "Failed to load team schedule.");
  }
}

/**
 * Render the schedule content from API response data.
 *
 * @param {HTMLElement} contentEl - The main content container.
 * @param {Object} data - The API response with team, record, and games.
 */
function renderScheduleContent(contentEl, data) {
  const { team, record, games } = data;

  contentEl.innerHTML = "";

  // Back navigation link
  const backLink = document.createElement("a");
  backLink.href = "#standings";
  backLink.className = "back-link";
  backLink.textContent = "\u2190 Back to Standings";
  backLink.addEventListener("click", function (e) {
    e.preventDefault();
    App.navigate("standings");
  });
  contentEl.appendChild(backLink);

  // Team header with name and record
  const header = document.createElement("div");
  header.className = "team-header";

  const teamTitle = document.createElement("h2");
  const logoId = typeof TEAM_LOGO_IDS !== "undefined" ? TEAM_LOGO_IDS[team] : null;
  if (logoId) {
    const logo = document.createElement("img");
    logo.src = "img/logos/" + logoId + ".png";
    logo.alt = team + " logo";
    logo.width = 28;
    logo.height = 28;
    logo.style.verticalAlign = "middle";
    logo.style.marginRight = "0.5rem";
    teamTitle.appendChild(logo);
  }
  teamTitle.appendChild(document.createTextNode(team));
  header.appendChild(teamTitle);

  const recordSpan = document.createElement("span");
  recordSpan.className = "team-record";
  recordSpan.textContent = formatRecord(record);
  header.appendChild(recordSpan);

  contentEl.appendChild(header);

  // Handle empty schedule
  if (!games || games.length === 0) {
    const emptyState = document.createElement("div");
    emptyState.className = "empty-state";
    const emptyMsg = document.createElement("p");
    emptyMsg.textContent = "No schedule data available for this team.";
    emptyState.appendChild(emptyMsg);
    contentEl.appendChild(emptyState);
    return;
  }

  // Schedule table
  const table = document.createElement("table");
  table.className = "table table-hover schedule-table";

  // Table header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const columns = ["Week", "Opponent", "Opp Str", "Home/Away", "Score", "Result/Status", "Team Str"];
  columns.forEach(function (col) {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Table body — games sorted chronologically by week, with bye week inserted
  const tbody = document.createElement("tbody");
  const sortedGames = games.slice().sort(function (a, b) {
    return a.week - b.week;
  });

  // Find bye week (weeks 1-17 only — bye weeks never occur in week 18)
  const gameWeeks = new Set(sortedGames.map(function (g) { return g.week; }));
  let byeWeek = null;
  for (let w = 1; w <= 17; w++) {
    if (!gameWeeks.has(w)) {
      byeWeek = w;
      break;
    }
  }

  // Build combined list with bye week inserted
  let byeInserted = false;
  sortedGames.forEach(function (game) {
    // Insert bye week row before the first game after the bye
    if (byeWeek !== null && !byeInserted && game.week > byeWeek) {
      const byeRow = document.createElement("tr");
      byeRow.style.backgroundColor = "var(--color-border-light)";
      const byeWeekCell = document.createElement("td");
      byeWeekCell.textContent = byeWeek;
      byeRow.appendChild(byeWeekCell);
      const byeLabel = document.createElement("td");
      byeLabel.colSpan = 6;
      byeLabel.textContent = "BYE WEEK";
      byeLabel.style.fontWeight = "600";
      byeLabel.style.color = "var(--color-text-muted)";
      byeLabel.style.fontStyle = "italic";
      byeRow.appendChild(byeLabel);
      tbody.appendChild(byeRow);
      byeInserted = true;
    }

    const row = document.createElement("tr");

    switch (game.status) {
      case "completed":
        renderCompletedGameRow(row, game);
        break;
      case "in-progress":
        renderInProgressGameRow(row, game);
        break;
      case "scheduled":
      default:
        renderScheduledGameRow(row, game);
        break;
    }

    tbody.appendChild(row);
  });

  // If bye week wasn't inserted (it's after all games), append it
  if (byeWeek !== null && !byeInserted) {
    const byeRow = document.createElement("tr");
    byeRow.style.backgroundColor = "var(--color-border-light)";
    const byeWeekCell = document.createElement("td");
    byeWeekCell.textContent = byeWeek;
    byeRow.appendChild(byeWeekCell);
    const byeLabel = document.createElement("td");
    byeLabel.colSpan = 6;
    byeLabel.textContent = "BYE WEEK";
    byeLabel.style.fontWeight = "600";
    byeLabel.style.color = "var(--color-text-muted)";
    byeLabel.style.fontStyle = "italic";
    byeRow.appendChild(byeLabel);
    tbody.appendChild(byeRow);
  }

  table.appendChild(tbody);
  contentEl.appendChild(table);

  // Legend
  const legend = document.createElement("div");
  legend.style.cssText = "margin-top:1rem;padding:0.75rem 1rem;background:var(--color-surface);border-radius:var(--radius-sm);box-shadow:var(--shadow-sm);font-size:0.8rem;color:var(--color-text-muted);line-height:1.8";
  legend.innerHTML =
    "<strong>Legend:</strong> " +
    "<strong>Opp Str</strong> = Opponent strength rating at that week (1.000 = league average; higher = stronger opponent). " +
    "<strong>Team Str</strong> = This team's strength rating at that week. " +
    "Strength is recalculated weekly based on cumulative results and strength of schedule — values change as the season progresses.";
  contentEl.appendChild(legend);
}

/**
 * Format the team record as "W-L-T (Win%)".
 *
 * @param {Object} record - The record object with wins, losses, ties, win_percentage.
 * @returns {string} Formatted record string.
 */
function formatRecord(record) {
  if (!record) {
    return "";
  }
  const { wins, losses, ties, win_percentage } = record;
  const pct = win_percentage != null ? " (" + formatWinPct(win_percentage) + ")" : "";
  return wins + "-" + losses + "-" + ties + pct;
}

/**
 * Format win percentage as a 3-decimal string (e.g., ".769").
 *
 * @param {number} pct - Win percentage as a decimal (0 to 1).
 * @returns {string} Formatted percentage string.
 */
function formatWinPct(pct) {
  return pct.toFixed(3).replace(/^0/, "");
}

/**
 * Render a completed game row.
 *
 * @param {HTMLTableRowElement} row - The table row element.
 * @param {Object} game - The game data object.
 */
function renderCompletedGameRow(row, game) {
  // Week
  const weekCell = document.createElement("td");
  weekCell.textContent = game.week;
  row.appendChild(weekCell);

  // Opponent
  const oppCell = document.createElement("td");
  oppCell.textContent = game.opponent;
  row.appendChild(oppCell);

  // Opponent Strength
  const strCell = document.createElement("td");
  strCell.textContent = game.opponent_strength != null ? game.opponent_strength.toFixed(3) : "—";
  strCell.style.fontSize = "0.85rem";
  strCell.style.color = "var(--color-text-muted)";
  row.appendChild(strCell);

  // Home/Away
  const locCell = document.createElement("td");
  locCell.textContent = game.home ? "Home" : "Away";
  row.appendChild(locCell);

  // Score
  const scoreCell = document.createElement("td");
  scoreCell.textContent = formatGameScore(game);
  row.appendChild(scoreCell);

  // Result
  const resultCell = document.createElement("td");
  const resultText = formatResult(game.result);
  resultCell.textContent = resultText;
  resultCell.className = getResultClass(game.result);
  row.appendChild(resultCell);

  // Team Strength
  const teamStrCell = document.createElement("td");
  teamStrCell.textContent = game.team_strength != null ? game.team_strength.toFixed(3) : "—";
  teamStrCell.style.fontSize = "0.85rem";
  teamStrCell.style.color = "var(--color-text-muted)";
  row.appendChild(teamStrCell);
}

/**
 * Render an in-progress game row.
 *
 * @param {HTMLTableRowElement} row - The table row element.
 * @param {Object} game - The game data object.
 */
function renderInProgressGameRow(row, game) {
  row.classList.add("game-status--in-progress");

  // Week
  const weekCell = document.createElement("td");
  weekCell.textContent = game.week;
  row.appendChild(weekCell);

  // Opponent
  const oppCell = document.createElement("td");
  oppCell.textContent = game.opponent;
  row.appendChild(oppCell);

  // Opponent Strength
  const strCell = document.createElement("td");
  strCell.textContent = game.opponent_strength != null ? game.opponent_strength.toFixed(3) : "—";
  strCell.style.fontSize = "0.85rem";
  strCell.style.color = "var(--color-text-muted)";
  row.appendChild(strCell);

  // Home/Away
  const locCell = document.createElement("td");
  locCell.textContent = game.home ? "Home" : "Away";
  row.appendChild(locCell);

  // Current score
  const scoreCell = document.createElement("td");
  scoreCell.textContent = formatGameScore(game);
  row.appendChild(scoreCell);

  // Status: quarter and clock
  const statusCell = document.createElement("td");
  statusCell.className = "game-status--in-progress";
  const quarterText = game.quarter != null ? "Q" + game.quarter : "";
  const clockText = game.clock || "";
  statusCell.textContent = quarterText + (clockText ? " " + clockText : "");
  row.appendChild(statusCell);

  // Team Strength
  const teamStrCell = document.createElement("td");
  teamStrCell.textContent = game.team_strength != null ? game.team_strength.toFixed(3) : "—";
  teamStrCell.style.fontSize = "0.85rem";
  teamStrCell.style.color = "var(--color-text-muted)";
  row.appendChild(teamStrCell);
}

/**
 * Render a scheduled game row.
 *
 * @param {HTMLTableRowElement} row - The table row element.
 * @param {Object} game - The game data object.
 */
function renderScheduledGameRow(row, game) {
  row.classList.add("game-status--scheduled");

  // Week
  const weekCell = document.createElement("td");
  weekCell.textContent = game.week;
  row.appendChild(weekCell);

  // Opponent
  const oppCell = document.createElement("td");
  oppCell.textContent = game.opponent;
  row.appendChild(oppCell);

  // Opponent Strength
  const strCell = document.createElement("td");
  strCell.textContent = game.opponent_strength != null ? game.opponent_strength.toFixed(3) : "—";
  strCell.style.fontSize = "0.85rem";
  strCell.style.color = "var(--color-text-muted)";
  row.appendChild(strCell);

  // Home/Away
  const locCell = document.createElement("td");
  locCell.textContent = game.home ? "Home" : "Away";
  row.appendChild(locCell);

  // Score (empty for scheduled)
  const scoreCell = document.createElement("td");
  scoreCell.textContent = "\u2014";
  row.appendChild(scoreCell);

  // Date
  const dateCell = document.createElement("td");
  dateCell.className = "game-status--scheduled";
  dateCell.textContent = game.date ? formatDate(game.date) : "TBD";
  row.appendChild(dateCell);

  // Team Strength
  const teamStrCell = document.createElement("td");
  teamStrCell.textContent = game.team_strength != null ? game.team_strength.toFixed(3) : "—";
  teamStrCell.style.fontSize = "0.85rem";
  teamStrCell.style.color = "var(--color-text-muted)";
  row.appendChild(teamStrCell);
}

/**
 * Format the game score display.
 * For home games: "team_score - opponent_score"
 * For away games: "team_score - opponent_score"
 * The home_score/away_score from the API are always home team first.
 *
 * @param {Object} game - The game data object.
 * @returns {string} Formatted score string.
 */
function formatGameScore(game) {
  if (game.home_score == null && game.away_score == null) {
    return "\u2014";
  }
  if (game.home) {
    return game.home_score + " - " + game.away_score;
  }
  return game.away_score + " - " + game.home_score;
}

/**
 * Format a game result string.
 *
 * @param {string} result - "win", "loss", or "tie".
 * @returns {string} Display text.
 */
function formatResult(result) {
  switch (result) {
    case "win":
      return "W";
    case "loss":
      return "L";
    case "tie":
      return "T";
    default:
      return "\u2014";
  }
}

/**
 * Get the CSS class for a game result.
 *
 * @param {string} result - "win", "loss", or "tie".
 * @returns {string} CSS class name.
 */
function getResultClass(result) {
  switch (result) {
    case "win":
      return "game-result--win";
    case "loss":
      return "game-result--loss";
    case "tie":
      return "game-result--tie";
    default:
      return "";
  }
}

/**
 * Format a date string (YYYY-MM-DD) into a readable format.
 *
 * @param {string} dateStr - ISO date string (e.g., "2024-12-22").
 * @returns {string} Formatted date (e.g., "Dec 22, 2024").
 */
function formatDate(dateStr) {
  if (!dateStr) {
    return "TBD";
  }
  const parts = dateStr.split("-");
  if (parts.length !== 3) {
    return dateStr;
  }
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const year = parts[0];
  const monthIndex = parseInt(parts[1], 10) - 1;
  const day = parseInt(parts[2], 10);
  if (monthIndex < 0 || monthIndex > 11 || isNaN(day)) {
    return dateStr;
  }
  return months[monthIndex] + " " + day + ", " + year;
}
