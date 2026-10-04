/**
 * Export view for the NFL Playoff Rankings Monte Carlo Simulator.
 *
 * Offers two backend-generated exports of the current season state:
 * - a single standalone HTML page (Standings, Statistics, Schedule Grid,
 *   and Simulation if available), and
 * - a ZIP bundle (index + one page per section + one page per team, every
 *   team name linked).
 *
 * It also offers a client-rendered teaser PNG (teaser.js) that compares the
 * last simulation run against the season's saved baseline.
 *
 * The last completed simulation result — if any — lives in
 * window._simulationResults (set by simulation.js once a run finishes; see
 * app.js's setCutoffWeek, which clears it when the cutoff changes). Since
 * results only live in server memory for a few minutes per job with no
 * lookup by cutoff, this view forwards that already-fetched result directly
 * to the export endpoints rather than asking the server to look one up.
 */

"use strict";

/**
 * Render the export view.
 *
 * @param {HTMLElement} contentEl - The main content container.
 */
async function renderExport(contentEl) {
  const hasSimulation = !!window._simulationResults;
  const simNote = hasSimulation
    ? `Includes your last simulation run (cutoff week ${window._simulationResults.cutoff_week_used}, ${window._simulationResults.iterations_run} iterations).`
    : `No simulation results available yet — the Simulation section will be omitted from both exports. <a href="#simulations">Run one on Simulations</a> first if you want it included.`;

  let baselineInfo;
  try {
    const { baseline } = await API.getTeaserBaseline();
    baselineInfo = _describeTeaserBaseline(baseline);
  } catch (err) {
    baselineInfo = { text: `Could not load the saved baseline: ${err.message}`, saved: false };
  }

  contentEl.innerHTML = `
    <div class="mdn-page">
      <h1 style="font:800 34px var(--mdn-font-heading);margin:0 0 6px">Export</h1>
      <p class="mdn-hint" style="margin:0 0 20px">
        Save the current Standings, Statistics, and Schedule Grid as standalone HTML.
      </p>
      <p>${simNote}</p>
      <div class="mdn-card" style="margin:20px 0">
        <h3>Single page</h3>
        <p>One self-contained HTML file with everything on it. Team names are plain text — no per-team pages, to keep the file manageable.</p>
        <button type="button" class="mdn-btn mdn-btn-primary" id="export-page-btn">Export standalone page</button>
        <span id="export-page-status" class="mdn-hint"></span>
      </div>
      <div class="mdn-card">
        <h3>Site bundle</h3>
        <p>A ZIP with an index page, one page per section, and one page per team — every team name links to its own page.</p>
        <button type="button" class="mdn-btn mdn-btn-primary" id="export-bundle-btn">Export site bundle (.zip)</button>
        <span id="export-bundle-status" class="mdn-hint"></span>
      </div>
      <div class="mdn-card" style="margin:20px 0">
        <h3>Teaser image</h3>
        <p>A 1200×630 "Biggest movers" card for link previews: the five teams whose playoff probability changed most since the saved baseline. Download compares your last simulation run against the baseline; once you have published this run, save it as the baseline so next week's teaser compares against it.</p>
        <p id="teaser-baseline-info" class="mdn-hint"></p>
        <button type="button" class="mdn-btn mdn-btn-primary" id="teaser-download-btn" ${hasSimulation && baselineInfo.saved ? "" : "disabled"}>Download teaser (.png)</button>
        <button type="button" class="mdn-btn mdn-btn-secondary" id="teaser-save-btn" ${hasSimulation ? "" : "disabled"}>Save as baseline</button>
        <span id="teaser-status" class="mdn-hint"></span>
      </div>
    </div>
  `;

  document.getElementById("export-page-btn").addEventListener("click", () => _runExport("page"));
  document.getElementById("export-bundle-btn").addEventListener("click", () => _runExport("bundle"));
  document.getElementById("teaser-baseline-info").textContent = baselineInfo.text;
  document.getElementById("teaser-download-btn").addEventListener("click", _downloadTeaser);
  document.getElementById("teaser-save-btn").addEventListener("click", _saveTeaserBaseline);
}

/**
 * Describe the saved teaser baseline for the Export page, as HTML text.
 *
 * @param {{cutoff_week: number, saved_at: string}|null} baseline
 * @returns {{text: string, saved: boolean}}
 */
