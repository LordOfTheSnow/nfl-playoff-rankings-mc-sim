/**
 * Schedule Grid view for the NFL Playoff Rankings Monte Carlo Simulator.
 *
 * "Ledger" design (Modernist system): league-wide schedule grid with all 32
 * teams as rows and the season's weeks as columns (1–18, or 1–17 for a
 * pre-2021 season), reusing the same `.mdn-led-table`
 * component as Standings/Team Detail/Results/Statistics — see
 * design_handoff_standings_redesign/ for the design system this view now
 * matches (the handoff itself scoped Schedule Grid out as "close enough";
 * this brings it fully in line).
 *
 * Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4,
 *              3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 5.1, 5.4, 5.5,
 *              7.1, 7.2, 7.3, 7.4, 7.5
 */

"use strict";

/**
 * Render the schedule grid view into the given container element.
 *
 * @param {HTMLElement} contentEl - The main content container to render into.
 */
async function renderScheduleGrid(contentEl) {
  App.showLoading();

  try {
    const data = await API.getScheduleGrid();
    App.hideLoading();
    renderGrid(contentEl, data);
  } catch (err) {
    App.hideLoading();
    App.showError(err.message || "Failed to load schedule grid.");
  }
}

/**
 * Render the schedule grid table from API response data.
 *
 * @param {HTMLElement} contentEl - The main content container.
 * @param {Object} data - The API response with teams array.
 */
