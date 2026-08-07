/**
 * Simulation controls and results rendering for the NFL Monte Carlo Playoff Simulator.
 *
 * Provides two global functions:
 *   - renderSimulation(contentEl) — renders the simulation controls view (#simulate)
 *   - renderResults(contentEl) — renders the simulation results view (#results)
 *
 * Requirements: 5.5, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.10,
 *               11.1, 11.2, 11.7, 11.11, 11.12, 11.13, 11.14
 */

"use strict";

/** Module-level storage for the latest simulation results. */
window._simulationResults = null;

/**
 * Render the simulation controls view.
 *
 * @param {HTMLElement} contentEl - The main content container element.
 */
async function renderSimulation(contentEl) {
  // Determine the default cutoff week from status
  let defaultCutoff = 18;
  let status = null;
  try {
    status = await API.fetchStatus();
    if (status && status.games_cached > 0) {
      defaultCutoff = 18;
    }
  } catch (_) {
    // Ignore — we'll just use 18 as default
  }

  contentEl.innerHTML = `
    <div class="card card-body mb-3">
      <h2>Simulation Controls</h2>
      <div class="row g-3 align-items-end">
        <div class="col-auto">
          <label for="sim-iterations">Iterations</label>
          <input type="number" id="sim-iterations" class="form-control" min="100" max="1000000" value="10000"
                 aria-describedby="iterations-help">
          <span id="iterations-help" class="cutoff-label">100 to 1,000,000 trials</span>
        </div>
        <div class="col-auto">
          <label for="sim-cutoff-week">Cutoff Week</label>
          <select id="sim-cutoff-week" class="form-select" aria-describedby="cutoff-help">
            <option value="">Auto (latest completed)</option>
            ${Array.from({ length: 18 }, (_, i) => i + 1)
              .map((w) => `<option value="${w}">Week ${w}</option>`)
              .join("")}
          </select>
          <span id="cutoff-help" class="cutoff-label" aria-live="polite">
            Games after the cutoff week will be simulated
          </span>
        </div>
        <div class="col-auto">
          <label for="sim-noise">Game Noise</label>
          <input type="range" id="sim-noise" class="form-range" min="0" max="100" value="20"
                 aria-describedby="noise-help" style="min-width:160px">
          <span id="noise-help" class="cutoff-label">0.20 — moderate variance</span>
        </div>
        <div class="col-auto">
          <label for="sim-workers" title="Parallel CPU cores: each Monte Carlo trial is independent, so batches run simultaneously across cores. More workers = faster simulation (near-linear speedup). Uses Python multiprocessing to bypass the GIL.">Workers &#9432;</label>
          <input type="range" id="sim-workers" class="form-range" min="1" max="${status && status.cpu_count ? status.cpu_count : 4}" value="${localStorage.getItem('sim-workers') || (status && status.cpu_count ? status.cpu_count : 4)}"
                 aria-describedby="workers-help" style="min-width:160px"
                 title="1 = single-process (no overhead), max = all available CPU cores running trial batches in parallel">
          <span id="workers-help" class="cutoff-label">${localStorage.getItem('sim-workers') || (status && status.cpu_count ? status.cpu_count : 4)} cores</span>
        </div>
      </div>
      <div class="row g-3 align-items-end mt-2">
        <div class="col-auto">
          <button id="btn-run-simulation" class="btn btn-primary" type="button">
            Run Simulation
          </button>
        </div>
        <div class="col-auto">
          <button id="btn-fetch-data" class="btn btn-secondary" type="button">
            Fetch Data
          </button>
        </div>
      </div>
      <p id="sim-total-games" class="cutoff-label" style="margin-top:1rem;font-size:0.9rem" aria-live="polite"></p>
    </div>
    <div id="sim-progress-overlay" class="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center d-none" style="background:rgba(0,0,0,0.5);z-index:1055">
      <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">Running simulation…</span>
      </div>
    </div>
  `;

  // Wire up cutoff week label updates
  const cutoffSelect = document.getElementById("sim-cutoff-week");
  const cutoffHelp = document.getElementById("cutoff-help");

  cutoffSelect.addEventListener("change", () => {
    const val = cutoffSelect.value;
    if (val) {
      cutoffHelp.textContent = `Games after week ${val} will be simulated`;
    } else {
      cutoffHelp.textContent = "Games after the cutoff week will be simulated";
    }
  });

  // Wire up noise slider
  const noiseSlider = document.getElementById("sim-noise");
  const noiseHelp = document.getElementById("noise-help");
  noiseSlider.addEventListener("input", () => {
    const val = (parseInt(noiseSlider.value, 10) / 100).toFixed(2);
    const label = parseFloat(val) <= 0.05 ? "no noise (pure strength)" : parseFloat(val) <= 0.15 ? "low variance" : parseFloat(val) <= 0.25 ? "moderate variance" : parseFloat(val) <= 0.4 ? "high variance" : "very chaotic";
    noiseHelp.textContent = val + " — " + label;
  });

  // Wire up workers slider
  const workersSlider = document.getElementById("sim-workers");
  const workersHelp = document.getElementById("workers-help");
  workersSlider.addEventListener("input", () => {
    const val = parseInt(workersSlider.value, 10);
    workersHelp.textContent = val === 1 ? "1 core (no parallelism)" : val + " cores";
    localStorage.setItem('sim-workers', val);
  });

  // Live-updating total game simulations display
  const totalGamesEl = document.getElementById("sim-total-games");
  const iterationsInput = document.getElementById("sim-iterations");
  const gamesPerWeek = (status && status.games_per_week) ? status.games_per_week : {};
  const totalGamesInSeason = Object.values(gamesPerWeek).reduce((a, b) => a + b, 0);

  function updateTotalGames() {
    const iterations = parseInt(iterationsInput.value, 10) || 10000;
    const cutoffVal = cutoffSelect.value;
    const cutoff = cutoffVal ? parseInt(cutoffVal, 10) : 18;

    // Count games after cutoff week
    let gamesToSimulate = 0;
    for (const [week, count] of Object.entries(gamesPerWeek)) {
      if (parseInt(week, 10) > cutoff) {
        gamesToSimulate += count;
      }
    }

    const totalSimulations = iterations * gamesToSimulate;
    if (gamesToSimulate > 0) {
      totalGamesEl.textContent = `${gamesToSimulate} games × ${iterations.toLocaleString()} iterations = ${totalSimulations.toLocaleString()} total game simulations`;
    } else {
      totalGamesEl.textContent = "No games to simulate (cutoff is at or beyond last week with data)";
    }
  }

  iterationsInput.addEventListener("input", updateTotalGames);
  cutoffSelect.addEventListener("change", updateTotalGames);
  updateTotalGames(); // Initial calculation

  // Wire up Run Simulation button
  const runBtn = document.getElementById("btn-run-simulation");
  runBtn.addEventListener("click", _handleRunSimulation);

  // Wire up Fetch Data button
  const fetchBtn = document.getElementById("btn-fetch-data");
  fetchBtn.addEventListener("click", _handleFetchData);
}

