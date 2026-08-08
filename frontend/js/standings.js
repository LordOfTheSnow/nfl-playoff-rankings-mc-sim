/**
 * Standings view rendering for the NFL Monte Carlo Playoff Simulator.
 *
 * "Ledger" design (Modernist system): dense per-division tables grouped by
 * conference, a Season/Simulation card, conference filtering, clinch/eliminate
 * badges, and a tiebreaker column — see design_handoff_standings_redesign/
 * for the source spec this view implements.
 *
 * Requirements: 7.8, 10.1, 10.2, 10.3, 10.5, 10.6, 11.7, 11.9, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
 */

"use strict";

/**
 * Module-level storage for CP solver clinch/elimination results.
 * Populated asynchronously after standings render; keyed by team name.
 * @type {Object<string, {status: string, solve_time_ms: number, num_variables: number, minimum_seed: number|null, magic_number: number|null}>|null}
 */
let _cpClinchResults = null;

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
 * Short tiebreaker code (from the server's `tiebreaker` field, e.g. "Div 4-1-0")
 * expanded to a human-readable rule name for the tooltip.
 */
const TIEBREAKER_RULE_NAMES = {
  H2H: "head-to-head record",
  Div: "division record",
  Conf: "conference record",
  SoV: "strength of victory",
  SoS: "strength of schedule",
  Pts: "net points",
  Alpha: "alphabetical order (final tiebreaker)",
};

/**
 * Ledger table column abbreviations, expanded for the legend card — one
 * entry per line rather than run together as inline prose.
 */
const COLUMN_DEFS = [
  ["W / L / T", "Wins, losses, ties"],
  ["PCT", "Winning percentage"],
  ["DIV", "Division record"],
  ["CONF", "Conference record"],
  ["GB", "Games behind the division leader"],
  ["STR", "Team strength rating (1.000 = league average)"],
];

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

  // Read cutoff week from localStorage (set by simulation controls)
  const savedCutoff = localStorage.getItem('sim-cutoff');
  const cutoffWeek = savedCutoff ? parseInt(savedCutoff, 10) : null;

  let data;
  try {
    data = await API.getStandings(cutoffWeek);
  } catch (err) {
    App.hideLoading();
    contentEl.innerHTML = "";
    const root = _buildStandingsRoot();
    contentEl.appendChild(root);
    // Show status info even when standings fail
    if (status && status.total_games === 0) {
      root.appendChild(buildStatusPanel(status));
    } else if (status) {
      root.appendChild(buildStatusPanel(status));
      App.showError(err.message || "Failed to load standings.");
    } else {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = "<p>Unable to load standings. Go to Simulate and click Fetch Data first.</p>";
      root.appendChild(empty);
    }
    return;
  }

  App.hideLoading();

  contentEl.innerHTML = "";
  const root = _buildStandingsRoot();
  contentEl.appendChild(root);

  if (!data || !data.conferences) {
    if (status) {
      root.appendChild(buildStatusPanel(status));
    } else {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = "<p>No standings data available. Please fetch data first.</p>";
      root.appendChild(empty);
    }
    return;
  }

  // Show status summary
  if (status && status.total_games > 0) {
    root.appendChild(buildStatusPanel(status));
  }

  // Build filter bar
  const filterBar = buildFilterBar();
  root.appendChild(filterBar);

  // Build conference sections
  const conferences = data.conferences;
  const conferenceNames = ["AFC", "NFC"];

  for (const conf of conferenceNames) {
    if (!conferences[conf]) continue;
    const section = buildConferenceSection(conf, conferences[conf]);
    root.appendChild(section);
  }

  // Apply default filter (All)
  applyConferenceFilter("All", root);

  // Add legend below all tables
  root.appendChild(buildLegend());

  // Fetch CP solver clinch/elimination data (non-blocking)
  _fetchAndApplyCPBadges(root, cutoffWeek);
}

