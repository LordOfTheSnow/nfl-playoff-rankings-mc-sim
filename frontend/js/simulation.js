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
    window._simulationResults = results;
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
      <h2><img src="img/logos/${conf.toLowerCase()}.png" alt="${conf}" width="24" height="24" style="vertical-align:middle;margin-right:0.5rem">${conf} Playoff Probabilities</h2>
      <table class="probability-table" aria-label="${conf} playoff probabilities">
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

  // Playoff path analysis - on-demand button
  if (teamData.playoff_probability < 75) {
    html += `<div class="controls-panel" id="path-section-${_escapeHtml(teamName)}">
      <h3>Playoff Path</h3>
      <p style="font-size:0.85rem;color:var(--color-text-muted);margin-bottom:0.75rem">
        Analyze what game outcomes are needed for ${_escapeHtml(teamName)} to make the playoffs.
      </p>
      <button id="btn-analyze-path" class="btn btn-secondary" type="button" data-team="${_escapeHtml(teamName)}">
        Analyze Playoff Path
      </button>
      <button id="btn-guaranteed-path" class="btn btn-secondary" type="button" data-team="${_escapeHtml(teamName)}" style="margin-left:0.5rem">
        Find Guaranteed Path
      </button>
      <div id="path-spinner" style="display:none;margin-top:0.5rem;align-items:center;gap:0.5rem">
        <div class="spinner"></div><span style="font-size:0.85rem;color:var(--color-text-muted)">Running path analysis…</span>
      </div>
      <div id="path-results"></div>
    </div>`;
  }

  panel.innerHTML = html;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });

  // Wire up the analyze button
  const analyzeBtn = document.getElementById("btn-analyze-path");
  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", async () => {
      const spinner = document.getElementById("path-spinner");
      const resultsDiv = document.getElementById("path-results");
      analyzeBtn.disabled = true;
      spinner.style.display = "flex";

      try {
        // Use higher iterations and same cutoff as last simulation
        const cutoff = results.cutoff_week_used || null;
        const pathData = await API.analyzePath(teamName, 5000, cutoff, 0.2);
        spinner.style.display = "none";
        resultsDiv.innerHTML = _renderPathResults(pathData);
      } catch (err) {
        spinner.style.display = "none";
        resultsDiv.innerHTML = `<p style="color:var(--color-accent);margin-top:0.5rem">${err.message || "Path analysis failed."}</p>`;
      } finally {
        analyzeBtn.disabled = false;
      }
    });
  }
  // Wire up the guaranteed path button
  const guaranteedBtn = document.getElementById("btn-guaranteed-path");
  if (guaranteedBtn) {
    guaranteedBtn.addEventListener("click", async () => {
      const spinner = document.getElementById("path-spinner");
      const resultsDiv = document.getElementById("path-results");
      guaranteedBtn.disabled = true;
      spinner.style.display = "flex";

      try {
        const cutoff = results.cutoff_week_used || null;
        const pathData = await API.guaranteedPath(teamName, cutoff);
        spinner.style.display = "none";
        resultsDiv.innerHTML = _renderGuaranteedPath(pathData);
      } catch (err) {
        spinner.style.display = "none";
        resultsDiv.innerHTML = `<p style="color:var(--color-accent);margin-top:0.5rem">${err.message || "Guaranteed path analysis failed."}</p>`;
      } finally {
        guaranteedBtn.disabled = false;
      }
    });
  }
}

/**
 * Render guaranteed path results as HTML.
 */
