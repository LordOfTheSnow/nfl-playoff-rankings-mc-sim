/**
 * Standings view rendering for the NFL Monte Carlo Playoff Simulator.
 *
 * Displays current NFL standings grouped by conference (AFC/NFC) and division,
 * with conference filtering, clickable team names, and division leader highlighting.
 *
 * Requirements: 7.8, 11.7, 11.9, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
 */

"use strict";

/**
 * ESPN team logo ID mapping.
 * Logo URL: https://a.espncdn.com/i/teamlogos/nfl/500/{id}.png
 */
const TEAM_LOGO_IDS = {
  "Bills": "buf",
  "Dolphins": "mia",
  "Patriots": "ne",
  "Jets": "nyj",
  "Ravens": "bal",
  "Bengals": "cin",
  "Browns": "cle",
  "Steelers": "pit",
  "Texans": "hou",
  "Colts": "ind",
  "Jaguars": "jax",
  "Titans": "ten",
  "Chiefs": "kc",
  "Broncos": "den",
  "Chargers": "lac",
  "Raiders": "lv",
  "Cowboys": "dal",
  "Eagles": "phi",
  "Giants": "nyg",
  "Commanders": "wsh",
  "Bears": "chi",
  "Lions": "det",
  "Packers": "gb",
  "Vikings": "min",
  "Falcons": "atl",
  "Panthers": "car",
  "Saints": "no",
  "Buccaneers": "tb",
  "Cardinals": "ari",
  "Rams": "lar",
  "49ers": "sf",
  "Seahawks": "sea",
};

/**
 * Render the standings view into the given container element.
 *
 * @param {HTMLElement} contentEl - The main content container to render into.
 */
async function renderStandings(contentEl) {
  App.showLoading();

  // First check status to show data summary
  let status = null;
  try {
    status = await API.fetchStatus();
  } catch (_) {
    // Ignore status errors
  }

  let data;
  try {
    data = await API.getStandings();
  } catch (err) {
    App.hideLoading();
    contentEl.innerHTML = "";
    // Show status info even when standings fail
    if (status && status.total_games === 0) {
      contentEl.appendChild(buildStatusPanel(status));
    } else if (status) {
      contentEl.appendChild(buildStatusPanel(status));
      App.showError(err.message || "Failed to load standings.");
    } else {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = "<p>Unable to load standings. Go to Simulate and click Fetch Data first.</p>";
      contentEl.appendChild(empty);
    }
    return;
  }

  App.hideLoading();

  if (!data || !data.conferences) {
    contentEl.innerHTML = "";
    if (status) {
      contentEl.appendChild(buildStatusPanel(status));
    } else {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = "<p>No standings data available. Please fetch data first.</p>";
      contentEl.appendChild(empty);
    }
    return;
  }

  contentEl.innerHTML = "";

  // Show status summary
  if (status && status.total_games > 0) {
    contentEl.appendChild(buildStatusPanel(status));
  }

  // Build filter bar
  const filterBar = buildFilterBar();
  contentEl.appendChild(filterBar);

  // Build conference sections
  const conferences = data.conferences;
  const conferenceNames = ["AFC", "NFC"];

  for (const conf of conferenceNames) {
    if (!conferences[conf]) continue;
    const section = buildConferenceSection(conf, conferences[conf]);
    contentEl.appendChild(section);
  }

  // Apply default filter (All)
  applyConferenceFilter("All", contentEl);

  // Add legend below all tables
  const legend = document.createElement("div");
  legend.style.cssText = "margin-top:1.5rem;padding:1rem;background:var(--color-surface);border-radius:var(--radius-md);box-shadow:var(--shadow-sm);font-size:0.8rem;color:var(--color-text-muted);line-height:1.8";
  legend.innerHTML = "<strong>Legend:</strong> " +
    "W = Wins, " +
    "L = Losses, " +
    "T = Ties, " +
    "Win% = Winning Percentage, " +
    "Div = Division Record, " +
    "Conf = Conference Record, " +
    "GB = Games Behind Division Leader, " +
    "Str = Team Strength Rating (1.000 = league average), " +
    "TB = Tiebreaker Used (H2H = Head-to-Head, Conf = Conference Record)";
  contentEl.appendChild(legend);
}