/**
 * Create the scoping root element for the Modernist standings page.
 * Everything rendered by this module lives inside it so its typography/token
 * overrides don't leak into the still-Bootstrap-styled views.
 *
 * @returns {HTMLElement}
 */
function _buildStandingsRoot() {
  const root = document.createElement("div");
  root.className = "mdn-page";
  return root;
}

/**
 * Build the conference filter bar with AFC/NFC/All segmented control.
 *
 * @returns {HTMLElement} The filter bar element.
 */
function buildFilterBar() {
  const bar = document.createElement("div");
  bar.style.cssText = "display:flex;align-items:center;gap:14px;margin:22px 0 4px";

  const label = document.createElement("span");
  label.className = "mdn-stat-lbl";
  label.style.fontSize = "10px";
  label.textContent = "Conference";
  bar.appendChild(label);

  const seg = document.createElement("div");
  seg.className = "mdn-seg";

  const filters = ["All", "AFC", "NFC"];
  for (const filter of filters) {
    const opt = document.createElement("span");
    opt.className = "mdn-seg-opt" + (filter === "All" ? " active" : "");
    opt.textContent = filter;
    opt.setAttribute("data-filter", filter);
    opt.addEventListener("click", function () {
      seg.querySelectorAll("[data-filter]").forEach(function (o) {
        o.classList.remove("active");
      });
      opt.classList.add("active");
      applyConferenceFilter(filter, bar.parentElement);
    });
    seg.appendChild(opt);
  }
  bar.appendChild(seg);

  return bar;
}

/**
 * Apply conference filter to show/hide conference sections.
 *
 * @param {string} filter - "All", "AFC", or "NFC".
 * @param {HTMLElement} container - The parent container with conference sections.
 */
function applyConferenceFilter(filter, container) {
  if (!container) return;
  const sections = container.querySelectorAll(".mdn-conf-section");
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
  section.className = "mdn-conf-section";
  section.setAttribute("data-conference", conferenceName);

  const header = document.createElement("div");
  header.className = "mdn-conf-head";

  const confLogo = document.createElement("img");
  confLogo.src = "img/logos/" + conferenceName.toLowerCase() + ".png";
  confLogo.alt = conferenceName + " logo";
  confLogo.width = 26;
  confLogo.height = 26;
  header.appendChild(confLogo);

  const h2 = document.createElement("h2");
  h2.textContent = conferenceName;
  header.appendChild(h2);
  section.appendChild(header);

  const grid = document.createElement("div");
  grid.className = "mdn-div-grid";

  const divisionOrder = ["East", "North", "South", "West"];
  for (const divName of divisionOrder) {
    if (!divisions[divName]) continue;
    grid.appendChild(buildDivisionSection(divName, divisions[divName]));
  }
  section.appendChild(grid);

  return section;
}

/**
 * Build a division section with its ledger table.
 *
 * @param {string} divisionName - Division name (East, North, South, West).
 * @param {Array} teams - Array of team standings objects.
 * @returns {HTMLElement} The division section element.
 */