function _renderGuaranteedPath(data) {
  let html = `<div style="margin-top:0.75rem">`;

  if (!data.found_path) {
    html += `<p style="color:var(--color-text-muted)">${data.message}</p>`;
    if (data.team_must_win && data.team_must_win.length > 0) {
      html += `<p style="margin-top:0.5rem;font-size:0.85rem"><strong>At minimum, the team must win:</strong></p>
        <ul style="font-size:0.85rem;margin-top:0.25rem">`;
      for (const g of data.team_must_win) {
        html += `<li>Week ${g.week}: vs ${_escapeHtml(g.opponent)}</li>`;
      }
      html += `</ul>`;
    }
    html += `</div>`;
    return html;
  }

  html += `<p style="color:var(--color-success);font-weight:600;margin-bottom:0.75rem">${data.message}</p>`;

  // Team's own games
  if (data.team_must_win && data.team_must_win.length > 0) {
    html += `<h4 style="font-size:0.9rem;margin-bottom:0.5rem">Team must win all remaining games:</h4>
      <table class="probability-table" style="margin-bottom:1rem">
        <thead><tr><th>Week</th><th>Opponent</th></tr></thead><tbody>`;
    for (const g of data.team_must_win) {
      html += `<tr style="background-color:var(--color-division-leader-bg)">
        <td class="numeric">${g.week}</td>
        <td>${_escapeHtml(g.opponent)}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  // Required other outcomes
  if (data.required_outcomes && data.required_outcomes.length > 0) {
    html += `<h4 style="font-size:0.9rem;margin-bottom:0.5rem">Other required results:</h4>
      <table class="probability-table">
        <thead><tr><th>Week</th><th>Game</th><th>Required Winner</th><th>Required Loser</th></tr></thead><tbody>`;
    for (const g of data.required_outcomes) {
      html += `<tr>
        <td class="numeric">${g.week}</td>
        <td>${_escapeHtml(g.home_team)} vs ${_escapeHtml(g.away_team)}</td>
        <td style="color:var(--color-success);font-weight:600">${_escapeHtml(g.required_winner)}</td>
        <td style="color:var(--color-accent)">${_escapeHtml(g.required_loser)}</td>
      </tr>`;
    }
    html += `</tbody></table>`;
  }

  if (data.verified) {
    html += `<p style="font-size:0.8rem;color:var(--color-success);margin-top:0.75rem">✓ Verified: if all these outcomes happen, the team is guaranteed a playoff spot regardless of other game results.</p>`;
  }

  html += `</div>`;
  return html;
}

/**
 * Render path analysis results as HTML.
 */
function _renderPathResults(pathData) {
  if (!pathData.path || pathData.path.length === 0) {
    return `<p style="margin-top:0.75rem;color:var(--color-text-muted)">${pathData.message || "No clear path found. The team may need very specific combinations that vary too much across trials."}</p>`;
  }

  let html = `<p style="font-size:0.85rem;color:var(--color-text-muted);margin:0.75rem 0 0.5rem">
    Based on ${pathData.qualifying_trials} qualifying trials (${pathData.playoff_probability}% probability). Only games with causal impact are shown.
  </p>`;

  html += `<table class="probability-table" style="margin-top:0.5rem">
    <thead><tr><th>Week</th><th>Game</th><th>Needed Result</th><th>Confidence</th></tr></thead><tbody>`;

  for (const g of pathData.path) {
    const winner = g.is_tie ? "Tie" : _escapeHtml(g.required_winner || "");
    const matchup = _escapeHtml(g.home_team) + " vs " + _escapeHtml(g.away_team);
    const isOwn = g.involves_team;
    const rowStyle = isOwn ? ' style="font-weight:600;background-color:var(--color-division-leader-bg)"' : '';
    html += `<tr${rowStyle}>
      <td class="numeric">${g.week}</td>
      <td>${matchup}</td>
      <td><strong>${winner}</strong> wins</td>
      <td class="numeric">${g.frequency}%</td>
    </tr>`;
  }

  html += `</tbody></table>
    <p style="font-size:0.8rem;color:var(--color-text-muted);margin-top:0.75rem;line-height:1.6">
      <strong>How to read:</strong> Games highlighted in blue are the team's own games.
      The confidence % shows how often this outcome occurred across all qualifying simulation trials.
      <br>• <strong>100%</strong> = happened in every qualifying trial — essentially mandatory.
      <br>• <strong>75–99%</strong> = needed in most paths, but a few alternative routes exist without it.
      <br>• <strong>60–75%</strong> = helpful in the majority of paths, but other outcomes can compensate.
      <br><br>Only games where flipping the result would actually change the team's playoff status are shown (causality-filtered).
      If a game shows 76.5% confidence, it means in 23.5% of qualifying trials the opposite result happened but the team still made the playoffs via a different combination.
    </p>`;

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
