/**
 * Simulations view for the NFL Monte Carlo Playoff Simulator.
 *
 * Provides one global function:
 *   - renderSimulations(contentEl) — renders the Simulations view (#simulations)
 *
 * This page owns the whole simulation: it fetches season status, renders the
 * shared "Season data" card plus its own Iterations/Cutoff/Noise/Workers/
 * Simulate/Fetch-data controls, then the results output (probability tables,
 * seeding matrix, top-scenarios accordion) and the inline per-team
 * candidate-details panel revealed by clicking a team name. #simulate and
 * #results are legacy aliases that redirect here (see app.js).
 *
 * Requirements: 5.5, 6.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 9.10,
 *               11.1, 11.2, 11.7, 11.11, 11.12, 11.13, 11.14
 */

"use strict";

/** Module-level storage for the latest simulation results. */
window._simulationResults = null;

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
 * Build the ms/eval trend sparkline SVG (140x28, min/max-normalized,
 * oldest -> newest, latest point marked with a filled dot). Modernist
 * "Solver Timing History" redesign — see design_handoff_standings_redesign/
 * (Option 4a).
 *
 * @param {Array} timings - Array of timing rows as returned by the API
 *   (newest first); reversed internally to plot oldest -> newest.
 * @returns {string} SVG markup, or an empty-state span if fewer than 2 points.
 */