/**
 * Handle the "Run Simulation" button click.
 * Validates inputs, calls the API, stores results, and navigates to #results.
 */
async function _handleRunSimulation() {
  const iterationsInput = document.getElementById("sim-iterations");
  const cutoffSelect = document.getElementById("sim-cutoff-week");
  const overlayEl = document.getElementById("sim-progress-overlay");
  const runBtn = document.getElementById("btn-run-simulation");

  // Validate iterations
  const iterations = parseInt(iterationsInput.value, 10);
  if (isNaN(iterations) || iterations < 100 || iterations > 1000000) {
    App.showError("Iterations must be a number between 100 and 1,000,000.");
    return;
  }

  // Parse cutoff week (null means auto-detect)
  const cutoffValue = cutoffSelect.value;
  const cutoffWeek = cutoffValue ? parseInt(cutoffValue, 10) : null;

  // Parse noise value
  const noiseSlider = document.getElementById("sim-noise");
  const noise = parseInt(noiseSlider.value, 10) / 100;

  // Parse num_workers from slider
  const workersInput = document.getElementById("sim-workers");
  const numWorkers = parseInt(workersInput.value, 10);

  // Show progress overlay
  overlayEl.classList.remove("d-none");
  runBtn.disabled = true;

  try {
    const results = await API.runSimulation(iterations, cutoffWeek, noise, numWorkers);
    window._simulationResults = results;
    App.showInfo("Simulation complete.");
    App.navigate("results");
  } catch (err) {
    App.showError(err.message || "Simulation failed.");
  } finally {
    overlayEl.classList.add("d-none");
    runBtn.disabled = false;
  }
}

/**
 * Handle the "Fetch Data" button click.
 * Triggers ESPN data fetch via the API.
 */
async function _handleFetchData() {
  const fetchBtn = document.getElementById("btn-fetch-data");
  fetchBtn.disabled = true;

  App.showLoading();
  try {
    const result = await API.fetchData();
    const msg = `Data fetched: ${result.games_fetched} games loaded.`;
    App.showInfo(msg);
  } catch (err) {
    App.showError(err.message || "Failed to fetch data.");
  } finally {
    App.hideLoading();
    fetchBtn.disabled = false;
  }
}

/**
 * Handle the "Export" button click.
 * Writes timing data to doc/solver-performance.md in the project directory.
 */
async function _handleExportPerformance() {
  const btn = document.getElementById("btn-export-performance");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Exporting…";
  try {
    const response = await fetch("/api/export-solver-performance");
    const data = await response.json();
    if (!response.ok) {
      btn.textContent = "Failed";
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
      return;
    }
    if (data.status === "no_data") {
      btn.textContent = "No data";
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    } else if (data.entries_added === 0) {
      btn.textContent = "Already up to date";
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    } else {
      btn.textContent = "+" + data.entries_added + " entries";
      setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
    }
  } catch (err) {
    btn.textContent = "Error";
    setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 2000);
  }
}

/**
 * Handle the "Timing History" button click.
 * Opens a modal showing solver timing history from the API.
 */
