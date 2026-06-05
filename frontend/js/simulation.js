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
let _simulationResults = null;

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
    <div class="controls-panel">
      <h2>Simulation Controls</h2>
      <div class="control-group">
        <div class="control-field">
          <label for="sim-iterations">Iterations</label>
          <input type="number" id="sim-iterations" min="100" max="1000000" value="10000"
                 aria-describedby="iterations-help">
          <span id="iterations-help" class="cutoff-label">100 to 1,000,000 trials</span>
        </div>
        <div class="control-field">
          <label for="sim-cutoff-week">Cutoff Week</label>
          <select id="sim-cutoff-week" aria-describedby="cutoff-help">
            <option value="">Auto (latest completed)</option>
            ${Array.from({ length: 18 }, (_, i) => i + 1)
              .map((w) => `<option value="${w}">Week ${w}</option>`)
              .join("")}
          </select>
          <span id="cutoff-help" class="cutoff-label" aria-live="polite">
            Games after the cutoff week will be simulated
          </span>
        </div>
        <div class="control-field">
          <label for="sim-noise">Game Noise</label>
          <input type="range" id="sim-noise" min="0" max="100" value="20"
                 aria-describedby="noise-help" style="min-width:160px">
          <span id="noise-help" class="cutoff-label">0.20 — moderate variance</span>
        </div>
      </div>
      <div class="control-group">
        <button id="btn-run-simulation" class="btn btn-primary" type="button">
          Run Simulation
        </button>
        <button id="btn-fetch-data" class="btn btn-secondary" type="button">
          Fetch Data
        </button>
      </div>
      <p id="sim-total-games" class="cutoff-label" style="margin-top:1rem;font-size:0.9rem" aria-live="polite"></p>
    </div>
    <div id="sim-progress" class="progress-indicator" hidden>
      <div class="spinner" aria-hidden="true"></div>
      <span class="progress-text">Running simulation…</span>
    </div>
    <div id="sim-progress-overlay" class="progress-overlay" hidden></div>
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
  const progressEl = document.getElementById("sim-progress");
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

  // Show progress
  progressEl.hidden = false;
  overlayEl.hidden = false;
  runBtn.disabled = true;

  try {
    const results = await API.runSimulation(iterations, cutoffWeek, noise);
    _simulationResults = results;
    App.showInfo("Simulation complete.");
    App.navigate("results");
  } catch (err) {
    App.showError(err.message || "Simulation failed.");
  } finally {
    progressEl.hidden = true;
    overlayEl.hidden = true;
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
  if (!_simulationResults) {
    contentEl.innerHTML = `
      <div class="empty-state">
        <p>No simulation results available.</p>
        <p>Go to <a href="#simulate">Simulate</a> to run a simulation first.</p>
      </div>
    `;
    return;
  }

  const results = _simulationResults;

  // Build the results page
  let html = "";

  // Metadata header
  html += `<div class="controls-panel">
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
  html += `<div id="team-detail-panel" class="results-section" hidden></div>`;

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
      <h2>${conf} Playoff Probabilities</h2>
      <table class="probability-table" aria-label="${conf} playoff probabilities">
        <thead>
          <tr>
            <th class="team-name">Team</th>
            <th>Division</th>
            <th>Playoff %</th>
            <th>Strength</th>
          </tr>
        </thead>
        <tbody>`;

    for (const team of teams) {
      const logoId = TEAM_LOGO_IDS[team.team] || "";
      const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="" width="20" height="20" style="vertical-align:middle;margin-right:0.4rem">` : "";
      html += `<tr>
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
      <h2>${conf} Seeding Probabilities</h2>
      <table class="probability-table" aria-label="${conf} seeding probability matrix">
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
    <h2>Top ${scenarios.length} Most Likely Playoff Scenarios</h2>
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

  html += `</ol></div>`;
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

  let html = `<h2>${_escapeHtml(teamName)} — Details</h2>`;

  // Team summary
  html += `<div class="controls-panel">
    <p><strong>Conference:</strong> ${_escapeHtml(teamData.conference)} | 
       <strong>Division:</strong> ${_escapeHtml(teamData.division)}</p>
    <p><strong>Playoff Probability:</strong> ${teamData.playoff_probability.toFixed(1)}% | 
       <strong>Strength Rating:</strong> ${teamData.strength_rating.toFixed(3)}</p>
  </div>`;

  // Seed distribution
  html += `<div class="controls-panel">
    <h3>Seed Distribution</h3>
    <table class="probability-table" aria-label="Seed distribution for ${_escapeHtml(teamName)}">
      <thead><tr>`;
  for (let s = 1; s <= 7; s++) {
    html += `<th>Seed ${s}</th>`;
  }
  html += `</tr></thead><tbody><tr>`;
  const seeds = teamData.seed_probabilities || {};
  for (let s = 1; s <= 7; s++) {
    const prob = seeds[String(s)] || 0;
    html += `<td class="numeric">${prob.toFixed(1)}%</td>`;
  }
  html += `</tr></tbody></table></div>`;

  // Impact games (if available in team data)
  if (teamData.impact_games && teamData.impact_games.length > 0) {
    html += `<div class="controls-panel">
      <h3>Top 5 Impact Games</h3>
      <table class="probability-table" aria-label="Impact games for ${_escapeHtml(teamName)}">
        <thead><tr>
          <th>Week</th><th>Matchup</th><th>Impact</th>
        </tr></thead><tbody>`;

    const impactGames = teamData.impact_games.slice(0, 5);
    for (const game of impactGames) {
      html += `<tr>
        <td class="numeric">${game.week || "—"}</td>
        <td>${_escapeHtml(game.home_team || "")} vs ${_escapeHtml(game.away_team || "")}</td>
        <td class="numeric">${game.impact != null ? game.impact.toFixed(1) + "%" : "—"}</td>
      </tr>`;
    }

    html += `</tbody></table></div>`;
  }

  panel.innerHTML = html;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
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
