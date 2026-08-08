/**
 * Settings / Info view rendering for the NFL Monte Carlo Playoff Simulator.
 *
 * Read-only diagnostics page (Modernist system): SQLite cache metadata
 * (which seasons are stored, how complete each one is, and recent ESPN
 * fetch attempts including failures), the server's runtime environment
 * (CPU, Python, platform), and lifetime run counters (total games
 * simulated / clinching resolver evaluations), sourced from
 * GET /api/system-info.
 */

"use strict";

/**
 * Render the Settings / Info view into the given container element.
 *
 * @param {HTMLElement} contentEl - The main content container to render into.
 */
async function renderSettings(contentEl) {
  App.showLoading();

  let data = null;
  let error = null;
  try {
    data = await API.getSystemInfo();
  } catch (err) {
    error = err;
  }

  App.hideLoading();

  contentEl.innerHTML = "";
  const root = document.createElement("div");
  root.className = "mdn-page";
  contentEl.appendChild(root);

  const heading = document.createElement("h1");
  heading.textContent = "Settings / Info";
  root.appendChild(heading);

  if (!data) {
    const empty = document.createElement("div");
    empty.className = "mdn-card";
    empty.innerHTML = "<p>Unable to load system info.</p>";
    root.appendChild(empty);
    App.showError((error && error.message) || "Failed to load system info.");
    return;
  }

  root.appendChild(_buildRuntimeCard(data));
  root.appendChild(_buildCountersCard(data));
  root.appendChild(_buildDatabaseCard(data));
  root.appendChild(_buildFetchLogCard(data));
}

/**
 * Build the runtime environment card (server version, CPU, Python, platform).
 *
 * @param {Object} data - The /api/system-info response.
 * @returns {HTMLElement}
 */
function _buildRuntimeCard(data) {
  const runtime = data.runtime || {};
  const card = document.createElement("div");
  card.className = "mdn-card";
  card.style.marginTop = "22px";

  let html = '<div class="mdn-card-kicker">Runtime environment</div>';
  html += '<div class="mdn-card-title">Server v' + _escapeHtml(data.version || "unknown") + "</div>";
  html += '<div style="display:flex;gap:28px;margin-top:12px;flex-wrap:wrap">';
  html += _statBlock("CPU model", runtime.cpu_model || "Unknown");
  html += _statBlock("CPU cores", runtime.cpu_cores != null ? String(runtime.cpu_cores) : "Unknown");
  html += _statBlock("Python", runtime.python_version || "Unknown");
  html += _statBlock("Platform", runtime.platform || "Unknown");
  html += _statBlock("Simulation workers", runtime.simulation_mp_method || "Unknown");
  html += _statBlock("Clinching resolver workers", runtime.clinching_resolver_mp_method || "Unknown");
  html += "</div>";
  html += '<p class="mdn-hint" style="margin-top:10px">Simulation uses a fixed worker start method (fork on Unix, spawn on Windows); the clinching resolver uses Python\'s platform-default method, which can differ by Python version.</p>';

  card.innerHTML = html;
  return card;
}

/**
 * Build the lifetime run counters card (total games simulated by Monte
 * Carlo runs, and clinching resolver evaluations performed, ever).
 *
 * @param {Object} data - The /api/system-info response.
 * @returns {HTMLElement}
 */
function _buildCountersCard(data) {
  const counters = data.lifetime_counters || {};
  const card = document.createElement("div");
  card.className = "mdn-card";
  card.style.marginTop = "22px";

  let html = '<div class="mdn-card-kicker">Lifetime totals</div>';
  html += '<div class="mdn-card-title">Simulation &amp; resolver activity</div>';
  html += '<div style="display:flex;gap:28px;margin-top:12px;flex-wrap:wrap">';
  html += _statBlock("Games simulated", _formatCount(counters.games_simulated_total));
  html += _statBlock("Clinching resolver evaluations", _formatCount(counters.clinching_resolver_evals_total));
  html += "</div>";
  html += '<p class="mdn-hint" style="margin-top:10px">Games simulated sums every individual game outcome rolled across every Monte Carlo simulation run (iterations &times; remaining games per run) on this database.<br>Clinching resolver evaluations sum the game-outcome universes evaluated by every clinching scenarios run.</p>';

  card.innerHTML = html;
  return card;
}

/**
 * Build the database card: file metadata plus a per-season completeness table.
 *
 * @param {Object} data - The /api/system-info response.
 * @returns {HTMLElement}
 */