async function _handleTimingHistory() {
  // Create the modal element if it doesn't exist yet
  let modalEl = document.getElementById("timingHistoryModal");
  if (!modalEl) {
    modalEl = document.createElement("div");
    modalEl.className = "modal fade";
    modalEl.id = "timingHistoryModal";
    modalEl.tabIndex = -1;
    modalEl.setAttribute("aria-labelledby", "timingHistoryModalLabel");
    modalEl.setAttribute("aria-hidden", "true");
    modalEl.innerHTML = `
      <div class="modal-dialog modal-lg">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title" id="timingHistoryModalLabel">Solver Timing History</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body" id="timingHistoryBody">
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modalEl);
  }

  const bodyEl = document.getElementById("timingHistoryBody");
  bodyEl.innerHTML = '<div class="text-center"><div class="spinner-border spinner-border-sm" role="status"><span class="visually-hidden">Loading…</span></div></div>';

  // Show modal immediately with loading state
  const modal = new bootstrap.Modal(modalEl);
  modal.show();

  try {
    const data = await API.solverTimings();
    if (!data.timings || data.timings.length === 0) {
      bodyEl.innerHTML = '<div class="alert alert-info">No timing data collected yet. Run the clinching solver to start building calibration data.</div>';
    } else {
      let rows = "";
      for (const t of data.timings) {
        const recordedAt = t.recorded_at ? new Date(t.recorded_at).toLocaleString() : "—";
        rows += `<tr>
          <td style="text-align:right">${t.ms_per_eval.toFixed(2)}</td>
          <td>${_escapeHtml(t.method)}</td>
          <td style="text-align:right">${t.relevant_games_count}</td>
          <td style="text-align:right">${t.total_evals.toLocaleString()}</td>
          <td>${recordedAt}</td>
        </tr>`;
      }
      bodyEl.innerHTML = `
        <p class="text-muted">These measurements are collected after each solver run and used to calibrate time estimates. The system keeps the last 50 measurements.</p>
        <p><strong>${data.count} measurements</strong>, avg ${data.avg_ms_per_eval.toFixed(2)} ms/eval</p>
        <div style="max-height: 300px; overflow-y: auto;">
          <table class="table table-sm table-striped">
            <thead><tr><th>ms/eval</th><th>Method</th><th>Games</th><th>Evaluations</th><th>Recorded At</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      `;
    }
  } catch (err) {
    bodyEl.innerHTML = `<div class="alert alert-danger">Failed to load timing data: ${_escapeHtml(err.message || "Unknown error")}</div>`;
  }
}

/**
 * Render the simulation results view.
 *
 * @param {HTMLElement} contentEl - The main content container element.
 */
async function renderResults(contentEl) {
  if (!window._simulationResults) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p>No simulation results available.</p>
        <p>Go to <a href="#simulate">Simulate</a> to run a simulation first.</p>
      </div>
    `;
    return;
  }

  const results = window._simulationResults;

  // Build the results page — Modernist "Ledger" redesign (see
  // design_handoff_standings_redesign/, Simulation Results Option 3a).
  let html = `<div class="mdn-page">`;

  // Metadata header
  const showWarning = results.low_confidence || !results.convergence_achieved;
  html += `<div class="mdn-card">
    <div class="mdn-card-kicker">Simulation results</div>
    <div class="mdn-card-title">Simulation Results</div>
    <div style="display:flex;gap:28px;margin-top:12px;flex-wrap:wrap">
      <div><div class="mdn-stat-lbl">Iterations</div><div class="mdn-stat-val">${results.iterations_run.toLocaleString()}</div></div>
      <div><div class="mdn-stat-lbl">Cutoff week</div><div class="mdn-stat-val">${_escapeHtml(String(results.cutoff_week_used))}</div></div>
      <div><div class="mdn-stat-lbl">Fixed games</div><div class="mdn-stat-val">${results.fixed_games != null ? results.fixed_games : "?"}</div></div>
      <div><div class="mdn-stat-lbl">Simulated games</div><div class="mdn-stat-val">${results.simulated_games != null ? results.simulated_games : "?"}</div></div>
    </div>
    ${showWarning ? `<p class="mdn-hint" style="color:var(--mdn-accent-700);margin-top:10px">${results.low_confidence ? "Low confidence." : ""}${results.convergence_achieved ? "" : " Convergence not achieved."}</p>` : ""}
  </div>`;

  // Playoff probability summary tables by conference
  html += _renderPlayoffProbabilityTables(results.team_results);

  // Seeding probability matrix + Top scenarios
  html += _renderSeedingMatrix(results.team_results);
  html += _renderTopScenarios(results.top_scenarios);

  html += `</div>`;

  // Team detail panel (hidden initially, shown on team click)
  html += `<div id="team-detail-panel" class="mdn-page" style="margin-top:2.5rem" hidden></div>`;

  contentEl.innerHTML = html;

  // Attach click handlers for team names
  contentEl.querySelectorAll("[data-team-click]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const teamName = el.getAttribute("data-team-click");
      _showTeamDetail(teamName, results);
    });
  });
}

/**
 * Render playoff probability summary tables grouped by conference.
 * Sorted descending by probability; alphabetical for ties.
 *
 * @param {Array} teamResults - Array of team result objects.
 * @returns {string} HTML string.
 */