/**
 * Build the conference filter bar with AFC/NFC/All buttons.
 *
 * @returns {HTMLElement} The filter bar element.
 */
function buildFilterBar() {
  const bar = document.createElement("div");
  bar.className = "filter-bar";

  const label = document.createElement("span");
  label.className = "filter-label";
  label.textContent = "Conference:";
  bar.appendChild(label);

  const filters = ["All", "AFC", "NFC"];
  for (const filter of filters) {
    const btn = document.createElement("button");
    btn.className = "filter-btn" + (filter === "All" ? " active" : "");
    btn.textContent = filter;
    btn.setAttribute("data-filter", filter);
    btn.addEventListener("click", function () {
      // Update active state
      bar.querySelectorAll(".filter-btn").forEach(function (b) {
        b.classList.remove("active");
      });
      btn.classList.add("active");
      // Apply filter
      applyConferenceFilter(filter, bar.parentElement);
    });
    bar.appendChild(btn);
  }

  return bar;
}

/**
 * Apply conference filter to show/hide conference sections.
 *
 * @param {string} filter - "All", "AFC", or "NFC".
 * @param {HTMLElement} container - The parent container with conference sections.
 */
function applyConferenceFilter(filter, container) {
  const sections = container.querySelectorAll(".conference-section");
  sections.forEach(function (section) {
    const conf = section.getAttribute("data-conference");
    if (filter === "All" || conf === filter) {
      section.style.display = "";
    } else {
      section.style.display = "none";
    }
  });
}

/**
 * Build a conference section with all its divisions.
 *
 * @param {string} conferenceName - "AFC" or "NFC".
 * @param {Object} divisions - Map of division name to array of team standings.
 * @returns {HTMLElement} The conference section element.
 */
function buildConferenceSection(conferenceName, divisions) {
  const section = document.createElement("div");
  section.className = "conference-section";
  section.setAttribute("data-conference", conferenceName);

  const header = document.createElement("h2");
  header.className =
    "conference-header conference-header--" + conferenceName.toLowerCase();

  const confLogo = document.createElement("img");
  confLogo.src = "img/logos/" + conferenceName.toLowerCase() + ".png";
  confLogo.alt = conferenceName + " logo";
  confLogo.width = 28;
  confLogo.height = 28;
  confLogo.style.verticalAlign = "middle";
  confLogo.style.marginRight = "0.5rem";
  header.appendChild(confLogo);

  const confText = document.createTextNode(conferenceName);
  header.appendChild(confText);
  section.appendChild(header);

  const divisionOrder = ["East", "North", "South", "West"];
  for (const divName of divisionOrder) {
    if (!divisions[divName]) continue;
    const divSection = buildDivisionSection(divName, divisions[divName]);
    section.appendChild(divSection);
  }

  return section;
}

/**
 * Build a division section with its standings table.
 *
 * @param {string} divisionName - Division name (East, North, South, West).
 * @param {Array} teams - Array of team standings objects.
 * @returns {HTMLElement} The division section element.
 */
