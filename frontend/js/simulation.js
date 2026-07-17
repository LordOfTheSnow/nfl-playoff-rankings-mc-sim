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

  // Build the results page
  let html = "";

  // Metadata header
  html += `<div class="card card-body mb-3">
    <h2>Simulation Results</h2>
    <p class="cutoff-label">
      ${results.iterations_run.toLocaleString()} iterations | Cutoff week: ${results.cutoff_week_used}
      | Fixed games: ${results.fixed_games || "?"} | Simulated games: ${results.simulated_games || "?"}
      ${results.low_confidence ? ' | <strong style="color:var(--color-warning)">Low confidence</strong>' : ""}
      ${results.convergence_achieved ? "" : ' | <strong style="color:var(--color-warning)">Convergence not achieved</strong>'}
    </p>
  </div>`;

  // Playoff probability summary tables by conference
  html += _renderPlayoffProbabilityTables(results.team_results);

  // Seeding probability matrix by conference
  html += _renderSeedingMatrix(results.team_results);

  // Top 50 scenarios
  html += _renderTopScenarios(results.top_scenarios);

  // Team detail panel (hidden initially, shown on team click)
  html += `<div id="team-detail-panel" class="results-section" style="margin-top:2.5rem" hidden></div>`;

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

    html += `<div class="results-section">
      <h2><img src="img/logos/${conf.toLowerCase()}.png" alt="${conf}" width="24" height="24" style="vertical-align:middle;margin-right:0.5rem">${conf} Playoff Probabilities</h2>
      <table class="table table-striped table-hover" aria-label="${conf} playoff probabilities">
        <thead>
          <tr>
            <th>#</th>
            <th class="team-name">Team</th>
            <th>Division</th>
            <th>Playoff %</th>
            <th>Strength</th>
          </tr>
        </thead>
        <tbody>`;

    for (let idx = 0; idx < teams.length; idx++) {
      const team = teams[idx];
      const logoId = TEAM_LOGO_IDS[team.team] || "";
      const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="" width="20" height="20" style="vertical-align:middle;margin-right:0.4rem">` : "";
      const borderStyle = idx === 7 ? ' style="border-top:2px solid var(--color-primary)"' : '';
      html += `<tr${borderStyle}>
        <td class="numeric">${idx + 1}</td>
        <td class="team-name">
          ${logoHtml}<a href="#" data-team-click="${_escapeHtml(team.team)}" class="team-link">${_escapeHtml(team.team)}</a>
        </td>
        <td>${_escapeHtml(team.division)}</td>
        <td class="numeric">${team.playoff_probability.toFixed(1)}%</td>
        <td class="numeric">${team.strength_rating.toFixed(3)}</td>
      </tr>`;
    }

    html += `</tbody></table></div>`;
  }

  return html;
}

/**
 * Render seeding probability matrix (teams × seeds 1-7) grouped by conference.
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

    html += `<div class="results-section">
      <h2><img src="img/logos/${conf.toLowerCase()}.png" alt="${conf}" width="24" height="24" style="vertical-align:middle;margin-right:0.5rem">${conf} Seeding Probabilities</h2>
      <table class="table table-bordered table-hover" aria-label="${conf} seeding probability matrix">
        <thead>
          <tr>
            <th class="team-name">Team</th>
            ${Array.from({ length: 7 }, (_, i) => `<th>Seed ${i + 1}</th>`).join("")}
          </tr>
        </thead>
        <tbody>`;

    for (const team of teams) {
      const seeds = team.seed_probabilities || {};
      const logoId = TEAM_LOGO_IDS[team.team] || "";
      const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="" width="20" height="20" style="vertical-align:middle;margin-right:0.4rem">` : "";
      html += `<tr>
        <td class="team-name">
          ${logoHtml}<a href="#" data-team-click="${_escapeHtml(team.team)}" class="team-link">${_escapeHtml(team.team)}</a>
        </td>`;
      for (let s = 1; s <= 7; s++) {
        const prob = seeds[String(s)] || 0;
        const intensity = Math.min(prob / 50, 1); // Scale for background color
        const bgColor = prob > 0
          ? `rgba(27, 58, 107, ${(intensity * 0.3).toFixed(2)})`
          : "transparent";
        html += `<td class="numeric" style="background-color:${bgColor}">${prob.toFixed(1)}%</td>`;
      }
      html += `</tr>`;
    }

    html += `</tbody></table></div>`;
  }

  return html;
}

/**
 * Render the top 50 most likely distinct playoff bracket scenarios.
 *
 * @param {Array} topScenarios - Array of scenario objects.
 * @returns {string} HTML string.
 */