function _renderPlayoffProbabilityTables(teamResults) {
  const conferences = _groupByConference(teamResults);
  let html = "";

  for (const conf of ["AFC", "NFC"]) {
    const teams = conferences[conf] || [];
    // Sort descending by playoff_probability, alphabetical for ties
    teams.sort((a, b) => {
      if (b.playoff_probability !== a.playoff_probability) {
        return b.playoff_probability - a.playoff_probability;
      }
      return a.team.localeCompare(b.team);
    });

    html += `<div class="mdn-conf-head">
      <img src="img/logos/${conf.toLowerCase()}.png" alt="${conf}" width="26" height="26">
      <h2>${conf} Playoff Probabilities</h2>
    </div>
    <table class="mdn-led-table" style="margin-bottom:32px" aria-label="${conf} playoff probabilities">
      <thead>
        <tr>
          <th style="width:36px" class="mdn-num">#</th>
          <th>Team</th>
          <th class="mdn-num">Record</th>
          <th>Division</th>
          <th style="width:220px">Playoff %</th>
          <th class="mdn-num">Strength</th>
        </tr>
      </thead>
      <tbody>`;

    for (let idx = 0; idx < teams.length; idx++) {
      const team = teams[idx];
      const logoId = TEAM_LOGO_IDS[team.team] || "";
      const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="" width="20" height="20">` : "";
      const pctNum = team.playoff_probability;
      const barColor = pctNum >= 99.95 ? "var(--mdn-accent-500)" : pctNum <= 0.05 ? "var(--mdn-neutral-400)" : "var(--mdn-accent-300)";
      const labelOpacity = pctNum <= 0.05 ? "0.5" : "1";
      // The 7th seed is the current projected playoff cutoff line.
      const rowClass = idx === 6 ? ' class="mdn-leader"' : "";
      html += `<tr${rowClass}>
        <td class="mdn-num" style="opacity:0.6">${idx + 1}</td>
        <td class="mdn-tm">
          <div class="mdn-team-cell">
            ${logoHtml}<a href="#" data-team-click="${_escapeHtml(team.team)}" class="mdn-team-link">${_escapeHtml(team.team)}</a>
          </div>
        </td>
        <td class="mdn-num">${_escapeHtml(team.record || "0-0-0")}</td>
        <td>${_escapeHtml(team.division)}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <div style="flex:1;height:6px;background:var(--mdn-neutral-200);position:relative">
              <div style="position:absolute;inset:0 auto 0 0;width:${pctNum}%;background:${barColor}"></div>
            </div>
            <span style="font-size:12px;width:44px;text-align:right;flex:none;opacity:${labelOpacity}">${pctNum.toFixed(1)}%</span>
          </div>
        </td>
        <td class="mdn-num">${team.strength_rating.toFixed(3)}</td>
      </tr>`;
    }

    html += `</tbody></table>`;
  }

  return html;
}

/**
 * Compute the warm brown→red tint (and whether it's dark enough to need
 * white text) for a seeding probability cell, per the Modernist design
 * handoff: transparent at 0%, pale tan → amber → orange → red → deep maroon
 * proportional to value, never gray, never tinted when the value is exactly
 * 0.0%.
 *
 * @param {number} v - Probability as a percentage (0-100).
 * @returns {{tint: string, hi: boolean}}
 */
function _seedTint(v) {
  if (v <= 0) return { tint: "transparent", hi: false };
  if (v < 15) return { tint: "oklch(91% 0.045 55)", hi: false };
  if (v < 30) return { tint: "oklch(82% 0.09 48)", hi: false };
  if (v < 45) return { tint: "oklch(71% 0.14 40)", hi: false };
  if (v < 60) return { tint: "oklch(60% 0.18 32)", hi: true };
  if (v < 80) return { tint: "oklch(48% 0.16 26)", hi: true };
  return { tint: "oklch(34% 0.10 30)", hi: true };
}

/**
 * Render seeding probability matrix (teams × seeds 1-7) grouped by conference.
 * Modernist "Ledger" redesign — see design_handoff_standings_redesign/
 * (Simulation Results Option 3a).
 *
 * @param {Array} teamResults - Array of team result objects.
 * @returns {string} HTML string.
 */
function _renderSeedingMatrix(teamResults) {
  const conferences = _groupByConference(teamResults);
  let html = "";

  for (const conf of ["AFC", "NFC"]) {
    const teams = conferences[conf] || [];
    // Sort descending by playoff_probability, alphabetical for ties
    teams.sort((a, b) => {
      if (b.playoff_probability !== a.playoff_probability) {
        return b.playoff_probability - a.playoff_probability;
      }
      return a.team.localeCompare(b.team);
    });

    html += `<div class="mdn-conf-head">
      <img src="img/logos/${conf.toLowerCase()}.png" alt="${conf}" width="26" height="26">
      <h2>${conf} Seeding Probabilities</h2>
    </div>
    <table class="mdn-led-table" style="margin-bottom:32px" aria-label="${conf} seeding probability matrix">
      <thead>
        <tr>
          <th>Team</th>
          ${Array.from({ length: 7 }, (_, i) => `<th class="mdn-num">Seed ${i + 1}</th>`).join("")}
        </tr>
      </thead>
      <tbody>`;

    for (const team of teams) {
      const seeds = team.seed_probabilities || {};
      const logoId = TEAM_LOGO_IDS[team.team] || "";
      const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="" width="20" height="20">` : "";
      html += `<tr>
        <td class="mdn-tm">
          <div class="mdn-team-cell">
            ${logoHtml}<a href="#" data-team-click="${_escapeHtml(team.team)}" class="mdn-team-link">${_escapeHtml(team.team)}</a>
          </div>
        </td>`;
      for (let s = 1; s <= 7; s++) {
        const prob = seeds[String(s)] || 0;
        const { tint, hi } = _seedTint(prob);
        html += `<td class="mdn-num${hi ? " mdn-seed-hi" : ""}" style="background:${tint};font-weight:700">${prob.toFixed(1)}%</td>`;
      }
      html += `</tr>`;
    }

    html += `</tbody></table>`;
  }

  return html;
}