function _buildTimingSparkline(timings) {
  const values = timings.map((t) => t.ms_per_eval).reverse();
  if (values.length < 2) {
    return '<span style="font-size:11px;opacity:0.5">Not enough data</span>';
  }
  const width = 140;
  const height = 28;
  const pad = 3;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = (width - pad * 2) / (values.length - 1);

  const points = values.map((v, i) => {
    const x = pad + i * step;
    const y = height - pad - ((v - min) / range) * (height - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const [lastX, lastY] = points[points.length - 1].split(",");

  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    <polyline points="${points.join(" ")}" fill="none" stroke="var(--mdn-accent-700)" stroke-width="1.5"></polyline>
    <circle cx="${lastX}" cy="${lastY}" r="2.5" fill="var(--mdn-accent-500)"></circle>
  </svg>`;
}

/**
 * Handle the "Timing History" button click.
 * Opens a Modernist dialog showing solver timing history from the API.
 */
async function _handleTimingHistory() {
  // Create the dialog element if it doesn't exist yet
  let backdropEl = document.getElementById("timingHistoryModal");
  if (!backdropEl) {
    backdropEl = document.createElement("div");
    backdropEl.className = "mdn-dialog-backdrop";
    backdropEl.id = "timingHistoryModal";
    backdropEl.style.display = "none";
    backdropEl.innerHTML = `
      <div class="mdn-dialog" role="dialog" aria-modal="true" aria-labelledby="timingHistoryModalLabel">
        <div class="mdn-dialog-header">
          <div class="mdn-dialog-title" id="timingHistoryModalLabel">Solver Timing History</div>
          <button type="button" class="mdn-btn mdn-btn-icon mdn-btn-ghost" id="timingHistoryCloseX" aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        <div id="timingHistoryBody"></div>
        <div class="mdn-dialog-actions">
          <button type="button" class="mdn-btn mdn-btn-primary" id="timingHistoryCloseFooter">Close</button>
        </div>
      </div>
    `;
    document.body.appendChild(backdropEl);

    const closeDialog = () => {
      backdropEl.style.display = "none";
    };
    document.getElementById("timingHistoryCloseX").addEventListener("click", closeDialog);
    document.getElementById("timingHistoryCloseFooter").addEventListener("click", closeDialog);
    backdropEl.addEventListener("click", (e) => {
      if (e.target === backdropEl) closeDialog();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && backdropEl.style.display !== "none") closeDialog();
    });
  }

  const bodyEl = document.getElementById("timingHistoryBody");
  bodyEl.innerHTML = '<div class="mdn-dialog-body"><p><span class="mdn-spinner"></span> Loading…</p></div>';

  // Show dialog immediately with loading state
  backdropEl.style.display = "flex";

  try {
    const data = await API.solverTimings();
    if (!data.timings || data.timings.length === 0) {
      bodyEl.innerHTML = '<div class="mdn-dialog-body"><p>No timing data collected yet. Run the clinching solver to start building calibration data.</p></div>';
      return;
    }

    let rows = "";
    for (const t of data.timings) {
      const recordedAt = t.recorded_at ? new Date(t.recorded_at).toLocaleString() : "—";
      const methodCls = t.method === "sampling" ? "mdn-tag-outline-accent" : "mdn-tag-elim";
      rows += `<tr>
        <td class="mdn-num" style="font-weight:700">${t.ms_per_eval.toFixed(2)}</td>
        <td><span class="mdn-tag ${methodCls}" style="font-size:9px">${_escapeHtml(t.method)}</span></td>
        <td class="mdn-num">${t.relevant_games_count}</td>
        <td class="mdn-num">${t.total_evals.toLocaleString()}</td>
        <td style="opacity:0.6;font-size:12px">${_escapeHtml(recordedAt)}</td>
      </tr>`;
    }

    bodyEl.innerHTML = `
      <div class="mdn-dialog-body">
        <p>These measurements are collected after each solver run and used to calibrate time estimates. The system keeps the last 50 measurements.</p>
        <div class="mdn-dialog-stat-row">
          <div style="display:flex;align-items:baseline;gap:8px">
            <span class="mdn-stat-val" style="font-size:17px">${data.count} measurement${data.count === 1 ? "" : "s"}</span>
            <span style="font-size:12.5px;opacity:0.6">avg ${data.avg_ms_per_eval.toFixed(2)} ms/eval</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px;flex:none">
            <span class="mdn-stat-lbl" style="font-size:9px">ms/eval trend</span>
            ${_buildTimingSparkline(data.timings)}
          </div>
        </div>
      </div>
      <div class="mdn-dialog-scroll">
        <table class="mdn-led-table">
          <thead>
            <tr>
              <th class="mdn-num" style="width:80px">ms/eval</th>
              <th>Method</th>
              <th class="mdn-num">Games</th>
              <th class="mdn-num">Evaluations</th>
              <th>Recorded At</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  } catch (err) {
    bodyEl.innerHTML = `<div class="mdn-dialog-body"><p style="color:var(--mdn-accent-700)">Failed to load timing data: ${_escapeHtml(err.message || "Unknown error")}</p></div>`;
  }
}

/**
 * Build the Simulations page's header card: the shared "Season data" left
 * cell plus its own Iterations/Cutoff/Noise/Workers/Simulate/Fetch-data
 * right cell (design_handoff_simulation_flow_v2/, Option 3a).
 *
 * @param {Object|null} status - Status object from /api/status, or null.
 * @returns {string} HTML string.
 */
function _buildSimulationHeaderCard(status) {
  if (!status || status.total_games === 0) {
    return `<div class="mdn-card">
      <p style="color:rgba(32,30,29,.6)">No data fetched yet. Click <strong>Fetch data</strong> to load game data from ESPN.</p>
      <div style="margin-top:0.75rem">
        <button id="btn-fetch-data-sim" class="mdn-btn mdn-btn-primary" type="button">Fetch data</button>
      </div>
    </div>`;
  }

  const savedCutoffLS = App.getCutoffWeek();
  const cpuCount = status.cpu_count || 4;
  const savedWorkers = parseInt(localStorage.getItem("sim-workers"), 10) || cpuCount;
  // Persist the resolved default immediately (not just on drag), so every
  // other reader of `sim-workers` — notably the clinching panel's estimate
  // line — sees the same value this slider is showing. Without this the key
  // stays unset until the user drags the slider, and each reader falls back
  // to its own default (6 here vs. a hardcoded 4 there).
  if (localStorage.getItem("sim-workers") == null) {
    localStorage.setItem("sim-workers", String(savedWorkers));
  }
  const savedNoise = localStorage.getItem("sim-noise") || "34";
  const noiseVal = (parseInt(savedNoise, 10) / 100).toFixed(2);
  const noiseLabel = _noiseLabel(parseFloat(noiseVal));
  const savedIterations = parseInt(localStorage.getItem("sim-iterations"), 10) || 10000;

  // Tie Probability slider: raw value is hundredths of a percent (0-300 =
  // 0.00%-3.00%), so tieProbFraction = sliderValue / 10000. Seeded from the
  // server's empirical estimate (status.default_tie_probability) the first
  // time — falls back to the DEFAULT_TIE_PROBABILITY constant's value (0.5%)
  // if the status response doesn't have one yet (e.g. no data fetched).
  const storedTieProb = localStorage.getItem("sim-tie-probability");
  const savedTieProb = storedTieProb != null
    ? storedTieProb
    : String(Math.round((status.default_tie_probability != null ? status.default_tie_probability : 0.005) * 10000));
  // Persist the resolved default immediately (not just on drag) so
  // sharedTieProbability() — used by the clinching panel's estimate line —
  // reflects the real value in effect even before the user touches the slider.
  if (storedTieProb == null) localStorage.setItem("sim-tie-probability", savedTieProb);
  const tieProbVal = (parseInt(savedTieProb, 10) / 100).toFixed(2);
  const tieProbSource = storedTieProb != null ? "custom" : "estimated";

  // Left column is content-sized (`auto`) rather than a fixed fraction: the
  // "Season data" cell needs ~490px for its 4-stat row and nothing more, so
  // any extra proportional width it got was dead space that the controls
  // column needed to keep Simulate/Fetch data on the fields' row. The 100px
  // gap is a fixed, deliberate separator between the two cells (not just
  // grid breathing room) — the right column stretches to fill the rest of
  // the row, so this gap is exactly the visible space between them.
  let html = `<div class="mdn-card" style="display:grid;grid-template-columns:auto minmax(0,1fr);gap:160px">`;
  html += `<div>${buildSeasonDataCell(status, savedCutoffLS)}</div>`;

  // This cell stretches to fill the grid's full right column (default grid
  // item behavior), and the fields row below uses `justify-content:
  // space-between` so any extra width the column gets on wide screens is
  // spent widening the gaps *between* Iterations/Cutoff/Noise/Tie
  // Probability/Workers/Simulate+Fetch, rather than collecting as one dead
  // strip before the whole cluster.
  html += '<div>';
  html += '<div class="mdn-card-kicker">Simulation</div>';
  html += '<div style="display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap;justify-content:space-between;margin-top:6px">';

  // Simulate/Fetch data sit at the end of this same wrapping row, grouped
  // into one flex item so they can never split from each other. The grid's
  // content-sized left column leaves enough room for them to stay inline
  // after Workers at normal widths.

  html += '<div class="mdn-field" style="width:85px">' +
    '<label for="sim-iterations-sim">Iterations' +
    _infoIcon("Number of Monte Carlo trials to run. More iterations = more accurate probabilities but longer runtime.") +
    '</label>' +
    '<input class="mdn-input" type="number" id="sim-iterations-sim" min="100" max="1000000" value="' + savedIterations + '"></div>';

  html += '<div class="mdn-field" style="width:94px">' +
    '<label for="sim-cutoff-sim">Cutoff' +
    _infoIcon("Games up to and including this week use real results. Games after this week are simulated. Synced with the Standings page.") +
    '</label>' +
    '<select class="mdn-input" id="sim-cutoff-sim"><option value="">Auto</option>';
  for (let w = 1; w <= (status.season_weeks || 18); w++) {
    html += '<option value="' + w + '"' + (savedCutoffLS == w ? ' selected' : '') + '>Week ' + w + '</option>';
  }
  html += '</select></div>';

  html += '<div class="mdn-field" style="width:92px">' +
    '<label for="sim-noise-sim">Noise' +
    _infoIcon("Per-game strength noise: adds random variance to each simulated game outcome, modeling the unpredictability of real NFL games ('Any given Sunday').") +
    '</label>' +
    '<input type="range" class="mdn-input" id="sim-noise-sim" min="0" max="100" value="' + savedNoise + '">' +
    '<div class="mdn-hint" id="sim-noise-label-sim">' + noiseVal + ' — ' + noiseLabel + '</div></div>';

  html += '<div class="mdn-field" style="width:140px">' +
    '<label for="sim-tie-prob-sim">Tie Probability' +
    _infoIcon("Per-game tie probability. Defaults to an empirical estimate from historical seasons (falls back to 0.50% until enough data is cached) — drag to override.") +
    ' <span class="mdn-tt-wrap"><button class="mdn-reset-btn" id="sim-tie-prob-reset-sim" type="button" aria-label="Reset to calculated default">R</button>' +
    '<span class="mdn-tt-pop">Reset to the calculated (empirical) default — in case you forgot the original value after dragging the slider.</span></span>' +
    '</label>' +
    '<input type="range" class="mdn-input" id="sim-tie-prob-sim" min="0" max="100" value="' + savedTieProb + '">' +
    '<div class="mdn-hint" id="sim-tie-prob-label-sim">' + tieProbVal + '% (' + tieProbSource + ')</div></div>';

  html += '<div class="mdn-field" style="width:88px">' +
    '<label for="sim-workers-sim">Workers' +
    _infoIcon("Number of parallel CPU cores used to run the simulation. The clinching-scenarios solver uses the same worker count.") +
    '</label>' +
    '<input type="range" class="mdn-input" id="sim-workers-sim" min="1" max="' + cpuCount + '" value="' + savedWorkers + '">' +
    '<div class="mdn-hint" id="sim-workers-label-sim">' + savedWorkers + (savedWorkers === 1 ? ' core' : ' cores') + ' of ' + cpuCount + '</div></div>';

  html += '<div style="display:flex;gap:10px;margin-top:23px">' +
    '<button id="btn-run-sim" class="mdn-btn mdn-btn-primary" type="button">Simulate</button>' +
    '<button id="btn-fetch-data-sim" class="mdn-btn mdn-btn-secondary" type="button">Fetch data</button>' +
    '</div>';
  html += '</div>';
  html += '<p class="mdn-hint" id="sim-total-sim" style="margin-top:10px"></p>';
  html += '<div id="sim-progress-sim" style="margin-top:0.75rem;display:none;align-items:center;gap:0.6rem">' +
    '<span class="mdn-spinner"></span><span class="mdn-hint">Running simulation…</span></div>';
  html += '</div>';

  html += `</div>`;
  return html;
}

/**
 * Wire up the Simulations header card's controls after it's inserted into
 * the DOM (mirrors the pattern used for Standings' cutoff-only panel).
 *
 * @param {Object|null} status - Status object from /api/status, or null.
 */
function _wireSimulationHeaderCard(status) {
  const iterInput = document.getElementById("sim-iterations-sim");
  const cutoffSel = document.getElementById("sim-cutoff-sim");
  const noiseSl = document.getElementById("sim-noise-sim");
  const tieProbSl = document.getElementById("sim-tie-prob-sim");
  const workersSl = document.getElementById("sim-workers-sim");
  const runBtn = document.getElementById("btn-run-sim");
  const fetchBtn = document.getElementById("btn-fetch-data-sim");
  const totalEl = document.getElementById("sim-total-sim");

  if (!iterInput || !cutoffSel || !totalEl) {
    // "No data fetched yet" state — only the Fetch data button exists.
    if (fetchBtn) fetchBtn.addEventListener("click", _handleFetchFromSimulations);
    return;
  }

  const gamesPerWeek = (status && status.games_per_week) || {};
  const completedPerWeek = (status && status.completed_per_week) || {};

  function updateTotal() {
    const iters = parseInt(iterInput.value, 10) || 10000;
    const cutoff = cutoffSel.value ? parseInt(cutoffSel.value, 10) : ((status && status.auto_cutoff_week) || 0);
    let gamesToSim = 0;
    for (const [wk, cnt] of Object.entries(gamesPerWeek)) {
      const week = parseInt(wk, 10);
      if (week > cutoff) {
        gamesToSim += cnt;
      } else {
        gamesToSim += cnt - (completedPerWeek[wk] || 0);
      }
    }
    if (gamesToSim > 0) {
      totalEl.textContent = gamesToSim + ' games × ' + iters.toLocaleString() + ' iterations = ' + (gamesToSim * iters).toLocaleString() + ' game simulations';
    } else {
      totalEl.textContent = 'No games to simulate at this cutoff';
    }
  }

  iterInput.addEventListener("input", updateTotal);
  cutoffSel.addEventListener("change", updateTotal);
  updateTotal();

  iterInput.addEventListener("change", () => localStorage.setItem('sim-iterations', iterInput.value));
  cutoffSel.addEventListener("change", () => {
    App.setCutoffWeek(cutoffSel.value);
    const contentEl = document.getElementById("content");
    if (contentEl) renderSimulations(contentEl);
  });

  if (noiseSl) noiseSl.addEventListener("input", () => {
    const val = (parseInt(noiseSl.value, 10) / 100).toFixed(2);
    const label = _noiseLabel(parseFloat(val));
    const labelEl = document.getElementById("sim-noise-label-sim");
    if (labelEl) labelEl.textContent = val + " — " + label;
    localStorage.setItem('sim-noise', noiseSl.value);
  });

  if (tieProbSl) tieProbSl.addEventListener("input", () => {
    const val = (parseInt(tieProbSl.value, 10) / 100).toFixed(2);
    const labelEl = document.getElementById("sim-tie-prob-label-sim");
    if (labelEl) labelEl.textContent = val + "% (custom)";
    localStorage.setItem('sim-tie-probability', tieProbSl.value);
  });

  const tieProbResetBtn = document.getElementById("sim-tie-prob-reset-sim");
  if (tieProbResetBtn && tieProbSl) {
    const calculatedDefault = Math.min(100, Math.max(0, Math.round(
      (status && status.default_tie_probability != null ? status.default_tie_probability : 0.005) * 10000
    )));
    tieProbResetBtn.addEventListener("click", () => {
      tieProbSl.value = calculatedDefault;
      const val = (calculatedDefault / 100).toFixed(2);
      const labelEl = document.getElementById("sim-tie-prob-label-sim");
      if (labelEl) labelEl.textContent = val + "% (estimated)";
      localStorage.setItem('sim-tie-probability', String(calculatedDefault));
    });
  }

  if (workersSl) {
    const cpuCount = (status && status.cpu_count) ? status.cpu_count : 4;
    workersSl.addEventListener("input", () => {
      const val = parseInt(workersSl.value, 10);
      const labelEl = document.getElementById("sim-workers-label-sim");
      if (labelEl) labelEl.textContent = (val === 1 ? "1 core" : val + " cores") + " of " + cpuCount;
      localStorage.setItem('sim-workers', val);
    });
  }

  if (runBtn) runBtn.addEventListener("click", async () => {
    const iterations = parseInt(iterInput.value, 10) || 10000;
    const cutoffWeek = cutoffSel.value ? parseInt(cutoffSel.value, 10) : null;
    const noise = noiseSl ? parseInt(noiseSl.value, 10) / 100 : 0.34;
    const tieProbability = tieProbSl ? parseInt(tieProbSl.value, 10) / 10000 : null;
    const numWorkers = workersSl ? parseInt(workersSl.value, 10) : null;

    if (iterations < 100 || iterations > 1000000) {
      App.showError("Iterations must be between 100 and 1,000,000.");
      return;
    }

    const controls = [iterInput, cutoffSel, noiseSl, tieProbSl, tieProbResetBtn, workersSl, runBtn, fetchBtn].filter(Boolean);
    controls.forEach((el) => { el.disabled = true; });
    const progressEl = document.getElementById("sim-progress-sim");
    if (progressEl) progressEl.style.display = "flex";

    try {
      const results = await API.runSimulation(iterations, cutoffWeek, noise, numWorkers, tieProbability);
      results._ranAt = new Date();
      window._simulationResults = results;
      App.showInfo("Simulation complete.");
      const contentEl = document.getElementById("content");
      if (contentEl) await renderSimulations(contentEl);
    } catch (err) {
      App.showError(err.message || "Simulation failed.");
      controls.forEach((el) => { el.disabled = false; });
      if (progressEl) progressEl.style.display = "none";
    }
  });

  if (fetchBtn) fetchBtn.addEventListener("click", _handleFetchFromSimulations);
}

/**
 * Handle "Fetch data" from the Simulations page.
 */
async function _handleFetchFromSimulations() {
  const btn = document.getElementById("btn-fetch-data-sim");
  if (btn) btn.disabled = true;
  App.showLoading();
  try {
    const result = await API.fetchData();
    App.showInfo("Data fetched: " + result.games_fetched + " games loaded.");
    const contentEl = document.getElementById("content");
    if (contentEl) await renderSimulations(contentEl);
  } catch (err) {
    App.showError(err.message || "Failed to fetch data.");
  } finally {
    App.hideLoading();
    if (btn) btn.disabled = false;
  }
}

/**
 * Render the Simulations view.
 *
 * @param {HTMLElement} contentEl - The main content container element.
 */
async function renderSimulations(contentEl) {
  App.showLoading();

  let status = null;
  try {
    status = await API.fetchStatus();
  } catch (_) {
    // Ignore status errors — the header card handles a missing/empty status.
  }

  App.hideLoading();

  const results = window._simulationResults;

  // Build the Simulations page — Modernist "Ledger" redesign (see
  // design_handoff_simulation_flow_v2/, Option 3a).
  let html = `<div class="mdn-page">`;
  html += _buildSimulationHeaderCard(status);

  // Results divider
  const rightNote = results
    ? `Select a team below for candidate details · Last run ${results._ranAt ? _escapeHtml(results._ranAt.toLocaleString()) : ""}`
    : `Run a simulation above to see results`;
  html += `<div style="display:flex;align-items:baseline;justify-content:space-between;margin:28px 0 2px">
    <span class="mdn-card-kicker" style="font-size:11px">Results</span>
    <span class="mdn-hint" style="font-size:11.5px">${rightNote}</span>
  </div>
  <div style="border-top:2px solid var(--mdn-divider);margin-bottom:18px"></div>`;

  if (results) {
    const showWarning = results.low_confidence || !results.convergence_achieved;
    if (showWarning) {
      html += `<p class="mdn-hint" style="color:var(--mdn-accent-700);margin:0 0 16px">${results.low_confidence ? "Low confidence." : ""}${results.convergence_achieved ? "" : " Convergence not achieved."}</p>`;
    }
    html += _renderPlayoffProbabilityTables(results.team_results);
    html += _renderSeedingMatrix(results.team_results);
    html += _renderTopScenarios(results.top_scenarios);
  } else {
    html += `<p class="mdn-hint" style="margin-bottom:28px">No simulation results yet — configure the controls above and click Simulate.</p>`;
  }

  html += `</div>`;

  // Team detail panel (hidden initially, shown on team click)
  html += `<div id="team-detail-panel" class="mdn-page" style="margin-top:2.5rem" hidden></div>`;

  contentEl.innerHTML = html;

  _wireSimulationHeaderCard(status);

  if (results) {
    // Attach click handlers for team names
    contentEl.querySelectorAll("[data-team-click]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        const teamName = el.getAttribute("data-team-click");
        _showTeamDetail(teamName, results);
      });
    });
  }
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
          <th style="width:220px">Playoff %${_infoIcon("Share of simulated seasons in which this team reaches the playoffs. Each trial plays out every remaining game using team strength plus noise, applies the NFL tiebreakers, then checks whether the team lands in the top 7 of its conference. 12,414 of 15,000 trials = 82.8%.")}</th>
          <th class="mdn-num">Strength${_infoIcon("Relative team rating derived from results so far. Higher values win more simulated games; 1.000 is league average.")}</th>
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
  const iterationsRun = results.iterations_run || (parseInt(localStorage.getItem("sim-iterations"), 10) || 10000);
  const pctVal = teamData.playoff_probability;
  const hits = Math.round((pctVal / 100) * iterationsRun);

  // Bordered/tinted container — marks this as a drill-in on an otherwise
  // white page (design_handoff_simulation_flow_v2/, Option 3a).
  let html = `<div style="border:2px solid var(--mdn-divider);border-left:3px solid var(--mdn-accent-500);padding:22px 24px;margin-bottom:28px;background:var(--mdn-neutral-100)">`;

  // Panel header
  html += `<div style="display:flex;align-items:center;gap:14px;margin-bottom:20px">
    ${logoId ? `<img src="img/logos/${logoId}.png" alt="" width="30" height="30">` : ""}
    <h2 style="font:800 24px var(--mdn-font-heading);margin:0">${_escapeHtml(teamName)} — Details</h2>
    <span class="mdn-card-kicker" style="font-size:10px;margin:0">Selected team</span>
    <button id="btn-close-team-detail" class="mdn-btn mdn-btn-ghost" type="button" style="margin-left:auto">Close ×</button>
  </div>`;

  // Stat row — a fixed label line-height keeps "Conference"/"Division"
  // (plain text) aligned with "Playoff Probability"/"Strength Rating"
  // (which carry a taller inline tooltip icon).
  html += `<div style="display:flex;gap:36px;flex-wrap:wrap;padding-bottom:20px;border-bottom:1px solid var(--mdn-divider);margin-bottom:22px">
    <div><div class="mdn-stat-lbl" style="height:13px;display:flex;align-items:center;gap:4px;margin-bottom:5px">Conference</div><div class="mdn-stat-val">${_escapeHtml(teamData.conference)}</div></div>
    <div><div class="mdn-stat-lbl" style="height:13px;display:flex;align-items:center;gap:4px;margin-bottom:5px">Division</div><div class="mdn-stat-val">${_escapeHtml(teamData.division)}</div></div>
    <div><div class="mdn-stat-lbl" style="height:13px;display:flex;align-items:center;gap:4px;margin-bottom:5px">Playoff Probability${_infoIcon(`Share of simulated seasons in which the ${teamName} reach the playoffs — remaining games are simulated from team strength plus noise, tiebreakers applied, then a top-7 conference finish counted. ${hits.toLocaleString()} of ${iterationsRun.toLocaleString()} trials = ${pctVal.toFixed(1)}%.`)}</div><div class="mdn-stat-val">${pctVal.toFixed(1)}%</div></div>
    <div><div class="mdn-stat-lbl" style="height:13px;display:flex;align-items:center;gap:4px;margin-bottom:5px">Strength Rating${_infoIcon("Relative team rating derived from results so far. Higher values win more simulated games; 1.000 is league average.")}</div><div class="mdn-stat-val">${teamData.strength_rating.toFixed(3)}</div></div>
  </div>`;

  // Seed distribution — 7-column grid of tinted blocks, not a table. Every
  // cell keeps a visible border so 0% cells (transparent fill) still read
  // as a cell, matching the Statistics page's bar-track convention.
  html += `<div class="mdn-div-lbl" style="margin-bottom:10px">Seed Distribution${_infoIcon(`How often the ${teamName} finish at each conference seed across all trials. Columns sum to the playoff probability; the remainder is seasons where they miss the playoffs.`)}</div>
  <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:26px">`;
  const seeds = teamData.seed_probabilities || {};
  for (let s = 1; s <= 7; s++) {
    const prob = seeds[String(s)] || 0;
    const { tint, hi } = _seedTint(prob);
    html += `<div>
      <div class="mdn-stat-lbl" style="text-align:right;margin-bottom:6px">Seed ${s}</div>
      <div style="height:34px;background:${tint};border:1px solid var(--mdn-neutral-400);display:flex;align-items:center;justify-content:flex-end;padding:0 10px;box-sizing:border-box">
        <span class="${hi ? "mdn-seed-hi" : ""}" style="font-weight:700;font-size:13px">${prob.toFixed(1)}%</span>
      </div>
    </div>`;
  }
  html += `</div>`;

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
    html += `<div id="clinch-section-${_escapeHtml(teamName)}">
      <div class="mdn-card-kicker">Clinching scenarios</div>
      <div class="mdn-card-title" style="font-size:17px;margin-bottom:6px">Clinching Scenarios</div>
      <p style="font-size:13px;opacity:0.65;margin:0 0 10px">
        Find all game-outcome combinations that guarantee ${_escapeHtml(teamName)} a playoff spot.
      </p>
      <p id="clinch-estimate-text" style="font-size:12.5px;margin:0 0 16px"></p>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px">
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
      <div class="mdn-field">
        <label for="clinch-enum-threshold">Enumerate up to <span id="clinch-enum-label" style="font-weight:400">9 games</span></label>
        <div style="display:flex;align-items:center;gap:18px;flex-wrap:wrap">
          <input class="mdn-input" type="range" id="clinch-enum-threshold" min="1" max="14" value="9" style="width:220px">
          <span id="clinch-enum-info" style="font-size:12.5px;color:rgba(32,30,29,.65)"></span>
        </div>
      </div>
      <p class="mdn-hint" id="clinch-settings-hint" style="margin:10px 0 0">Worker count follows the Simulation settings above.</p>
      <p id="clinch-mode-explanation" style="font-size:11.5px;opacity:.6;margin-top:20px;padding-top:16px;border-top:1px solid var(--mdn-divider);line-height:1.7">
        <strong>Enumeration</strong> — checks every possible outcome combination (exhaustive, proven results).<br>
        <strong>Sampling</strong> — tests strength-weighted random outcomes (faster, but may miss rare scenarios).<br>
        <strong>Export Performance Data</strong> — writes solver timing measurements to <code>doc/solver-performance.md</code> for cross-platform comparison. One row per method, using the median of the last 50 runs.<br>
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

  html += `</div>`; // close bordered/tinted container

  panel.innerHTML = html;
  panel.hidden = false;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });

  const closeBtn = document.getElementById("btn-close-team-detail");
  if (closeBtn) closeBtn.addEventListener("click", () => { panel.hidden = true; });

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
    // Falls back to the server's detected core count (filled in from
    // est.cpu_count below) rather than a hardcoded guess — with num_workers
    // unset the server itself uses os.cpu_count(), so that is the count the
    // run will actually get.
    let serverCpuCount = parseInt(localStorage.getItem("sim-workers"), 10) || null;

    // The solver reuses the main Simulation page's Iterations, Noise, and
    // Workers values — there is no separate solver-only sampling/noise/
    // worker setting.
    function sharedIterations() {
      return parseInt(localStorage.getItem("sim-iterations"), 10) || 10000;
    }
    function sharedNoise() {
      return (parseInt(localStorage.getItem("sim-noise"), 10) || 34) / 100;
    }
    function sharedTieProbability() {
      const stored = localStorage.getItem("sim-tie-probability");
      return stored != null ? parseInt(stored, 10) / 10000 : null;
    }

    function updateEnumLabel() {
      const val = parseInt(enumSlider.value, 10);
      enumLabel.textContent = val + " games";
      const coresLabel = serverCpuCount === 1 ? "1 core" : serverCpuCount + " cores";
      const noiseLabel = sharedNoise().toFixed(2) + " noise";
      const tieProbLabel = ((sharedTieProbability() != null ? sharedTieProbability() : 0.005) * 100).toFixed(2) + "% tie";
      const settingsHint = document.getElementById("clinch-settings-hint");
      if (relevantGames > 0) {
        if (relevantGames <= val) {
          const combos = Math.pow(3, relevantGames) * teamRecordCombos;
          const estLow = Math.max(1, Math.round((combos * msPerEval * 8 / 1000) / serverCpuCount));
          const estHigh = Math.max(estLow + 1, Math.round((combos * msPerEval * 15 / 1000) / serverCpuCount));
          enumInfo.textContent = "→ enumeration · " + combos.toLocaleString() + " evaluations · " + coresLabel + " · " + _formatTime(estLow) + " – " + _formatTime(estHigh);
          // Enumeration exhaustively tries all 3 outcomes per game with no
          // probability weighting — noise and tie probability have no effect
          // on it (same reason they're absent from the line above).
          if (settingsHint) settingsHint.textContent = "Enumeration tries every outcome exhaustively — Noise and Tie Probability don't apply. Worker count follows the Simulation settings above.";
        } else {
          const samplingIters = sharedIterations();
          const samplingEvals = samplingIters * teamRecordCombos;
          const estLow = Math.max(1, Math.round((samplingEvals * msPerEval * 8 / 1000) / serverCpuCount));
          const estHigh = Math.max(estLow + 1, Math.round((samplingEvals * msPerEval * 15 / 1000) / serverCpuCount));
          enumInfo.textContent = "→ sampling · " + samplingIters.toLocaleString() + " trials × " + teamRecordCombos + " records · " + noiseLabel + " · " + tieProbLabel + " · " + coresLabel + " · " + _formatTime(estLow) + " – " + _formatTime(estHigh);
          if (settingsHint) settingsHint.textContent = "Trials, Noise, Tie Probability, and worker count follow the Simulation settings above.";
        }
      }
    }
    function _formatTime(sec) {
      if (sec < 60) return sec + "s";
      return Math.floor(sec / 60) + "m " + (sec % 60) + "s";
    }
    // Restore from localStorage
    const savedThreshold = localStorage.getItem("clinch-enum-threshold");
    if (savedThreshold && enumSlider) enumSlider.value = savedThreshold;
    if (enumSlider) {
      enumSlider.addEventListener("input", () => {
        localStorage.setItem("clinch-enum-threshold", enumSlider.value);
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
        estEl.textContent = est.reason || "Not available";
      } else {
        relevantGames = est.relevant_games;
        teamRecordCombos = est.team_record_combos || 1;
        msPerEval = est.ms_per_eval || 2.0;
        // serverCpuCount stays pinned to the shared Workers value (sim-workers)
        // when the user has one — est.cpu_count is the server's total detected
        // core count, not the worker count sent to the solver. But when that
        // setting is unset we send num_workers: null, and the server then falls
        // back to os.cpu_count() itself — so est.cpu_count *is* the count the
        // run will get, and it's the honest number to label and estimate with.
        if (serverCpuCount == null) serverCpuCount = est.cpu_count || 1;
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
        const numSamples = sharedIterations();
        const numWorkers = parseInt(localStorage.getItem("sim-workers"), 10) || null;
        const body = { team: teamName, noise: sharedNoise() };
        if (cutoffWeek != null) body.cutoff_week = cutoffWeek;
        if (enumThreshold != null) body.enumeration_threshold = enumThreshold;
        if (numSamples != null) body.num_samples = numSamples;
        if (numWorkers != null) body.num_workers = numWorkers;
        const tieProbability = sharedTieProbability();
        if (tieProbability != null) body.tie_probability = tieProbability;
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