function buildDivisionSection(divisionName, teams) {
  const wrap = document.createElement("div");

  const label = document.createElement("div");
  label.className = "mdn-div-lbl";
  label.textContent = divisionName;
  wrap.appendChild(label);

  const table = document.createElement("table");
  table.className = "mdn-led-table";

  // Table header
  const thead = document.createElement("thead");
  const headerRow = document.createElement("tr");
  const columns = [
    { label: "Team" },
    { label: "W", num: true },
    { label: "L", num: true },
    { label: "T", num: true },
    { label: "Pct", num: true },
    { label: "Div", num: true },
    { label: "Conf", num: true },
    { label: "GB", num: true },
    { label: "Str", num: true },
    { label: "Tiebreaker" },
  ];

  for (const col of columns) {
    const th = document.createElement("th");
    th.textContent = col.label;
    if (col.num) {
      th.className = "mdn-num";
    }
    headerRow.appendChild(th);
  }
  thead.appendChild(headerRow);
  table.appendChild(thead);

  // Table body — use server-provided sort order (tiebreaker-aware)
  const tbody = document.createElement("tbody");
  for (let i = 0; i < teams.length; i++) {
    tbody.appendChild(buildTeamRow(teams[i], i === 0));
  }
  table.appendChild(tbody);

  wrap.appendChild(table);
  return wrap;
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
    row.className = "mdn-leader";
  }

  // Team name cell with logo and clickable link
  const nameCell = document.createElement("td");
  nameCell.className = "mdn-tm";

  const nameWrapper = document.createElement("div");
  nameWrapper.className = "mdn-team-cell";
  nameWrapper.setAttribute("data-team-name", team.team);

  const logoId = TEAM_LOGO_IDS[team.team];
  if (logoId) {
    const logo = document.createElement("img");
    logo.src = "img/logos/" + logoId + ".png";
    logo.alt = "";
    logo.width = 20;
    logo.height = 20;
    nameWrapper.appendChild(logo);
  }

  const link = document.createElement("a");
  link.className = "mdn-team-link";
  link.href = "#team/" + encodeURIComponent(team.team);
  link.textContent = team.team;
  link.addEventListener("click", function (e) {
    e.preventDefault();
    App.navigate("team/" + encodeURIComponent(team.team));
  });
  nameWrapper.appendChild(link);
  nameCell.appendChild(nameWrapper);
  row.appendChild(nameCell);

  row.appendChild(_numCell(team.wins != null ? team.wins : 0));
  row.appendChild(_numCell(team.losses != null ? team.losses : 0));
  row.appendChild(_numCell(team.ties != null ? team.ties : 0));
  row.appendChild(_numCell(formatWinPercentage(team.win_percentage)));
  row.appendChild(_numCell(team.division_record || "0-0-0"));
  row.appendChild(_numCell(team.conference_record || "0-0-0"));
  row.appendChild(_numCell(formatGamesBehind(team.games_behind)));
  row.appendChild(_numCell(team.strength != null ? team.strength.toFixed(3) : "1.000"));

  // Tiebreaker
  const tbCell = document.createElement("td");
  if (team.tiebreaker) {
    tbCell.appendChild(_buildTiebreakerTag(team.tiebreaker));
  }
  row.appendChild(tbCell);

  return row;
}

/**
 * Build a right-aligned numeric table cell.
 *
 * @param {string|number} value - Cell content.
 * @returns {HTMLTableCellElement}
 */
function _numCell(value) {
  const td = document.createElement("td");
  td.className = "mdn-num";
  td.textContent = value;
  return td;
}

/**
 * Build the outlined "Tiebreaker" chip + hover tooltip for a tied team.
 * The server only reports a short code (e.g. "Div 4-1-0"); the tooltip
 * expands the rule name since the API doesn't return the rival team or
 * full comparison.
 *
 * @param {string} tiebreaker - Short tiebreaker string, e.g. "Div 4-1-0".
 * @returns {HTMLElement}
 */
function _buildTiebreakerTag(tiebreaker) {
  const wrap = document.createElement("span");
  wrap.className = "mdn-tt-wrap";

  const tag = document.createElement("span");
  tag.className = "mdn-tag mdn-tag-outline";
  tag.textContent = tiebreaker;
  wrap.appendChild(tag);

  const code = tiebreaker.split(" ")[0];
  const ruleName = TIEBREAKER_RULE_NAMES[code] || "tiebreaker rule";
  const pop = document.createElement("span");
  pop.className = "mdn-tt-pop";
  pop.textContent = "Seeded by " + ruleName + ": " + tiebreaker + ".";
  wrap.appendChild(pop);

  return wrap;
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
  if (gb == null || gb === 0) return "—";
  return gb.toFixed(1);
}

/**
 * Build the bottom legend card explaining columns and status tags.
 *
 * @returns {HTMLElement}
 */