/**
 * Render the top 50 most likely distinct playoff bracket scenarios.
 * Modernist "Ledger" redesign — collapsed-by-default disclosure card with a
 * triangle marker, expanding into a ledger table — see
 * design_handoff_standings_redesign/ (Simulation Results Option 3a).
 *
 * @param {Array} topScenarios - Array of scenario objects.
 * @returns {string} HTML string.
 */
function _renderTopScenarios(topScenarios) {
  if (!topScenarios || topScenarios.length === 0) {
    return `<div class="mdn-card" style="margin:8px 0 28px">
      <div class="mdn-card-kicker">Top scenarios</div>
      <div class="mdn-card-title" style="font-size:16px">Top Playoff Scenarios</div>
      <p style="opacity:0.6;margin:8px 0 0">No scenarios available.</p>
    </div>`;
  }

  const scenarios = topScenarios;

  let html = `<details class="mdn-card mdn-scenario-card" style="margin:8px 0 28px">
    <summary>
      <span class="mdn-scenario-triangle">&#9656;</span>
      <span class="mdn-card-title" style="font-size:16px;margin:0">Top ${scenarios.length} Most Likely Playoff Scenarios</span>
    </summary>
    <table class="mdn-led-table" style="margin-top:16px">
      <thead>
        <tr>
          <th style="width:48px" class="mdn-num">#</th>
          <th>AFC Seeds (1&ndash;7)</th>
          <th>NFC Seeds (1&ndash;7)</th>
          <th class="mdn-num">Probability</th>
        </tr>
      </thead>
      <tbody>`;

  for (let i = 0; i < scenarios.length; i++) {
    const scenario = scenarios[i];
    html += `<tr>
      <td class="mdn-num" style="opacity:0.6">${i + 1}</td>
      <td>${scenario.afc_seeds.map(_escapeHtml).join(", ")}</td>
      <td>${scenario.nfc_seeds.map(_escapeHtml).join(", ")}</td>
      <td class="mdn-num" style="font-weight:700">${scenario.probability.toFixed(2)}%</td>
    </tr>`;
  }

  html += `</tbody></table></details>`;
  return html;
}

/**
 * Show team detail panel with scenario details and top 5 impact games.
 *
 * @param {string} teamName - The team name clicked.
 * @param {Object} results - The full simulation results.
 */
