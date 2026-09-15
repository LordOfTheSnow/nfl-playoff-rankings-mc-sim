/**
 * Export view for the NFL Monte Carlo Playoff Simulator.
 *
 * Offers two backend-generated exports of the current season state:
 * - a single standalone HTML page (Standings, Statistics, Schedule Grid,
 *   and Simulation if available), and
 * - a ZIP bundle (index + one page per section + one page per team, every
 *   team name linked).
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
    </div>
  `;

  document.getElementById("export-page-btn").addEventListener("click", () => _runExport("page"));
  document.getElementById("export-bundle-btn").addEventListener("click", () => _runExport("bundle"));
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
    const filename = kind === "page" ? `nfl-export-${season}.html` : `nfl-export-${season}.zip`;
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