function buildDivisionSection(divisionName, teams) {
  const section = document.createElement("div");
  section.className = "division-section";

  const header = document.createElement("div");
  header.className = "division-header";
  header.textContent = divisionName;
  section.appendChild(header);

  // Use server-provided sort order (tiebreaker-aware)
  const sorted = teams;

  const table = document.createElement("table");
  table.className = "standings-table";

  // Table header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const columns = [
    { label: "Team", cls: "team-name" },
    { label: "W", cls: "numeric" },
    { label: "L", cls: "numeric" },
    { label: "T", cls: "numeric" },
    { label: "Win%", cls: "numeric" },
    { label: "Div", cls: "numeric" },
    { label: "Conf", cls: "numeric" },
    { label: "GB", cls: "numeric" },
    { label: "Str", cls: "numeric" },
    { label: "TB", cls: "" },
  ];

  for (const col of columns) {
    const th = document.createElement("th");
    th.textContent = col.label;
    if (col.cls === "numeric") {
      th.className = "numeric";
    }
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Table body
  const tbody = document.createElement("tbody");
  for (let i = 0; i < sorted.length; i++) {
    const team = sorted[i];
    const isLeader = i === 0;
    const row = buildTeamRow(team, isLeader);
    tbody.appendChild(row);
  }
  table.appendChild(tbody);

  section.appendChild(table);
  return section;
}

/**
 * Build a table row for a single team.
 *
 * @param {Object} team - Team standings object with team, wins, losses, ties, win_percentage, games_behind.
 * @param {boolean} isLeader - Whether this team is the division leader.
 * @returns {HTMLTableRowElement} The table row element.
 */
function buildTeamRow(team, isLeader) {
  const row = document.createElement("tr");
  if (isLeader) {
    row.className = "division-leader";
  }

  // Team name cell with logo and clickable link
  const nameCell = document.createElement("td");
  nameCell.className = "team-name";

  const nameWrapper = document.createElement("span");
  nameWrapper.style.display = "inline-flex";
  nameWrapper.style.alignItems = "center";
  nameWrapper.style.gap = "0.5rem";

  const logoId = TEAM_LOGO_IDS[team.team];
  if (logoId) {
    const logo = document.createElement("img");
    logo.src = "img/logos/" + logoId + ".png";
    logo.alt = team.team + " logo";
    logo.width = 20;
    logo.height = 20;
    logo.style.flexShrink = "0";
    logo.style.verticalAlign = "middle";
    nameWrapper.appendChild(logo);
  }

  const link = document.createElement("a");
  link.className = "team-link";
  link.href = "#team/" + encodeURIComponent(team.team);
  link.textContent = team.team;
  link.addEventListener("click", function (e) {
    e.preventDefault();
    App.navigate("team/" + encodeURIComponent(team.team));
  });
  nameWrapper.appendChild(link);
  nameCell.appendChild(nameWrapper);
  row.appendChild(nameCell);

  // Wins
  const winsCell = document.createElement("td");
  winsCell.className = "numeric";
  winsCell.textContent = team.wins != null ? team.wins : 0;
  row.appendChild(winsCell);

  // Losses
  const lossesCell = document.createElement("td");
  lossesCell.className = "numeric";
  lossesCell.textContent = team.losses != null ? team.losses : 0;
  row.appendChild(lossesCell);

  // Ties
  const tiesCell = document.createElement("td");
  tiesCell.className = "numeric";
  tiesCell.textContent = team.ties != null ? team.ties : 0;
  row.appendChild(tiesCell);

  // Win percentage
  const wpCell = document.createElement("td");
  wpCell.className = "numeric";
  wpCell.textContent = formatWinPercentage(team.win_percentage);
  row.appendChild(wpCell);

  // Division record
  const divCell = document.createElement("td");
  divCell.className = "numeric";
  divCell.textContent = team.division_record || "0-0-0";
  row.appendChild(divCell);

  // Conference record
  const confCell = document.createElement("td");
  confCell.className = "numeric";
  confCell.textContent = team.conference_record || "0-0-0";
  row.appendChild(confCell);

  // Games behind
  const gbCell = document.createElement("td");
  gbCell.className = "numeric";
  gbCell.textContent = formatGamesBehind(team.games_behind);
  row.appendChild(gbCell);

  // Strength rating
  const strCell = document.createElement("td");
  strCell.className = "numeric";
  strCell.textContent = team.strength != null ? team.strength.toFixed(3) : "1.000";
  row.appendChild(strCell);

  // Tiebreaker
  const tbCell = document.createElement("td");
  tbCell.textContent = team.tiebreaker || "";
  tbCell.style.fontSize = "0.8rem";
  tbCell.style.color = "var(--color-text-muted)";
  row.appendChild(tbCell);

  return row;
}