function _buildDatabaseCard(data) {
  const db = data.database || {};
  const seasons = db.seasons || [];
  const expectedTotal = db.expected_games_per_season || 272;

  const card = document.createElement("div");
  card.className = "mdn-card";
  card.style.marginTop = "22px";

  let html = '<div class="mdn-card-kicker">SQLite cache database</div>';
  html += '<div class="mdn-card-title">' + _escapeHtml(db.path || "unknown") + "</div>";
  html += '<div style="display:flex;gap:28px;margin-top:12px;flex-wrap:wrap">';
  html += _statBlock("File size", _formatBytes(db.size_bytes));
  html += _statBlock("Seasons stored", String(seasons.length));
  html += "</div>";

  if (seasons.length === 0) {
    html += '<p class="mdn-hint" style="margin-top:14px">No season data cached yet. Fetch data from Standings first.</p>';
    card.innerHTML = html;
    return card;
  }

  html += '<table class="mdn-led-table" style="margin-top:18px">';
  html += "<thead><tr>" +
    "<th>Season</th>" +
    '<th class="mdn-num">Games loaded</th>' +
    '<th class="mdn-num">Games completed</th>' +
    '<th class="mdn-num">Weeks with data</th>' +
    '<th class="mdn-num">Completion</th>' +
    "<th>Last fetched</th>" +
    "</tr></thead><tbody>";

  seasons.forEach(function (season) {
    const pct = expectedTotal > 0
      ? Math.round(((season.completed_games || 0) / expectedTotal) * 100)
      : 0;
    const lastFetched = season.last_fetch_time
      ? new Date(season.last_fetch_time).toLocaleString()
      : "—";
    html += "<tr>" +
      "<td>" + season.year + "</td>" +
      '<td class="mdn-num">' + season.games_cached + " / " + expectedTotal + "</td>" +
      '<td class="mdn-num">' + season.completed_games + " / " + expectedTotal + "</td>" +
      '<td class="mdn-num">' + season.weeks_with_data + " / 18</td>" +
      '<td class="mdn-num">' + pct + "%</td>" +
      "<td>" + _escapeHtml(lastFetched) + "</td>" +
      "</tr>";
  });

  html += "</tbody></table>";
  card.innerHTML = html;
  return card;
}

/**
 * Build the recent fetch attempts card: the most recent ESPN fetch
 * attempts per week, flagging failures.
 *
 * @param {Object} data - The /api/system-info response.
 * @returns {HTMLElement}
 */
function _buildFetchLogCard(data) {
  const db = data.database || {};
  const attempts = db.recent_fetches || [];

  const card = document.createElement("div");
  card.className = "mdn-card";
  card.style.marginTop = "22px";

  let html = '<div class="mdn-card-kicker">Recent fetch attempts</div>';
  html += '<div class="mdn-card-title">Latest ' + attempts.length + " ESPN fetch(es)</div>";

  if (attempts.length === 0) {
    html += '<p class="mdn-hint" style="margin-top:14px">No fetch attempts recorded yet.</p>';
    card.innerHTML = html;
    return card;
  }

  html += '<table class="mdn-led-table" style="margin-top:18px">';
  html += "<thead><tr>" +
    "<th>Season</th>" +
    "<th>Week</th>" +
    "<th>Status</th>" +
    '<th class="mdn-num">Games</th>' +
    "<th>Fetched at</th>" +
    "</tr></thead><tbody>";

  attempts.forEach(function (attempt) {
    const fetchedAt = attempt.fetched_at
      ? new Date(attempt.fetched_at).toLocaleString()
      : "—";
    const statusTag = attempt.success
      ? '<span class="mdn-tag mdn-tag-outline">OK</span>'
      : '<span class="mdn-tag mdn-tag-accent">FAILED</span>';
    html += "<tr>" +
      "<td>" + attempt.year + "</td>" +
      "<td>" + attempt.week + "</td>" +
      "<td>" + statusTag + "</td>" +
      '<td class="mdn-num">' + attempt.games_count + "</td>" +
      "<td>" + _escapeHtml(fetchedAt) + "</td>" +
      "</tr>";
  });

  html += "</tbody></table>";
  card.innerHTML = html;
  return card;
}

/**
 * Build a labeled stat block (`.mdn-stat-lbl` / `.mdn-stat-val` pair) as an HTML string.
 *
 * @param {string} label
 * @param {string} value
 * @returns {string}
 */
function _statBlock(label, value) {
  return '<div><div class="mdn-stat-lbl">' + _escapeHtml(label) +
    '</div><div class="mdn-stat-val">' + _escapeHtml(value) + "</div></div>";
}

/**
 * Format an integer count with thousands separators (e.g. 1234567 -> "1,234,567").
 *
 * @param {number|null|undefined} count
 * @returns {string}
 */
function _formatCount(count) {
  if (count == null) return "0";
  return Number(count).toLocaleString("en-US");
}

/**
 * Format a byte count as a human-readable string (e.g. "2.3 MB").
 *
 * @param {number|null|undefined} bytes
 * @returns {string}
 */
function _formatBytes(bytes) {
  if (bytes == null) return "Unknown";
  if (bytes < 1024) return bytes + " B";
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return value.toFixed(1) + " " + units[unitIndex];
}