function _renderTopScenarios(topScenarios) {
  if (!topScenarios || topScenarios.length === 0) {
    return `<div class="results-section">
      <h2>Top Playoff Scenarios</h2>
      <div class="empty-state"><p>No scenarios available.</p></div>
    </div>`;
  }

  const scenarios = topScenarios;

  let html = `<div class="results-section">
    <details>
    <summary><h2 style="display:inline">Top ${scenarios.length} Most Likely Playoff Scenarios</h2></summary>
    <ol class="scenario-list">`;

  for (let i = 0; i < scenarios.length; i++) {
    const scenario = scenarios[i];
    html += `<li class="scenario-item">
      <div class="scenario-details">
        <strong>#${i + 1}</strong>
        <span class="scenario-seeds">
          <span><strong>AFC:</strong> ${scenario.afc_seeds.map(_escapeHtml).join(", ")}</span>
          <br>
          <span><strong>NFC:</strong> ${scenario.nfc_seeds.map(_escapeHtml).join(", ")}</span>
        </span>
      </div>
      <span class="scenario-probability">${scenario.probability.toFixed(2)}%</span>
    </li>`;
  }

  html += `</ol></details></div>`;
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
  const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="${_escapeHtml(teamName)} logo" width="28" height="28" style="vertical-align:middle;margin-right:0.5rem">` : "";
  let html = `<h2>${logoHtml}${_escapeHtml(teamName)} — Details</h2>`;

  // Team summary
  html += `<div class="card card-body mb-3">
    <p><strong>Conference:</strong> ${_escapeHtml(teamData.conference)} | 
       <strong>Division:</strong> ${_escapeHtml(teamData.division)}</p>
    <p><strong>Playoff Probability:</strong> ${teamData.playoff_probability.toFixed(1)}% | 
       <strong>Strength Rating:</strong> ${teamData.strength_rating.toFixed(3)}</p>
  </div>`;

  // Seed distribution
  html += `<div class="card card-body mb-3">
    <h3>Seed Distribution</h3>
    <table class="table table-bordered table-hover" aria-label="Seed distribution for ${_escapeHtml(teamName)}">
      <thead><tr>`;
  for (let s = 1; s <= 7; s++) {
    html += `<th>Seed ${s}</th>`;
  }
  html += `</tr></thead><tbody><tr>`;
  const seeds = teamData.seed_probabilities || {};
  for (let s = 1; s <= 7; s++) {
    const prob = seeds[String(s)] || 0;
    const intensity = Math.min(prob / 50, 1);
    const bgColor = prob > 0
      ? `rgba(27, 58, 107, ${(intensity * 0.3).toFixed(2)})`
      : "transparent";
    html += `<td class="numeric" style="background-color:${bgColor};text-align:center">${prob.toFixed(1)}%</td>`;
  }
  html += `</tr></tbody></table></div>`;

  // Impact games (if available in team data)
  if (teamData.impact_games && teamData.impact_games.length > 0) {
    html += `<div class="card card-body mb-3">
      <h3>Top 5 Impact Games</h3>
      <table class="table table-striped table-hover" aria-label="Impact games for ${_escapeHtml(teamName)}">
        <thead><tr>
          <th>Week</th><th>Matchup</th><th>Impact</th>
        </tr></thead><tbody>`;

    const impactGames = teamData.impact_games.slice(0, 5);
    for (const game of impactGames) {
      html += `<tr>
        <td>${game.week || "—"}</td>
        <td>${_escapeHtml(game.home_team || "")} vs ${_escapeHtml(game.away_team || "")}</td>
        <td class="numeric">${game.impact != null ? game.impact.toFixed(1) + "%" : "—"}</td>
      </tr>`;
    }

    html += `</tbody></table></div>`;
  }

  // Clinching scenarios - on-demand button (only for teams between 0% and 100%)
  if (teamData.playoff_probability > 0 && teamData.playoff_probability < 100) {
    html += `<div class="card card-body mb-3" id="clinch-section-${_escapeHtml(teamName)}">
      <h3>Clinching Scenarios</h3>
      <p style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:0.75rem">
        Find all game-outcome combinations that guarantee ${_escapeHtml(teamName)} a playoff spot.
      </p>
      <div class="d-flex gap-2 flex-wrap align-items-center">
        <button id="btn-clinching" class="btn btn-secondary" type="button" data-team="${_escapeHtml(teamName)}">
          Clinching Scenarios
        </button>
        <span id="clinch-estimate-text" style="font-size:0.8rem;color:var(--color-text-muted)"></span>
      </div>
      <div id="clinch-progress" style="display:none;margin-top:0.75rem;align-items:center;gap:0.75rem">
        <div class="spinner-border spinner-border-sm text-primary" role="status"><span class="visually-hidden">Computing…</span></div>
        <span id="clinch-status-text" style="font-size:0.85rem;color:var(--color-text-muted)">Computing clinching scenarios…</span>
      </div>
      <div id="clinch-results"></div>
    </div>`;
  }

  panel.innerHTML = html;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });

  // Wire up clinching scenarios button
  const clinchBtn = document.getElementById("btn-clinching");
  if (clinchBtn) {
    // Use the simulation's cutoff week so the solver matches the sim context
    const cutoffWeek = results.cutoff_week_used || null;

    // Fetch estimate on render
    API.clinchEstimate(teamName, cutoffWeek).then(est => {
      const estEl = document.getElementById("clinch-estimate-text");
      if (!estEl) return;
      if (!est.available) {
        clinchBtn.disabled = true;
        clinchBtn.title = est.reason || "Not available";
        estEl.textContent = est.reason || "Not available before week 14";
      } else {
        estEl.textContent = `~${est.estimated_seconds}s · ${est.method} · ${est.relevant_games} relevant games`;
      }
    }).catch(() => {});

    clinchBtn.addEventListener("click", async () => {
      const progress = document.getElementById("clinch-progress");
      const statusText = document.getElementById("clinch-status-text");
      const resultsDiv = document.getElementById("clinch-results");
      clinchBtn.disabled = true;
      progress.style.display = "flex";
      resultsDiv.innerHTML = "";

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
        const data = await API.clinchingScenarios(teamName, cutoffWeek);
        clearInterval(msgInterval);
        clearInterval(timerInterval);
        progress.style.display = "none";
        resultsDiv.innerHTML = _renderClinchingResults(data);
      } catch (err) {
        clearInterval(msgInterval);
        clearInterval(timerInterval);
        progress.style.display = "none";
        resultsDiv.innerHTML = `<p style="color:var(--color-accent);margin-top:0.5rem">${err.message || "Clinching analysis failed."}</p>`;
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
    return `<p style="margin-top:0.75rem;color:var(--color-text-muted)">No clinching scenarios found for this team.</p>`;
  }

  let html = `<div style="margin-top:0.75rem">`;

  // Method label
  if (!data.exhaustive) {
    html += `<p style="font-size:0.8rem;color:var(--color-warning);margin-bottom:0.75rem">
      Results based on sampling — covers the most likely paths but may not be exhaustive.
    </p>`;
  }

  html += `<p style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:1rem">
    ${data.relevant_games_count} relevant games analyzed via ${data.method}.
    Scenarios sorted by fewest required conditions.
  </p>`;

  for (const rg of data.record_groups) {
    const record = `${rg.wins}-${rg.losses}` + (rg.ties > 0 ? `-${rg.ties}` : "");

    if (rg.no_path) {
      html += `<div class="card mb-2" style="border-left:3px solid var(--color-accent)">
        <div class="card-body py-2 px-3">
          <strong>Finish ${record}</strong>
          <span style="color:var(--color-accent);margin-left:0.5rem">No path to playoffs</span>
        </div>
      </div>`;
      continue;
    }

    html += `<div class="card mb-3">
      <div class="card-header py-2">
        <strong>Finish ${record}</strong>
        <span style="font-size:0.8rem;color:var(--color-text-muted);margin-left:0.75rem">
          ${rg.scenarios.length} scenario${rg.scenarios.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div class="card-body py-2 px-3">`;

    if (rg.scenarios.length === 0) {
      html += `<p style="color:var(--color-success)">Team clinches regardless of other outcomes.</p>`;
    } else {
      for (let i = 0; i < rg.scenarios.length; i++) {
        const scenario = rg.scenarios[i];
        if (scenario.num_conditions === 0) {
          html += `<p style="color:var(--color-success);font-weight:600">Clinches regardless of other outcomes.</p>`;
          continue;
        }
        html += `<div style="margin-bottom:0.75rem;padding:0.5rem;background:var(--color-surface);border-radius:var(--radius-sm)">
          <span style="font-size:0.8rem;color:var(--color-text-muted)">Scenario ${i + 1} — ${scenario.num_conditions} condition${scenario.num_conditions !== 1 ? "s" : ""}:</span>
          <table class="table table-sm table-striped mb-0" style="margin-top:0.25rem;width:auto;font-size:0.85rem">
            <thead><tr><th>Week</th><th>Game</th><th>Needed</th></tr></thead><tbody>`;
        for (const c of scenario.conditions) {
          const needed = c.is_tie ? "Tie" : _escapeHtml(c.required_winner) + " wins";
          html += `<tr>
            <td>${c.week}</td>
            <td>${_escapeHtml(c.home_team)} vs ${_escapeHtml(c.away_team)}</td>
            <td><strong>${needed}</strong></td>
          </tr>`;
        }
        html += `</tbody></table></div>`;
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