function renderGrid(contentEl, data) {
  contentEl.innerHTML = "";

  const teams = data.teams || [];
  const seasonWeeks = data.season_weeks || (teams[0] && teams[0].weeks && teams[0].weeks.length) || 18;

  // Reverse lookup (abbreviation -> full team name), used to link each
  // opponent cell to that opponent's own Team Detail page — the row's own
  // team is already linked via the TEAM column, so linking there too would
  // be redundant and surprising.
  const teamByAbbreviation = {};
  teams.forEach(function (t) {
    if (t.abbreviation) teamByAbbreviation[t.abbreviation] = t.team;
  });

  const root = document.createElement("div");
  root.className = "mdn-page";
  contentEl.appendChild(root);

  const title = document.createElement("h1");
  title.style.cssText = "font:800 34px var(--mdn-font-heading);margin:0 0 6px";
  title.textContent = "Schedule Grid";
  root.appendChild(title);

  const subtitle = document.createElement("p");
  subtitle.className = "mdn-hint";
  subtitle.style.margin = "0 0 20px";
  subtitle.textContent = "All 32 teams · weeks 1–" + seasonWeeks;
  root.appendChild(subtitle);

  // Sort teams alphabetically by abbreviation
  const sorted = teams.slice().sort(function (a, b) {
    const abbA = a.abbreviation || "";
    const abbB = b.abbreviation || "";
    return abbA.localeCompare(abbB);
  });

  // Create wrapper for responsive scrolling
  const wrapper = document.createElement("div");
  wrapper.className = "mdn-grid-wrapper";

  // Create table
  const table = document.createElement("table");
  table.className = "mdn-led-table mdn-grid-table";

  // Build thead
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");

  const teamTh = document.createElement("th");
  teamTh.setAttribute("scope", "col");
  teamTh.textContent = "TEAM";
  headerRow.appendChild(teamTh);

  for (let week = 1; week <= seasonWeeks; week++) {
    const th = document.createElement("th");
    th.setAttribute("scope", "col");
    th.textContent = String(week);
    headerRow.appendChild(th);
  }

  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Build tbody
  const tbody = document.createElement("tbody");

  for (let i = 0; i < sorted.length; i++) {
    const entry = sorted[i];
    const row = document.createElement("tr");

    // Team cell with logo, abbreviation, and link
    const teamCell = document.createElement("td");
    teamCell.setAttribute("scope", "row");

    const teamLink = document.createElement("a");
    teamLink.href = "#team/" + encodeURIComponent(entry.team);
    teamLink.className = "mdn-grid-team-link";

    // Team logo
    const logoId = TEAM_LOGO_IDS[entry.team];
    if (logoId) {
      const logo = document.createElement("img");
      logo.src = "img/logos/" + logoId + ".png";
      logo.alt = entry.team + " logo";
      logo.width = 28;
      logo.height = 28;
      teamLink.appendChild(logo);
    }

    // Abbreviation text
    const abbText = document.createTextNode(entry.abbreviation || "");
    teamLink.appendChild(abbText);

    teamCell.appendChild(teamLink);
    row.appendChild(teamCell);

    // Week cells
    const weeks = entry.weeks || [];
    for (let w = 0; w < seasonWeeks; w++) {
      const weekEntry = weeks[w] || null;
      const cell = document.createElement("td");

      if (weekEntry === null) {
        // Bye week
        const byeSpan = document.createElement("span");
        byeSpan.className = "text-muted mdn-bye";
        byeSpan.textContent = "BYE";
        cell.appendChild(byeSpan);
      } else {
        const opponent = weekEntry.opponent || "";
        const isHome = weekEntry.home;
        const status = weekEntry.status;
        const teamScore = weekEntry.team_score;
        const oppScore = weekEntry.opponent_score;
        const hasScores = teamScore != null && oppScore != null;

        const oppText = isHome ? opponent : "@" + opponent;

        if ((status === "completed" || status === "in-progress") && hasScores) {
          const scoreText = status === "in-progress"
            ? teamScore + "-" + oppScore + " (r)"
            : teamScore + "-" + oppScore;
          cell.appendChild(_buildGridWeekCell(opponent, oppText, scoreText, teamByAbbreviation, false));
        } else if (status === "postponed" || status === "cancelled") {
          // Postponed/cancelled game — show the opponent plus a distinct
          // label so it isn't mistaken for a normal scheduled game or,
          // worse, a bye week (it isn't null, so it never renders as BYE).
          const label = status === "cancelled" ? "Canceled" : "Postponed";
          cell.appendChild(_buildGridWeekCell(opponent, oppText, label, teamByAbbreviation, true));
        } else {
          // Scheduled game or missing scores — just show opponent abbreviation
          cell.textContent = oppText;
        }
      }

      row.appendChild(cell);
    }

    tbody.appendChild(row);
  }

  table.appendChild(tbody);
  wrapper.appendChild(table);
  root.appendChild(wrapper);

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
 * Build a two-line week cell (opponent + a sub-label) used for scored games
 * (opponent + score) as well as postponed/cancelled games (opponent +
 * status label). Linked to the opponent's own Team Detail page whenever
 * their full name can be resolved, so a canceled/postponed game is still
 * as navigable as a played one — only plain (unlinked) text when it can't
 * be resolved, rather than guessing.
 *
 * @param {string} opponentAbbr - The opponent's abbreviation (grid key).
 * @param {string} oppText - The opponent text to display (with "@" prefix for away games).
 * @param {string} subLabel - The second line: a score string or a status label.
 * @param {Object} teamByAbbreviation - Map of abbreviation -> full team name.
 * @param {boolean} italicSubLabel - Whether the sub-label reads as a status note (italic) rather than a score.
 * @returns {HTMLElement} The cell content element (an `<a>` or `<div>`).
 */
function _buildGridWeekCell(opponentAbbr, oppText, subLabel, teamByAbbreviation, italicSubLabel) {
  const opponentTeam = teamByAbbreviation[opponentAbbr];
  const container = document.createElement(opponentTeam ? "a" : "div");
  if (opponentTeam) {
    container.href = "#team/" + encodeURIComponent(opponentTeam);
    container.className = "mdn-grid-score-link";
  }

  const oppSpan = document.createElement("div");
  oppSpan.textContent = oppText;
  container.appendChild(oppSpan);

  const subSpan = document.createElement("div");
  subSpan.className = "mdn-hint";
  subSpan.style.cssText = italicSubLabel ? "font-size:10px;font-style:italic" : "font-size:10px";
  subSpan.textContent = subLabel;
  container.appendChild(subSpan);

  return container;
}