function buildLegend() {
  const card = document.createElement("div");
  card.className = "mdn-card mdn-legend";
  card.style.marginTop = "8px";

  const kicker = document.createElement("div");
  kicker.className = "mdn-card-kicker";
  kicker.textContent = "Legend";
  card.appendChild(kicker);

  const colsHeading = document.createElement("div");
  colsHeading.innerHTML = "<strong>Columns</strong>";
  colsHeading.style.cssText = "margin-top:8px;margin-bottom:4px";
  card.appendChild(colsHeading);

  const colsTable = document.createElement("table");
  colsTable.className = "mdn-legend-table";
  const colsBody = document.createElement("tbody");
  for (const [abbr, meaning] of COLUMN_DEFS) {
    const row = document.createElement("tr");
    const abbrCell = document.createElement("td");
    abbrCell.textContent = abbr;
    const meaningCell = document.createElement("td");
    meaningCell.textContent = meaning;
    row.appendChild(abbrCell);
    row.appendChild(meaningCell);
    colsBody.appendChild(row);
  }
  colsTable.appendChild(colsBody);
  card.appendChild(colsTable);

  return card;
}

/**
 * Build a status panel showing data fetch summary and simulation controls.
 *
 * @param {Object} status - Status object from /api/status.
 * @returns {HTMLElement} The status panel element.
 */
