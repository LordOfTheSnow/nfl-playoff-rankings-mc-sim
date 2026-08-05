/**
 * Team Schedule ("Team Detail") view for the NFL Monte Carlo Playoff Simulator.
 *
 * "Ledger" design (Modernist system): single-team schedule table reusing the
 * same `.mdn-led-table` component as Standings, with a team hero header and
 * a Win/Loss/Tie result tag per game — see design_handoff_standings_redesign/
 * for the source spec this view implements (Option 2a).
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
  const root = document.createElement("div");
  root.className = "mdn-page";
  contentEl.appendChild(root);

  // Back navigation link
  const backLink = document.createElement("a");
  backLink.href = "#";
  backLink.className = "mdn-back-link";
  backLink.textContent = "← Back";
  backLink.addEventListener("click", function (e) {
    e.preventDefault();
    history.back();
  });
  root.appendChild(backLink);

  // Team hero header with logo, name, and record
  const hero = document.createElement("div");
  hero.className = "mdn-team-hero";

  const logoId = typeof TEAM_LOGO_IDS !== "undefined" ? TEAM_LOGO_IDS[team] : null;
  if (logoId) {
    const logo = document.createElement("img");
    logo.src = "img/logos/" + logoId + ".png";
    logo.alt = "";
    logo.width = 40;
    logo.height = 40;
    hero.appendChild(logo);
  }

  const teamTitle = document.createElement("h1");
  teamTitle.textContent = team;
  hero.appendChild(teamTitle);

  root.appendChild(hero);

  const recordEl = document.createElement("p");
  recordEl.className = "mdn-team-record";
  recordEl.textContent = formatRecord(record);
  root.appendChild(recordEl);

  // Handle empty schedule
  if (!games || games.length === 0) {
    const emptyState = document.createElement("div");
    emptyState.className = "mdn-card";
    const emptyMsg = document.createElement("p");
    emptyMsg.style.margin = "0";
    emptyMsg.textContent = "No schedule data available for this team.";
    emptyState.appendChild(emptyMsg);
    root.appendChild(emptyState);
    return;
  }

  // Schedule table
  const table = document.createElement("table");
  table.className = "mdn-led-table";

  // Table header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const columns = [
    { label: "Week" },
    { label: "Opponent" },
    { label: "Opp Str", num: true },
    { label: "Home/Away" },
    { label: "Score", num: true },
    { label: "Result/Status" },
    { label: "Team Str", num: true },
  ];
  columns.forEach(function (col) {
    const th = document.createElement("th");
    th.textContent = col.label;
    if (col.num) th.className = "mdn-num";
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
      tbody.appendChild(_buildByeRow(byeWeek));
      byeInserted = true;
    }

    tbody.appendChild(_buildGameRow(game));
  });

  // If bye week wasn't inserted (it's after all games), append it
  if (byeWeek !== null && !byeInserted) {
    tbody.appendChild(_buildByeRow(byeWeek));
  }

  table.appendChild(tbody);
  root.appendChild(table);

  // Legend
  root.appendChild(_buildLegend());

  // Back to top
  const backTopWrap = document.createElement("div");
  backTopWrap.style.cssText = "text-align:center;padding:20px 0";
  const backTop = document.createElement("a");
  backTop.href = "#";
  backTop.className = "mdn-back-to-top";
  backTop.textContent = "↑ Back to top";
  backTop.addEventListener("click", function (e) {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  backTopWrap.appendChild(backTop);
  root.appendChild(backTopWrap);
}

/**
 * Build a bye-week row: week number, then a single italic label cell
 * spanning the remaining columns.
 *
 * @param {number} byeWeek - The bye week number.
 * @returns {HTMLTableRowElement}
 */
function _buildByeRow(byeWeek) {
  const row = document.createElement("tr");
  const weekCell = document.createElement("td");
  weekCell.textContent = byeWeek;
  row.appendChild(weekCell);
  const byeLabel = document.createElement("td");
  byeLabel.colSpan = 6;
  byeLabel.className = "mdn-bye";
  byeLabel.textContent = "BYE WEEK";
  row.appendChild(byeLabel);
  return row;
}

/**
 * Build a single game row for the given status (completed, in-progress, or scheduled).
 *
 * @param {Object} game - The game data object.
 * @returns {HTMLTableRowElement}
 */