/**
 * Format win percentage as a 3-decimal string (e.g., ".750").
 *
 * @param {number|null|undefined} wp - Win percentage as a decimal (0.0 to 1.0).
 * @returns {string} Formatted win percentage.
 */
function formatWinPercentage(wp) {
  if (wp == null) return ".000";
  return wp.toFixed(3).replace(/^0/, "");
}

/**
 * Format games behind value.
 *
 * @param {number|null|undefined} gb - Games behind value.
 * @returns {string} Formatted games behind (e.g., "—" for leader, "2.0", "0.5").
 */
function formatGamesBehind(gb) {
  if (gb == null || gb === 0) return "\u2014";
  if (gb % 1 === 0) return gb.toFixed(1);
  return gb.toFixed(1);
}

/**
 * Build a status panel showing data fetch summary.
 *
 * @param {Object} status - Status object from /api/status.
 * @returns {HTMLElement} The status panel element.
 */
function buildStatusPanel(status) {
  const panel = document.createElement("div");
  panel.className = "controls-panel";
  panel.style.marginBottom = "1.5rem";

  if (!status || status.total_games === 0) {
    panel.innerHTML = `
      <p style="color:var(--color-text-muted)">No data fetched yet. Click <strong>Fetch Data</strong> to load game data from ESPN.</p>
      <div style="margin-top:0.75rem">
        <button id="btn-fetch-data-standings" class="btn btn-primary" type="button">Fetch Data</button>
      </div>
    `;
    setTimeout(() => {
      const btn = document.getElementById("btn-fetch-data-standings");
      if (btn) btn.addEventListener("click", _handleFetchFromStandings);
    }, 0);
    return panel;
  }

  const pctFetched = Math.round((status.total_games / status.expected_total) * 100);
  const gamesPerWeek = status.games_per_week || {};

  let html = '<div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:1rem">';

  // Left: data status
  html += '<div>';
  html += '<h2 style="font-size:1.1rem;margin-bottom:0.5rem">Season ' + status.season_year + ' Data</h2>';
  html += '<div style="display:flex;gap:1.5rem;flex-wrap:wrap;font-size:0.85rem">';
  html += '<span><strong>Weeks:</strong> ' + status.weeks_fetched + ' of 18</span>';
  html += '<span><strong>Games:</strong> ' + status.total_games + ' / ' + status.expected_total + ' (' + pctFetched + '%)</span>';
  html += '<span style="color:var(--color-success)"><strong>Completed:</strong> ' + status.completed + '</span>';
  if (status.in_progress > 0) {
    html += '<span style="color:var(--color-warning)"><strong>In Progress:</strong> ' + status.in_progress + '</span>';
  }
  if (status.scheduled > 0) {
    html += '<span style="color:var(--color-text-muted)"><strong>Scheduled:</strong> ' + status.scheduled + '</span>';
  }
  html += '</div>';
  if (status.last_fetch_time) {
    const fetchDate = new Date(status.last_fetch_time);
    html += '<p style="font-size:0.75rem;color:var(--color-text-muted);margin-top:0.25rem">Last fetched: ' + fetchDate.toLocaleString() + '</p>';
  }
  html += '</div>';

  // Right: simulation controls
  html += '<div>';
  html += '<h2 style="font-size:1.1rem;margin-bottom:0.5rem">Simulation</h2>';
  html += '<div style="display:flex;flex-wrap:wrap;gap:1.5rem;align-items:flex-end">';
  html += '<div class="control-field"><label for="sim-iterations-st">Iterations</label><input type="number" id="sim-iterations-st" min="100" max="1000000" value="' + (parseInt(localStorage.getItem('sim-iterations'), 10) || 10000) + '" style="width:100px"></div>';
  html += '<div class="control-field"><label for="sim-cutoff-st">Cutoff</label><select id="sim-cutoff-st" style="width:110px"><option value="">Auto</option>';
  for (let w = 1; w <= 18; w++) { html += '<option value="' + w + '"' + (localStorage.getItem('sim-cutoff') == w ? ' selected' : '') + '>Week ' + w + '</option>'; }
  html += '</select></div>';
  const savedNoise = localStorage.getItem('sim-noise') || '20';
  const noiseVal = (parseInt(savedNoise, 10) / 100).toFixed(2);
  const noiseLabel = parseFloat(noiseVal) <= 0.05 ? "none" : parseFloat(noiseVal) <= 0.15 ? "low" : parseFloat(noiseVal) <= 0.25 ? "moderate" : parseFloat(noiseVal) <= 0.4 ? "high" : "chaotic";
  html += '<div class="control-field"><label for="sim-noise-st" title="Per-game strength noise: adds random variance to each simulated game outcome, modeling the unpredictability of real NFL games (\'any given Sunday\')">Noise &#9432;</label><input type="range" id="sim-noise-st" min="0" max="100" value="' + savedNoise + '" style="width:100px" title="0 = pure strength, 0.2 = moderate variance, 0.5+ = very chaotic"><span id="sim-noise-label-st" style="font-size:0.75rem;color:var(--color-text-muted);margin-left:0.4rem">' + noiseVal + ' ' + noiseLabel + '</span></div>';
  const cpuCount = (status && status.cpu_count) ? status.cpu_count : 4;
  const savedWorkers = parseInt(localStorage.getItem('sim-workers'), 10) || cpuCount;
  html += '<div class="control-field"><label for="sim-workers-st" title="Parallel CPU cores: each Monte Carlo trial is independent, so batches run simultaneously across cores. More workers = faster simulation (near-linear speedup). Uses Python multiprocessing to bypass the GIL.">Workers &#9432;</label><input type="range" id="sim-workers-st" min="1" max="' + cpuCount + '" value="' + savedWorkers + '" style="width:80px" title="1 = single-process (no overhead), max = all available CPU cores running trial batches in parallel"><span id="sim-workers-label-st" style="font-size:0.75rem;color:var(--color-text-muted);margin-left:0.4rem">' + savedWorkers + (savedWorkers === 1 ? ' core' : ' cores') + '</span></div>';
  html += '<button id="btn-run-sim-standings" class="btn btn-primary" type="button">Simulate</button>';
  html += '<button id="btn-fetch-data-standings" class="btn btn-secondary" type="button">Fetch Data</button>';
  html += '</div>';
  html += '</div>';

  html += '</div>';

  // Total games info line
  html += '<p id="sim-total-st" style="font-size:0.8rem;color:var(--color-text-muted);margin-top:0.5rem"></p>';
  // Progress spinner
  html += '<div id="sim-progress-st" style="margin-top:0.75rem;display:none;align-items:center;gap:0.75rem"><div class="spinner"></div><span style="font-size:0.9rem;color:var(--color-text-muted)">Running simulation…</span></div>';

  panel.innerHTML = html;

  // Wire up event listeners after DOM insert
  setTimeout(() => {
    const iterInput = document.getElementById("sim-iterations-st");
    const cutoffSel = document.getElementById("sim-cutoff-st");
    const noiseSl = document.getElementById("sim-noise-st");
    const runBtn = document.getElementById("btn-run-sim-standings");
    const fetchBtn = document.getElementById("btn-fetch-data-standings");
    const totalEl = document.getElementById("sim-total-st");

    function updateTotal() {
      const iters = parseInt(iterInput.value, 10) || 10000;
      const cutoff = cutoffSel.value ? parseInt(cutoffSel.value, 10) : 18;
      let gamesToSim = 0;
      for (const [wk, cnt] of Object.entries(gamesPerWeek)) {
        if (parseInt(wk, 10) > cutoff) gamesToSim += cnt;
      }
      if (gamesToSim > 0) {
        totalEl.textContent = gamesToSim + ' games × ' + iters.toLocaleString() + ' iterations = ' + (gamesToSim * iters).toLocaleString() + ' game simulations';
      } else {
        totalEl.textContent = 'No games to simulate at this cutoff';
      }
    }

    if (iterInput) iterInput.addEventListener("input", updateTotal);
    if (cutoffSel) cutoffSel.addEventListener("change", updateTotal);
    updateTotal();

    // Persist values on change
    if (iterInput) iterInput.addEventListener("change", () => localStorage.setItem('sim-iterations', iterInput.value));
    if (cutoffSel) cutoffSel.addEventListener("change", () => localStorage.setItem('sim-cutoff', cutoffSel.value));

    // Noise label update
    if (noiseSl) noiseSl.addEventListener("input", () => {
      const val = (parseInt(noiseSl.value, 10) / 100).toFixed(2);
      const label = parseFloat(val) <= 0.05 ? "none" : parseFloat(val) <= 0.15 ? "low" : parseFloat(val) <= 0.25 ? "moderate" : parseFloat(val) <= 0.4 ? "high" : "chaotic";
      const labelEl = document.getElementById("sim-noise-label-st");
      if (labelEl) labelEl.textContent = val + " " + label;
      localStorage.setItem('sim-noise', noiseSl.value);
    });

    // Workers label update
    const workersSl = document.getElementById("sim-workers-st");
    if (workersSl) workersSl.addEventListener("input", () => {
      const val = parseInt(workersSl.value, 10);
      const labelEl = document.getElementById("sim-workers-label-st");
      if (labelEl) labelEl.textContent = val === 1 ? "1 core" : val + " cores";
      localStorage.setItem('sim-workers', val);
    });

    if (runBtn) runBtn.addEventListener("click", async () => {
      const iterations = parseInt(iterInput.value, 10) || 10000;
      const cutoffWeek = cutoffSel.value ? parseInt(cutoffSel.value, 10) : null;
      const noise = parseInt(noiseSl.value, 10) / 100;
      const numWorkers = workersSl ? parseInt(workersSl.value, 10) : null;

      if (iterations < 100 || iterations > 1000000) {
        App.showError("Iterations must be between 100 and 1,000,000.");
        return;
      }

      const progressEl = document.getElementById("sim-progress-st");
      progressEl.style.display = "flex";
      runBtn.disabled = true;

      try {
        const results = await API.runSimulation(iterations, cutoffWeek, noise, numWorkers);
        window._simulationResults = results;
        App.showInfo("Simulation complete.");
        App.navigate("results");
      } catch (err) {
        App.showError(err.message || "Simulation failed.");
      } finally {
        progressEl.style.display = "none";
        runBtn.disabled = false;
      }
    });

    if (fetchBtn) fetchBtn.addEventListener("click", _handleFetchFromStandings);
  }, 0);

  return panel;
}

/**
 * Handle fetch data from the standings page.
 */
async function _handleFetchFromStandings() {
  const btn = document.getElementById("btn-fetch-data-standings");
  if (btn) btn.disabled = true;
  App.showLoading();
  try {
    const result = await API.fetchData();
    App.showInfo("Data fetched: " + result.games_fetched + " games loaded.");
    // Reload standings to show updated data
    const contentEl = document.getElementById("content");
    if (contentEl) await renderStandings(contentEl);
  } catch (err) {
    App.showError(err.message || "Failed to fetch data.");
  } finally {
    App.hideLoading();
    if (btn) btn.disabled = false;
  }
}