function buildStatusPanel(status) {
  const panel = document.createElement("div");
  panel.className = "mdn-card";

  if (!status || status.total_games === 0) {
    panel.innerHTML =
      '<p style="color:rgba(32,30,29,.6)">No data fetched yet. Click <strong>Fetch data</strong> to load game data from ESPN.</p>' +
      '<div style="margin-top:0.75rem">' +
      '<button id="btn-fetch-data-standings" class="mdn-btn mdn-btn-primary" type="button">Fetch data</button>' +
      '</div>';
    setTimeout(() => {
      const btn = document.getElementById("btn-fetch-data-standings");
      if (btn) btn.addEventListener("click", _handleFetchFromStandings);
    }, 0);
    return panel;
  }

  panel.style.cssText += ";display:grid;grid-template-columns:1.1fr 1.6fr;gap:32px";

  const gamesPerWeek = status.games_per_week || {};
  const pctCompleted = status.expected_total > 0 ? Math.round(((status.completed || 0) / status.expected_total) * 100) : 0;

  const savedCutoffLS = localStorage.getItem('sim-cutoff');
  const cutoffTitle = savedCutoffLS
    ? "Week " + savedCutoffLS + " cutoff"
    : "Auto cutoff — week " + (status.weeks_completed || status.weeks_fetched || 0);

  // --- Left column: season data ---
  let html = '<div>';
  html += '<div class="mdn-card-kicker">Season data</div>';
  html += '<div class="mdn-card-title">' + status.season_year + ' · ' + cutoffTitle + '</div>';
  html += '<div style="display:flex;gap:28px;margin-top:12px;flex-wrap:wrap">';
  html += '<div><div class="mdn-stat-lbl">Weeks loaded</div><div class="mdn-stat-val">' + status.weeks_fetched + ' / 18</div></div>';
  html += '<div><div class="mdn-stat-lbl">Weeks completed</div><div class="mdn-stat-val">' + (status.weeks_completed || 0) + ' / 18</div></div>';
  html += '<div><div class="mdn-stat-lbl">Games loaded</div><div class="mdn-stat-val">' + status.total_games + ' / ' + status.expected_total + '</div></div>';
  html += '<div><div class="mdn-stat-lbl">Games completed</div><div class="mdn-stat-val">' + (status.completed || 0) + ' / ' + status.expected_total + ' (' + pctCompleted + '%)</div></div>';
  html += '</div>';
  if (status.last_fetch_time) {
    const fetchDate = new Date(status.last_fetch_time);
    html += '<p class="mdn-hint">Last fetched ' + fetchDate.toLocaleString() +
      (status.in_progress > 0 ? ' · ' + status.in_progress + ' game(s) in progress' : '') + '</p>';
  }
  html += '</div>';

  // --- Right column: simulation controls ---
  const cpuCount = (status && status.cpu_count) ? status.cpu_count : 4;
  const savedWorkers = parseInt(localStorage.getItem('sim-workers'), 10) || cpuCount;
  const savedNoise = localStorage.getItem('sim-noise') || '20';
  const noiseVal = (parseInt(savedNoise, 10) / 100).toFixed(2);
  const noiseLabel = _noiseLabel(parseFloat(noiseVal));

  html += '<div>';
  html += '<div class="mdn-card-kicker">Simulation</div>';
  html += '<div style="display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap;margin-top:6px">';

  html += '<div class="mdn-field" style="width:110px">' +
    '<label for="sim-iterations-st">Iterations' +
    _infoIcon("Number of Monte Carlo trials to run. More iterations = more accurate probabilities but longer runtime.") +
    '</label>' +
    '<input class="mdn-input" type="number" id="sim-iterations-st" min="100" max="1000000" value="' +
    (parseInt(localStorage.getItem('sim-iterations'), 10) || 10000) + '"></div>';

  html += '<div class="mdn-field" style="width:110px">' +
    '<label for="sim-cutoff-st">Cutoff' +
    _infoIcon("Games up to and including this week use real results. Games after this week are simulated. Auto = latest completed week.") +
    '</label>' +
    '<select class="mdn-input" id="sim-cutoff-st"><option value="">Auto</option>';
  for (let w = 1; w <= 18; w++) {
    html += '<option value="' + w + '"' + (savedCutoffLS == w ? ' selected' : '') + '>Week ' + w + '</option>';
  }
  html += '</select></div>';

  html += '<div class="mdn-field" style="width:140px">' +
    '<label for="sim-noise-st">Noise' +
    _infoIcon("Per-game strength noise: adds random variance to each simulated game outcome, modeling the unpredictability of real NFL games (\"Any given Sunday\").") +
    '</label>' +
    '<input type="range" class="mdn-input" id="sim-noise-st" min="0" max="100" value="' + savedNoise + '">' +
    '<div class="mdn-hint" id="sim-noise-label-st">' + noiseVal + ' — ' + noiseLabel + '</div></div>';

  html += '<div class="mdn-field" style="width:130px">' +
    '<label for="sim-workers-st">Workers' +
    _infoIcon("Parallel CPU cores: each Monte Carlo trial is independent, so batches run simultaneously across cores. More workers = faster simulation.") +
    '</label>' +
    '<input type="range" class="mdn-input" id="sim-workers-st" min="1" max="' + cpuCount + '" value="' + savedWorkers + '">' +
    '<div class="mdn-hint" id="sim-workers-label-st">' + savedWorkers + (savedWorkers === 1 ? ' core' : ' cores') + '</div></div>';

  html += '<button id="btn-run-sim-standings" class="mdn-btn mdn-btn-primary" type="button" style="margin-top:23px">Simulate</button>';
  html += '<button id="btn-fetch-data-standings" class="mdn-btn mdn-btn-secondary" type="button" style="margin-top:23px">Fetch data</button>';
  html += '</div>';
  html += '<p class="mdn-hint" id="sim-total-st" style="margin-top:10px"></p>';
  html += '<div id="sim-progress-st" style="margin-top:0.75rem;display:none;align-items:center;gap:0.6rem">' +
    '<span class="mdn-spinner"></span><span class="mdn-hint">Running simulation…</span></div>';
  html += '</div>';

  panel.innerHTML = html;

  // Wire up event listeners after DOM insert
  setTimeout(() => {
    const iterInput = document.getElementById("sim-iterations-st");
    const cutoffSel = document.getElementById("sim-cutoff-st");
    const noiseSl = document.getElementById("sim-noise-st");
    const workersSl = document.getElementById("sim-workers-st");
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
    if (cutoffSel) cutoffSel.addEventListener("change", () => {
      localStorage.setItem('sim-cutoff', cutoffSel.value);
      // Re-render standings with the new cutoff week
      const contentEl = document.getElementById("content");
      if (contentEl) renderStandings(contentEl);
    });

    // Noise label update
    if (noiseSl) noiseSl.addEventListener("input", () => {
      const val = (parseInt(noiseSl.value, 10) / 100).toFixed(2);
      const label = _noiseLabel(parseFloat(val));
      const labelEl = document.getElementById("sim-noise-label-st");
      if (labelEl) labelEl.textContent = val + " — " + label;
      localStorage.setItem('sim-noise', noiseSl.value);
    });

    // Workers label update
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
 * Build a hoverable info icon + tooltip popover for a simulation control label.
 *
 * @param {string} text - Tooltip explanation text.
 * @returns {string} HTML string.
 */
function _infoIcon(text) {
  return ' <span class="mdn-tt-wrap"><span class="mdn-info-ic">i</span>' +
    '<span class="mdn-tt-pop">' + _escapeHtmlAttr(text) + '</span></span>';
}

/**
 * Qualitative label for a 0.0–1.0 noise value.
 *
 * @param {number} val - Noise value (0.0–1.0).
 * @returns {string}
 */
function _noiseLabel(val) {
  if (val <= 0.05) return "none";
  if (val <= 0.15) return "low";
  if (val <= 0.25) return "moderate";
  if (val <= 0.4) return "high";
  return "chaotic";
}

/**
 * Escape a string for safe insertion as HTML text content built via string
 * concatenation (used only for tooltip copy, never user-controlled data).
 *
 * @param {string} str
 * @returns {string}
 */
function _escapeHtmlAttr(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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

/**
 * Silently try to load cached CP solver results. If the server responds
 * quickly (results are cached), apply badges without showing a spinner.
 * If the server takes too long (results not cached), abort silently.
 *
 * @param {HTMLElement} contentEl - The standings container.
 * @param {number|null} cutoffWeek - Cutoff week.
 */
async function _tryLoadCachedCPBadges(contentEl, cutoffWeek) {
  try {
    let url = "/api/cp-clinch-all";
    if (cutoffWeek != null) url += "?cutoff_week=" + cutoffWeek;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2000); // 2s max

    const response = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);

    if (!response.ok) return;
    const data = await response.json();
    if (!data || !data.conferences) return;

    // Build lookup and apply badges (same logic as _fetchAndApplyCPBadges)
    const lookup = {};
    for (const conf of Object.values(data.conferences)) {
      if (!Array.isArray(conf)) continue;
      for (const entry of conf) {
        if (entry && entry.team) lookup[entry.team] = entry;
      }
    }
    _cpClinchResults = lookup;

    const nameWrappers = contentEl.querySelectorAll("[data-team-name]");
    for (const wrapper of nameWrappers) {
      const teamName = wrapper.getAttribute("data-team-name");
      const result = lookup[teamName];
      if (!result) continue;
      const badge = _createClinchBadge(result);
      if (badge) wrapper.appendChild(badge);
    }
  } catch (_) {
    // Aborted or failed — no badges, no problem
  }
}

/**
 * Fetch CP solver clinch/elimination data and apply badges to existing team rows.
 * Non-blocking: if the endpoint fails or is unavailable, standings remain unchanged.
 *
 * @param {HTMLElement} contentEl - The standings container.
 * @param {number|null} cutoffWeek - Cutoff week.
 */
async function _fetchAndApplyCPBadges(contentEl, cutoffWeek) {
  // Show a subtle loading hint while CP solver runs
  const hint = document.createElement("div");
  hint.id = "cp-solver-hint";
  hint.style.cssText = "margin-bottom:0.75rem;padding:0.6rem 1rem;background:#fff;border:1px solid var(--mdn-divider);font-size:0.85rem;color:rgba(32,30,29,.6);display:flex;align-items:center;gap:0.6rem";
  hint.innerHTML = '<span class="mdn-spinner"></span> Computing clinch/elimination…';
  contentEl.insertBefore(hint, contentEl.children[1] || null);

  const data = await API.fetchCPClinchAll(cutoffWeek);

  // Remove the hint
  hint.remove();
  if (!data || !data.conferences) {
    _cpClinchResults = null;
    return;
  }

  // Build a flat lookup map: team name → result object
  const lookup = {};
  for (const conf of Object.values(data.conferences)) {
    if (!Array.isArray(conf)) continue;
    for (const entry of conf) {
      if (entry && entry.team) {
        lookup[entry.team] = entry;
      }
    }
  }
  _cpClinchResults = lookup;

  // Apply badges to all rendered team rows
  const nameWrappers = contentEl.querySelectorAll("[data-team-name]");
  for (const wrapper of nameWrappers) {
    const teamName = wrapper.getAttribute("data-team-name");
    const result = lookup[teamName];
    if (!result) continue;

    const badge = _createClinchBadge(result);
    if (badge) {
      wrapper.appendChild(badge);
    }
  }
}

/**
 * Create a clinch/elimination status tag (with hover tooltip) for a CP
 * solver result. Tag label/style follows the legend: #1 SEED, DIVISION,
 * CLINCHED, ELIMINATED, PENDING.
 *
 * @param {Object} result - CP solver result for a team.
 * @returns {HTMLElement|null} Tag+tooltip wrapper element, or null if status is "alive".
 */
function _createClinchBadge(result) {
  const status = result.status;
  if (status === "alive") return null;

  const tag = document.createElement("span");
  tag.style.marginLeft = "6px";

  let statusText;
  if (status === "clinched" && result.clinched_homefield) {
    tag.className = "mdn-tag mdn-tag-accent";
    tag.textContent = "#1 SEED";
    statusText = "Clinched #1 seed (homefield advantage)";
  } else if (status === "clinched" && result.clinched_division) {
    tag.className = "mdn-tag mdn-tag-accent-division";
    tag.textContent = "DIVISION";
    statusText = "Clinched division title";
  } else if (status === "clinched") {
    tag.className = "mdn-tag mdn-tag-win-o";
    tag.style.cursor = "default";
    tag.textContent = "CLINCHED";
    statusText = "Clinched a playoff spot";
  } else if (status === "eliminated") {
    tag.className = "mdn-tag mdn-tag-elim";
    tag.textContent = "ELIMINATED";
    statusText = "Eliminated from playoff contention";
  } else if (status === "inconclusive") {
    tag.className = "mdn-tag mdn-tag-outline-dashed";
    tag.textContent = "PENDING";
    statusText = "Inconclusive — solver timed out before reaching a proof";
  } else {
    return null;
  }

  const wrap = document.createElement("span");
  wrap.className = "mdn-tt-wrap";
  wrap.setAttribute("data-cp-clinch-badge", status);
  wrap.setAttribute("data-team", result.team);
  wrap.appendChild(tag);

  const pop = document.createElement("span");
  pop.className = "mdn-tt-pop";
  pop.textContent = result.team + " — " + statusText + _buildPopoverText(result);
  wrap.appendChild(pop);

  return wrap;
}

/**
 * Build the plain-text tooltip body with solver details (one line per fact,
 * matching the tooltip's `white-space: pre-line` styling).
 *
 * @param {Object} result - CP solver result for a team.
 * @returns {string} Text starting with a newline, or "" if no detail available.
 */
function _buildPopoverText(result) {
  const lines = [];
  lines.push("Solve time: " + (result.solve_time_ms || 0) + " ms");
  if (result.num_variables > 0) {
    lines.push("Remaining games: " + result.num_variables);
  }
  if (result.record_groups_total > 0) {
    lines.push("Scenarios checked: " + (result.record_groups_completed || 0) + " of " + result.record_groups_total);
  }
  if (result.minimum_seed != null) {
    lines.push("Best seed: #" + result.minimum_seed);
  }
  if (result.magic_number != null) {
    lines.push("Magic number: " + result.magic_number + " wins to clinch");
  }
  if (result.error) {
    lines.push(result.error);
  }
  return lines.length ? "\n" + lines.join("\n") : "";
}