function _buildGameRow(game) {
  const row = document.createElement("tr");

  const weekCell = document.createElement("td");
  weekCell.textContent = game.week;
  row.appendChild(weekCell);

  const oppCell = document.createElement("td");
  oppCell.style.fontWeight = "700";
  oppCell.textContent = game.opponent;
  row.appendChild(oppCell);

  const strCell = document.createElement("td");
  strCell.className = "mdn-num";
  strCell.style.opacity = "0.6";
  strCell.textContent = game.opponent_strength != null ? game.opponent_strength.toFixed(3) : "—";
  row.appendChild(strCell);

  const locCell = document.createElement("td");
  locCell.textContent = game.home ? "Home" : "Away";
  row.appendChild(locCell);

  const scoreCell = document.createElement("td");
  scoreCell.className = "mdn-num";
  scoreCell.textContent = formatGameScore(game);
  row.appendChild(scoreCell);

  const statusCell = document.createElement("td");
  switch (game.status) {
    case "completed": {
      const tag = _buildResultTag(game.result);
      if (tag) {
        statusCell.appendChild(tag);
      } else {
        statusCell.textContent = "—";
      }
      break;
    }
    case "in-progress": {
      const quarterText = game.quarter != null ? "Q" + game.quarter : "";
      const clockText = game.clock || "";
      statusCell.className = "mdn-hint";
      statusCell.textContent = quarterText + (clockText ? " " + clockText : "");
      break;
    }
    case "scheduled":
    default:
      statusCell.className = "mdn-hint";
      statusCell.textContent = game.date ? formatDate(game.date) : "TBD";
      break;
  }
  row.appendChild(statusCell);

  const teamStrCell = document.createElement("td");
  teamStrCell.className = "mdn-num";
  teamStrCell.textContent = game.team_strength != null ? game.team_strength.toFixed(3) : "—";
  row.appendChild(teamStrCell);

  return row;
}

/**
 * Build the Win/Loss/Tie result tag for a completed game.
 *
 * @param {string} result - "win", "loss", or "tie".
 * @returns {HTMLElement|null} The tag element, or null if the result is unrecognized.
 */
function _buildResultTag(result) {
  const tag = document.createElement("span");
  tag.className = "mdn-tag " + getResultClass(result);
  switch (result) {
    case "win":
      tag.textContent = "Win";
      break;
    case "loss":
      tag.textContent = "Loss";
      break;
    case "tie":
      tag.textContent = "Tie";
      break;
    default:
      return null;
  }
  return tag;
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
 * Get the Modernist tag CSS class for a game result.
 *
 * @param {string} result - "win", "loss", or "tie".
 * @returns {string} CSS class name (without the "mdn-tag" base class).
 */
function getResultClass(result) {
  switch (result) {
    case "win":
      return "mdn-tag-win-o";
    case "loss":
      // Shared with the Standings ELIMINATED badge for visual consistency.
      return "mdn-tag-elim";
    case "tie":
      return "mdn-tag-tie";
    default:
      return "";
  }
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
    return "—";
  }
  if (game.home) {
    return game.home_score + " - " + game.away_score;
  }
  return game.away_score + " - " + game.home_score;
}

/**
 * Build the bottom legend card explaining the Opp Str / Team Str columns —
 * one line per column definition rather than a single run-on paragraph.
 *
 * @returns {HTMLElement}
 */
function _buildLegend() {
  const card = document.createElement("div");
  card.className = "mdn-card";
  card.style.cssText = "margin:20px 0 28px;font-size:11.5px;line-height:1.7";

  const kicker = document.createElement("div");
  kicker.className = "mdn-card-kicker";
  kicker.textContent = "Legend";
  card.appendChild(kicker);

  const defs = [
    ["Opp Str", "opponent strength rating at that week (1.000 = league average; higher = stronger opponent)."],
    ["Team Str", "this team's strength rating at that week. Strength is recalculated weekly based on cumulative results and strength of schedule — values change as the season progresses."],
  ];

  const list = document.createElement("div");
  list.style.cssText = "display:flex;flex-direction:column;gap:4px;margin-top:4px";
  for (const [label, explanation] of defs) {
    const line = document.createElement("div");
    const strong = document.createElement("strong");
    strong.style.whiteSpace = "nowrap";
    strong.textContent = label;
    line.appendChild(strong);
    line.appendChild(document.createTextNode(" — " + explanation));
    list.appendChild(line);
  }
  card.appendChild(list);

  return card;
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