function _showTeamDetail(teamName, results) {
  const panel = document.getElementById("team-detail-panel");
  if (!panel) return;

  // Find the team in results
  const teamData = results.team_results.find((t) => t.team === teamName);
  if (!teamData) {
    panel.hidden = true;
    return;
  }

  const logoId = TEAM_LOGO_IDS[teamName] || "";
  let html = `<div class="mdn-conf-head" style="margin-top:8px">
    ${logoId ? `<img src="img/logos/${logoId}.png" alt="" width="32" height="32">` : ""}
    <h2>${_escapeHtml(teamName)} — Details</h2>
  </div>`;

  // Team summary
  html += `<div class="mdn-card">
    <div style="display:flex;gap:28px;flex-wrap:wrap">
      <div><div class="mdn-stat-lbl">Conference</div><div class="mdn-stat-val">${_escapeHtml(teamData.conference)}</div></div>
      <div><div class="mdn-stat-lbl">Division</div><div class="mdn-stat-val">${_escapeHtml(teamData.division)}</div></div>
      <div><div class="mdn-stat-lbl">Playoff probability</div><div class="mdn-stat-val">${teamData.playoff_probability.toFixed(1)}%</div></div>
      <div><div class="mdn-stat-lbl">Strength rating</div><div class="mdn-stat-val">${teamData.strength_rating.toFixed(3)}</div></div>
    </div>
  </div>`;

  // Seed distribution
  html += `<div style="margin-bottom:20px">
    <div class="mdn-div-lbl">Seed Distribution</div>
    <table class="mdn-led-table" aria-label="Seed distribution for ${_escapeHtml(teamName)}">
      <thead><tr>`;
  for (let s = 1; s <= 7; s++) {
    html += `<th class="mdn-num">Seed ${s}</th>`;
  }
  html += `</tr></thead><tbody><tr>`;
  const seeds = teamData.seed_probabilities || {};
  for (let s = 1; s <= 7; s++) {
    const prob = seeds[String(s)] || 0;
    const { tint, hi } = _seedTint(prob);
    html += `<td class="mdn-num${hi ? " mdn-seed-hi" : ""}" style="background:${tint};font-weight:700">${prob.toFixed(1)}%</td>`;
  }
  html += `</tr></tbody></table></div>`;

  // Impact games (if available in team data)
  if (teamData.impact_games && teamData.impact_games.length > 0) {
    html += `<div style="margin-bottom:20px">
      <div class="mdn-div-lbl">Top 5 Impact Games</div>
      <table class="mdn-led-table" aria-label="Impact games for ${_escapeHtml(teamName)}">
        <thead><tr>
          <th>Week</th><th>Matchup</th><th class="mdn-num">Impact</th>
        </tr></thead><tbody>`;

    const impactGames = teamData.impact_games.slice(0, 5);
    for (const game of impactGames) {
      html += `<tr>
        <td>${game.week || "—"}</td>
        <td>${_escapeHtml(game.home_team || "")} vs ${_escapeHtml(game.away_team || "")}</td>
        <td class="mdn-num">${game.impact != null ? game.impact.toFixed(1) + "%" : "—"}</td>
      </tr>`;
    }

    html += `</tbody></table></div>`;
  }

  // Clinching scenarios - on-demand button (only for teams between 0% and 100%)
  if (teamData.playoff_probability > 0 && teamData.playoff_probability < 100) {
    html += `<div class="mdn-card" id="clinch-section-${_escapeHtml(teamName)}">
      <div class="mdn-card-kicker">Clinching scenarios</div>
      <div class="mdn-card-title" style="font-size:16px">Clinching Scenarios</div>
      <p style="font-size:12.5px;opacity:0.65;margin:8px 0 4px">
        Find all game-outcome combinations that guarantee ${_escapeHtml(teamName)} a playoff spot.
      </p>
      <p id="clinch-estimate-text" style="font-size:12.5px;opacity:0.65;margin-bottom:10px"></p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center">
        <button id="btn-clinching" class="mdn-btn mdn-btn-primary" type="button" data-team="${_escapeHtml(teamName)}">
          Clinching Scenarios
        </button>
        <button id="btn-timing-history" class="mdn-btn mdn-btn-secondary" type="button">
          Timing History
        </button>
        <button id="btn-export-performance" class="mdn-btn mdn-btn-secondary" type="button" title="Export solver performance as markdown">
          Export Performance Data
        </button>
      </div>
      <div style="margin-top:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <label for="clinch-enum-threshold" style="font:800 10px var(--mdn-font-heading);letter-spacing:.04em;text-transform:uppercase;opacity:.65;white-space:nowrap">Enumerate up to</label>
        <input class="mdn-input" type="range" id="clinch-enum-threshold" min="5" max="14" value="9" style="width:100px">
        <span id="clinch-enum-label" style="font-size:12px;font-weight:700">9 games</span>
        <label for="clinch-samples" style="font:800 10px var(--mdn-font-heading);letter-spacing:.04em;text-transform:uppercase;opacity:.65;white-space:nowrap;margin-left:10px">Sampling iterations</label>
        <input class="mdn-input" type="number" id="clinch-samples" min="100" max="100000" value="10000" style="width:100px">
        <span id="clinch-enum-info" style="font-size:11.5px;opacity:.65"></span>
      </div>
      <p id="clinch-mode-explanation" style="font-size:11px;opacity:.6;margin-top:8px;margin-bottom:0;line-height:1.6">
        <strong>Enumeration</strong>: checks every possible outcome combination (exhaustive, proven results).<br>
        <strong>Sampling</strong>: tests strength-weighted random outcomes (faster, but may miss rare scenarios).<br>
        <strong>Export Performance Data</strong>: writes solver timing measurements to <code>doc/solver-performance.md</code> for cross-platform comparison. One row per method, using the median of the last 50 runs.<br>
        Time estimates are rough approximations (work in progress) — actual runtime depends on the number of qualifying scenarios found and the underlying hardware.
      </p>
      <div id="clinch-progress" style="display:none;margin-top:14px;align-items:center;gap:10px">
        <span class="mdn-spinner"></span>
        <span id="clinch-status-text" style="font-size:12.5px;opacity:.65">Computing clinching scenarios…</span>
        <button id="btn-clinch-cancel" class="mdn-btn mdn-btn-secondary" style="padding:4px 10px;font-size:10px" type="button">Cancel</button>
      </div>
      <div id="clinch-results"></div>
    </div>`;
  }

  panel.innerHTML = html;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });

  // Wire up Timing History button
  const timingBtn = document.getElementById("btn-timing-history");
  if (timingBtn) {
    timingBtn.addEventListener("click", _handleTimingHistory);
  }

  // Wire up Export button (downloads solver-performance.md)
  const exportBtn = document.getElementById("btn-export-performance");
  if (exportBtn) {
    exportBtn.addEventListener("click", _handleExportPerformance);
  }

  // Wire up clinching scenarios button
  const clinchBtn = document.getElementById("btn-clinching");
  if (clinchBtn) {
    // Use the simulation's cutoff week so the solver matches the sim context
    const cutoffWeek = results.cutoff_week_used || null;

    // Slider logic
    const enumSlider = document.getElementById("clinch-enum-threshold");
    const enumLabel = document.getElementById("clinch-enum-label");
    const enumInfo = document.getElementById("clinch-enum-info");
    let relevantGames = 0;
    let teamRecordCombos = 1;
    let msPerEval = 2.0;
    let serverCpuCount = parseInt(localStorage.getItem("sim-workers"), 10) || 4;

    function updateEnumLabel() {
      const val = parseInt(enumSlider.value, 10);
      enumLabel.textContent = val + " games";
      if (relevantGames > 0) {
        if (relevantGames <= val) {
          const combos = Math.pow(3, relevantGames) * teamRecordCombos;
          const estLow = Math.max(1, Math.round((combos * msPerEval * 8 / 1000) / serverCpuCount));
          const estHigh = Math.max(estLow + 1, Math.round((combos * msPerEval * 15 / 1000) / serverCpuCount));
          enumInfo.textContent = "→ enumeration · " + combos.toLocaleString() + " evaluations · " + _formatTime(estLow) + " – " + _formatTime(estHigh);
        } else {
          const samplingIters = samplesInput ? parseInt(samplesInput.value, 10) || 10000 : 10000;
          const samplingEvals = samplingIters * teamRecordCombos;
          const estLow = Math.max(1, Math.round((samplingEvals * msPerEval * 8 / 1000) / serverCpuCount));
          const estHigh = Math.max(estLow + 1, Math.round((samplingEvals * msPerEval * 15 / 1000) / serverCpuCount));
          enumInfo.textContent = "→ sampling · " + samplingIters.toLocaleString() + " trials × " + teamRecordCombos + " records · " + _formatTime(estLow) + " – " + _formatTime(estHigh);
        }
      }
    }
    function _formatTime(sec) {
      if (sec < 60) return sec + "s";
      return Math.floor(sec / 60) + "m " + (sec % 60) + "s";
    }
    const samplesInput = document.getElementById("clinch-samples");
    // Restore from localStorage
    const savedThreshold = localStorage.getItem("clinch-enum-threshold");
    const savedSamples = localStorage.getItem("clinch-samples");
    if (savedThreshold && enumSlider) enumSlider.value = savedThreshold;
    if (savedSamples && samplesInput) samplesInput.value = savedSamples;
    if (enumSlider) {
      enumSlider.addEventListener("input", () => {
        localStorage.setItem("clinch-enum-threshold", enumSlider.value);
        updateEnumLabel();
      });
    }
    if (samplesInput) {
      samplesInput.addEventListener("input", () => {
        localStorage.setItem("clinch-samples", samplesInput.value);
        updateEnumLabel();
      });
    }

    // Fetch estimate on render
    API.clinchEstimate(teamName, cutoffWeek).then(est => {
      const estEl = document.getElementById("clinch-estimate-text");
      if (!estEl) return;
      if (!est.available) {
        clinchBtn.disabled = true;
        clinchBtn.title = est.reason || "Not available";
        estEl.textContent = est.reason || "Not available before week 14";
      } else {
        relevantGames = est.relevant_games;
        teamRecordCombos = est.team_record_combos || 1;
        msPerEval = est.ms_per_eval || 2.0;
        serverCpuCount = est.cpu_count || 4;
        estEl.textContent = est.relevant_games + " relevant games · " + teamRecordCombos + " team record combinations";
        updateEnumLabel();
      }
    }).catch(() => {});

    clinchBtn.addEventListener("click", async () => {
      const progress = document.getElementById("clinch-progress");
      const statusText = document.getElementById("clinch-status-text");
      const resultsDiv = document.getElementById("clinch-results");
      const cancelBtn = document.getElementById("btn-clinch-cancel");
      clinchBtn.disabled = true;
      progress.style.display = "flex";
      resultsDiv.innerHTML = "";

      // AbortController for cancellation
      const abortController = new AbortController();
      cancelBtn.addEventListener("click", () => abortController.abort(), { once: true });

      // Cycle through status messages with elapsed time
      const messages = [
        "Identifying playoff contenders…",
        "Evaluating team record combinations…",
        "Sampling game outcomes (strength-weighted)…",
        "Testing qualifying universes…",
        "Checking minimality of conditions…",
        "Deduplicating scenarios…",
        "Still working — reducing condition sets…",
      ];
      let msgIdx = 0;
      const startTime = Date.now();
      function updateStatus() {
        const elapsed = Math.round((Date.now() - startTime) / 1000);
        statusText.textContent = messages[msgIdx] + " (" + elapsed + "s)";
      }
      updateStatus();
      const msgInterval = setInterval(() => {
        if (msgIdx < messages.length - 1) msgIdx++;
        updateStatus();
      }, 8000);
      const timerInterval = setInterval(updateStatus, 1000);

      try {
        const enumThreshold = enumSlider ? parseInt(enumSlider.value, 10) : null;
        const numSamples = samplesInput ? parseInt(samplesInput.value, 10) : null;
        const numWorkers = parseInt(localStorage.getItem("sim-workers"), 10) || null;
        const body = { team: teamName };
        if (cutoffWeek != null) body.cutoff_week = cutoffWeek;
        if (enumThreshold != null) body.enumeration_threshold = enumThreshold;
        if (numSamples != null) body.num_samples = numSamples;
        if (numWorkers != null) body.num_workers = numWorkers;
        // Pass MC playoff probability so the solver can trigger full tiebreaker
        // resolution when the fast path finds no qualifying universes.
        if (window._simulationResults) {
          const teamResult = window._simulationResults.team_results.find(
            (t) => t.team === teamName
          );
          if (teamResult) {
            body.playoff_probability = teamResult.playoff_probability;
          }
        }
        const response = await fetch("/api/clinching-scenarios", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: abortController.signal,
        });
        if (!response.ok) {
          const err = await response.json().catch(() => ({}));
          throw new Error(err.message || "Server error");
        }
        const data = await response.json();
        clearInterval(msgInterval);
        clearInterval(timerInterval);
        progress.style.display = "none";
        resultsDiv.innerHTML = _renderClinchingResults(data);
      } catch (err) {
        clearInterval(msgInterval);
        clearInterval(timerInterval);
        progress.style.display = "none";
        if (err.name === "AbortError") {
          resultsDiv.innerHTML = '<p style="opacity:0.6;margin-top:10px">Cancelled.</p>';
        } else {
          resultsDiv.innerHTML = `<p style="color:var(--mdn-accent-700);margin-top:10px">${err.message || "Clinching analysis failed."}</p>`;
        }
      } finally {
        clinchBtn.disabled = false;
      }
    });
  }
}

