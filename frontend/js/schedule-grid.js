/**
 * Schedule Grid View for the NFL Monte Carlo Playoff Simulator.
 *
 * Renders a league-wide schedule grid with all 32 teams as rows and
 * weeks 1–18 as columns. Each cell shows the opponent abbreviation
 * (prefixed with "@" for away games), "BYE" for bye weeks, and scores
 * for completed/in-progress games.
 *
 * Requirements: 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4,
 *              3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 5.1, 5.4, 5.5,
 *              7.1, 7.2, 7.3, 7.4, 7.5
 */

"use strict";

/**
 * Team name to uppercase abbreviation mapping for cell display.
 */
const TEAM_ABBREVIATIONS = {
  "Bills": "BUF", "Dolphins": "MIA", "Patriots": "NE", "Jets": "NYJ",
  "Ravens": "BAL", "Bengals": "CIN", "Browns": "CLE", "Steelers": "PIT",
  "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Titans": "TEN",
  "Chiefs": "KC", "Broncos": "DEN", "Chargers": "LAC", "Raiders": "LV",
  "Cowboys": "DAL", "Eagles": "PHI", "Giants": "NYG", "Commanders": "WSH",
  "Bears": "CHI", "Lions": "DET", "Packers": "GB", "Vikings": "MIN",
  "Falcons": "ATL", "Panthers": "CAR", "Saints": "NO", "Buccaneers": "TB",
  "Cardinals": "ARI", "Rams": "LAR", "49ers": "SF", "Seahawks": "SEA",
};

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

  // Sort teams alphabetically by abbreviation
  const sorted = teams.slice().sort(function (a, b) {
    const abbA = a.abbreviation || "";
    const abbB = b.abbreviation || "";
    return abbA.localeCompare(abbB);
  });

  // Create wrapper for responsive scrolling
  const wrapper = document.createElement("div");
  wrapper.className = "schedule-grid-wrapper";

  // Create table
  const table = document.createElement("table");
  table.className = "table table-bordered schedule-grid";

  // Build thead
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");

  const teamTh = document.createElement("th");
  teamTh.setAttribute("scope", "col");
  teamTh.textContent = "TEAM";
  headerRow.appendChild(teamTh);

  for (let week = 1; week <= 18; week++) {
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
    teamLink.style.textDecoration = "none";
    teamLink.style.color = "inherit";
    teamLink.style.display = "inline-flex";
    teamLink.style.alignItems = "center";
    teamLink.style.gap = "0.25rem";

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
    for (let w = 0; w < 18; w++) {
      const weekEntry = weeks[w] || null;
      const cell = document.createElement("td");

      if (weekEntry === null) {
        // Bye week
        const byeSpan = document.createElement("span");
        byeSpan.className = "text-muted";
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
          // Render opponent + score (no link — no game detail page exists)
          const oppSpan = document.createElement("div");
          oppSpan.textContent = oppText;
          cell.appendChild(oppSpan);

          const scoreSpan = document.createElement("div");
          scoreSpan.style.fontSize = "smaller";
          if (status === "in-progress") {
            scoreSpan.textContent = teamScore + "-" + oppScore + " (r)";
          } else {
            scoreSpan.textContent = teamScore + "-" + oppScore;
          }
          cell.appendChild(scoreSpan);
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
  contentEl.appendChild(wrapper);
}