function _describeTeaserBaseline(baseline) {
  if (!baseline) {
    return {
      text: "No baseline saved yet for this season.",
      saved: false,
    };
  }
  const savedAt = new Date(baseline.saved_at).toLocaleString();
  return {
    text: `Baseline: cutoff week ${baseline.cutoff_week}, saved ${savedAt}.`,
    saved: true,
  };
}

/**
 * Build the teaser's movers from the last simulation run and the saved
 * baseline, render the card, and download it as a PNG.
 */
async function _downloadTeaser() {
  const statusEl = document.getElementById("teaser-status");
  const sim = window._simulationResults;
  if (!sim) {
    App.showError("Run a simulation first.");
    return;
  }

  if (statusEl) statusEl.textContent = " Generating…";
  try {
    const { baseline } = await API.getTeaserBaseline();
    if (!baseline) {
      App.showError("Save a baseline first, then download the teaser.");
      return;
    }

    const current = {};
    for (const entry of sim.team_results) {
      current[entry.team] = entry.playoff_probability;
    }
    const movers = computeMovers(current, baseline.probabilities);
    let version;
    try {
      version = (await API.fetchStatus()).version;
    } catch (_err) {
      // Version is optional on the card; omit it if the status call fails.
    }
    const blob = await buildTeaserBlob(movers, {
      season: baseline.season,
      cutoffWeek: sim.cutoff_week_used,
      baselineWeek: baseline.cutoff_week,
      version,
    });

    const filename = `nfl-playoff-rankings-mc-sim-teaser-${baseline.season}-week${sim.cutoff_week_used}.png`;
    _downloadBlob(blob, filename);
  } catch (err) {
    App.showError(err.message || "Teaser generation failed.");
  } finally {
    if (statusEl) statusEl.textContent = "";
  }
}

/**
 * Save the last simulation run's playoff probabilities as the season's
 * teaser baseline, replacing any earlier one.
 */
async function _saveTeaserBaseline() {
  const statusEl = document.getElementById("teaser-status");
  const sim = window._simulationResults;
  if (!sim) {
    App.showError("Run a simulation first.");
    return;
  }

  if (statusEl) statusEl.textContent = " Saving…";
  try {
    const { baseline } = await API.saveTeaserBaseline(sim);
    const infoEl = document.getElementById("teaser-baseline-info");
    if (infoEl) infoEl.textContent = _describeTeaserBaseline(baseline).text;
    const downloadBtn = document.getElementById("teaser-download-btn");
    if (downloadBtn) downloadBtn.disabled = false;
    App.showInfo(`Baseline saved at cutoff week ${baseline.cutoff_week}.`);
  } catch (err) {
    App.showError(err.message || "Could not save the baseline.");
  } finally {
    if (statusEl) statusEl.textContent = "";
  }
}

/**
 * Build the shared export request payload: the last simulation result (if
 * any) and the app's currently-selected cutoff week, so the exported
 * standings match what the Standings page currently displays.
 *
 * @returns {{simulation_result: Object|null, cutoff_week?: number}}
 */
function _buildExportPayload() {
  const payload = { simulation_result: window._simulationResults || null };
  const cutoffWeek = App.getCutoffWeek();
  if (cutoffWeek) {
    const parsed = parseInt(cutoffWeek, 10);
    if (!Number.isNaN(parsed)) {
      payload.cutoff_week = parsed;
    }
  }
  return payload;
}

/**
 * Trigger one export, download the result, and report status/errors inline
 * next to the button that was clicked.
 *
 * @param {"page"|"bundle"} kind
 */
async function _runExport(kind) {
  const statusEl = document.getElementById(`export-${kind}-status`);
  if (statusEl) statusEl.textContent = " Generating…";

  const seasonSelector = document.getElementById("season-selector");
  const season = seasonSelector ? seasonSelector.value : "export";
  const payload = _buildExportPayload();

  try {
    const blob = kind === "page"
      ? await API.exportPage(payload)
      : await API.exportBundle(payload);
    const filename = `nfl-playoff-rankings-mc-sim-export-${season}.${kind === "page" ? "html" : "zip"}`;
    _downloadBlob(blob, filename);
    if (statusEl) statusEl.textContent = "";
  } catch (err) {
    if (statusEl) statusEl.textContent = "";
    App.showError(err.message || "Export failed.");
  }
}

/**
 * Trigger a browser download of a Blob via a temporary anchor element.
 *
 * @param {Blob} blob
 * @param {string} filename
 */
function _downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