/**
 * Render clinching scenarios results as HTML.
 */
function _renderClinchingResults(data) {
  if (!data.record_groups || data.record_groups.length === 0) {
    return `<p style="margin-top:14px;opacity:0.6">No clinching scenarios found for this team.</p>`;
  }

  let html = `<div style="margin-top:14px">`;

  // Method label
  if (!data.exhaustive) {
    html += `<p style="font-size:12px;color:var(--mdn-accent-700);margin-bottom:10px">
      Results based on sampling — covers the most likely paths but may not be exhaustive.
    </p>`;
  }

  html += `<p style="font-size:12.5px;opacity:0.65;margin-bottom:14px">
    ${data.relevant_games_count} relevant games analyzed via ${data.method}.
    Scenarios sorted by fewest required conditions.
  </p>`;

  for (const rg of data.record_groups) {
    const record = `${rg.wins}-${rg.losses}` + (rg.ties > 0 ? `-${rg.ties}` : "");

    if (rg.no_path) {
      html += `<div class="mdn-card" style="border-left:3px solid var(--mdn-accent-500);padding:12px 16px;margin-bottom:8px">
        <strong style="font-size:13px">Finish ${record}</strong>
        <span class="mdn-tag mdn-tag-elim" style="margin-left:10px">No path to playoffs</span>
      </div>`;
      continue;
    }

    html += `<div class="mdn-card" style="padding:0;margin-bottom:14px;overflow:hidden">
      <div style="padding:10px 16px;border-bottom:1px solid var(--mdn-divider)">
        <strong style="font-size:13px">Finish ${record}</strong>
        <span style="font-size:11.5px;opacity:0.6;margin-left:10px">
          ${rg.scenarios.length} scenario${rg.scenarios.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div style="padding:12px 16px">`;

    if (rg.scenarios.length === 0) {
      html += `<span class="mdn-tag mdn-tag-accent">Clinches regardless of other outcomes</span>`;
    } else {
      const autoClinch = rg.scenarios.some((s) => s.num_conditions === 0);
      const condScenarios = rg.scenarios.filter((s) => s.num_conditions > 0);

      if (autoClinch) {
        html += `<span class="mdn-tag mdn-tag-accent">Clinches regardless of other outcomes</span>`;
      }

      // A single table per record group — not one table per scenario — so the
      // Week/Game/Needed columns line up across every scenario instead of each
      // auto-sizing to its own row. The # column is rowspan'd to group each
      // scenario's conditions.
      if (condScenarios.length > 0) {
        html += `<table class="mdn-led-table" style="${autoClinch ? "margin-top:10px" : ""}">
          <thead><tr><th style="width:36px" class="mdn-num">#</th><th>Week</th><th>Game</th><th>Needed</th></tr></thead>
          <tbody>`;
        for (let i = 0; i < condScenarios.length; i++) {
          const scenario = condScenarios[i];
          for (let c_idx = 0; c_idx < scenario.conditions.length; c_idx++) {
            const c = scenario.conditions[c_idx];
            const neededTag = c.is_tie
              ? `<span class="mdn-tag mdn-tag-tie">Tie</span>`
              : `<span class="mdn-tag mdn-tag-win-o">${_escapeHtml(c.required_winner)} win</span>`;
            const rowStyle = c_idx === 0 && i > 0 ? ' style="border-top:2px solid var(--mdn-divider-strong)"' : "";
            html += `<tr${rowStyle}>`;
            if (c_idx === 0) {
              html += `<td class="mdn-num" rowspan="${scenario.conditions.length}" style="opacity:0.6;vertical-align:middle">${i + 1}</td>`;
            }
            html += `<td>${c.week}</td>
              <td>${_escapeHtml(c.home_team)} vs ${_escapeHtml(c.away_team)}</td>
              <td>${neededTag}</td>
            </tr>`;
          }
        }
        html += `</tbody></table>`;
      }
    }

    html += `</div></div>`;
  }

  html += `</div>`;
  return html;
}

/**
 * Group team results by conference.
 *
 * @param {Array} teamResults - Array of team result objects.
 * @returns {Object} Map of conference name to array of team results.
 */
function _groupByConference(teamResults) {
  const grouped = {};
  for (const team of teamResults) {
    const conf = team.conference;
    if (!grouped[conf]) {
      grouped[conf] = [];
    }
    grouped[conf].push(team);
  }
  return grouped;
}

/**
 * Escape HTML special characters to prevent XSS.
 *
 * @param {string} str - The string to escape.
 * @returns {string} Escaped string.
 */
function _escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
