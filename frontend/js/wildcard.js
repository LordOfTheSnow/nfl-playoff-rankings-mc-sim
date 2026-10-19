/**
 * Wild Card Round view for the NFL Playoff Rankings Monte Carlo Simulator.
 *
 * Shows the top-7-seeds-per-conference Wild Card matchups (2v7, 3v6, 4v5),
 * the #1 seed's first-round bye, and an "In the Hunt" list of teams below
 * seed 7 that can still make it — from either Actual standings (real
 * results through the shared cutoff week) or Simulated seeding (the most
 * likely bracket from the last Monte Carlo run). See
 * design_handoff_wildcard/README.md for the full screen spec.
 *
 * All seed/record/strength/last5/streak/eliminated/playoff% data comes
 * pre-assembled from POST /api/wildcard (src/wildcard.py) — this view only
 * derives presentation groupings (bye/matchups/hunt) from the seed order.
 */

"use strict";

/**
 * ESPN team logo ID mapping (duplicated per-view, matching the existing
 * convention in standings.js/simulation.js/export.py).
 */
const WC_TEAM_LOGO_IDS = {
  "Bills": "buf", "Dolphins": "mia", "Patriots": "ne", "Jets": "nyj",
  "Ravens": "bal", "Bengals": "cin", "Browns": "cle", "Steelers": "pit",
  "Texans": "hou", "Colts": "ind", "Jaguars": "jax", "Titans": "ten",
  "Chiefs": "kc", "Broncos": "den", "Chargers": "lac", "Raiders": "lv",
  "Cowboys": "dal", "Eagles": "phi", "Giants": "nyg", "Commanders": "wsh",
  "Bears": "chi", "Lions": "det", "Packers": "gb", "Vikings": "min",
  "Falcons": "atl", "Panthers": "car", "Saints": "no", "Buccaneers": "tb",
  "Cardinals": "ari", "Rams": "lar", "49ers": "sf", "Seahawks": "sea",
};

/**
 * This session's selected data source, remembered across re-renders of this
 * view (e.g. a segment click) but not persisted — null means "not chosen
 * yet", so the next render falls back to the doc's default (Simulated if a
 * run exists, else Actual).
 * @type {"actual"|"simulated"|null}
 */
let _wcSelectedSource = null;

/**
 * Render the Wild Card view into the given container element.
 *
 * @param {HTMLElement} contentEl - The main content container.
 */
async function renderWildcard(contentEl) {
  if (_wcSelectedSource === null) {
    _wcSelectedSource = window._simulationResults ? "simulated" : "actual";
  }
  App.showLoading();
  try {
    await _loadAndRenderWildcard(contentEl, _wcSelectedSource);
  } finally {
    App.hideLoading();
  }
}

/**
 * Fetch Wild Card data for the given source (or skip the fetch for an
 * unavailable Simulated run) and render the whole page.
 *
 * @param {HTMLElement} contentEl
 * @param {"actual"|"simulated"} source
 */
async function _loadAndRenderWildcard(contentEl, source) {
  if (source === "simulated" && !window._simulationResults) {
    contentEl.innerHTML = _buildPageHtml(source, null);
    _wireSegment(contentEl, source);
    return;
  }

  let data = null;
  let errorMessage = null;
  try {
    const payload = { source };
    if (source === "simulated") {
      payload.simulation_result = window._simulationResults;
    } else {
      const cutoffRaw = App.getCutoffWeek();
      const cutoffWeek = cutoffRaw ? parseInt(cutoffRaw, 10) : NaN;
      if (!Number.isNaN(cutoffWeek)) payload.cutoff_week = cutoffWeek;
    }
    data = await API.postWildcard(payload);
  } catch (err) {
    errorMessage = err.message || "Failed to load Wild Card data.";
  }

  contentEl.innerHTML = _buildPageHtml(source, data, errorMessage);
  _wireSegment(contentEl, source);
  if (data) _wireTeamLinks(contentEl);
}

/**
 * Switch to a new data source and re-render, without a full page reload.
 *
 * @param {HTMLElement} contentEl
 * @param {"actual"|"simulated"} source
 */
function _switchSource(contentEl, source) {
  _wcSelectedSource = source;
  App.showLoading();
  _loadAndRenderWildcard(contentEl, source).finally(App.hideLoading);
}

/**
 * Wire up the "Data source" segmented control's click handlers.
 *
 * @param {HTMLElement} contentEl
 * @param {"actual"|"simulated"} activeSource
 */
function _wireSegment(contentEl, activeSource) {
  const seg = contentEl.querySelector("[data-wc-source-seg]");
  if (!seg) return;
  seg.querySelectorAll("[data-source]").forEach((opt) => {
    opt.addEventListener("click", () => {
      const source = opt.getAttribute("data-source");
      if (source !== activeSource) _switchSource(contentEl, source);
    });
  });
}

/**
 * Wire up click-to-navigate on every team name link in the rendered page.
 *
 * @param {HTMLElement} contentEl
 */
function _wireTeamLinks(contentEl) {
  contentEl.querySelectorAll("[data-wc-team-link]").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      App.navigate("team/" + encodeURIComponent(link.getAttribute("data-wc-team-link")));
    });
  });
}

/**
 * Build the whole page's HTML: summary card, conference grid (or empty
 * state), and footnote.
 *
 * @param {"actual"|"simulated"} source
 * @param {Object|null} data - Response from POST /api/wildcard, or null
 *   if unavailable (no run yet, or the request failed).
 * @param {string|null} [errorMessage]
 * @returns {string}
 */
function _buildPageHtml(source, data, errorMessage) {
  let html = '<div class="mdn-page">';
  html += _buildSummaryCardHtml(source, data);

  if (errorMessage) {
    html += `<p class="mdn-hint" style="color:var(--mdn-accent-700)">${_escapeHtml(errorMessage)}</p>`;
  } else if (!data) {
    html += _buildEmptyStateHtml();
  } else {
    html += '<div class="mdn-wc-grid">';
    html += _buildConferenceHtml("AFC", data.conferences.AFC, source);
    html += _buildConferenceHtml("NFC", data.conferences.NFC, source);
    html += "</div>";
    html +=
      '<p class="mdn-hint" style="margin-top:24px;font-size:11.5px">' +
      "Last 5 reads left to right, oldest to most recent — the → marks the flow of time toward the most " +
      "recent game. Example: L-W-W-L-W means the team lost, then won, won, lost, and most recently won.</p>";
  }

  html += "</div>";
  return html;
}

/**
 * Build the top summary card: left column (kicker/tag/title/stats/note),
 * right column (Data source segment + note).
 *
 * @param {"actual"|"simulated"} source
 * @param {Object|null} data
 * @returns {string}
 */
function _buildSummaryCardHtml(source, data) {
  const isSimulated = source === "simulated";
  const tag = isSimulated
    ? '<span class="mdn-tag mdn-tag-accent" style="font-size:9px;margin-left:8px">SIMULATED</span>'
    : '<span class="mdn-tag mdn-tag-neutral" style="font-size:9px;margin-left:8px">ACTUAL STANDINGS</span>';

  const cutoffWeek = data ? data.cutoff_week : null;
  const title = isSimulated
    ? "Projected Seeding & Matchups"
    : `Seeding & Matchups Through Week ${cutoffWeek != null ? cutoffWeek : "—"}`;

  const note = isSimulated
    ? "Seeds and strength ratings come from the Monte Carlo run — this is the single most likely seeding, " +
      "not a certainty. Matchup win probabilities aren't modeled yet, so match cards show each side's rating only."
    : "Seeds reflect real results through the cutoff week. If the regular season isn't finished, seeds 7–8 " +
      "and matchups here can still change.";

  let statsHtml =
    '<div><div class="mdn-stat-lbl">Cutoff</div><div class="mdn-stat-val">' +
    (cutoffWeek != null ? `Week ${cutoffWeek}` : "—") +
    "</div></div>";
  if (isSimulated) {
    const iterations = data && data.iterations != null ? data.iterations.toLocaleString() : "—";
    statsHtml +=
      '<div><div class="mdn-stat-lbl">Iterations</div><div class="mdn-stat-val">' + iterations + "</div></div>";
  }

  return `
    <div class="mdn-card" style="display:grid;grid-template-columns:1fr 1fr;gap:32px">
      <div>
        <div class="mdn-card-kicker">Wild Card Round${tag}</div>
        <div class="mdn-card-title">${_escapeHtml(title)}</div>
        <div style="display:flex;gap:24px;margin-top:12px">${statsHtml}</div>
        <p class="mdn-hint" style="margin-top:10px">${note}</p>
      </div>
      <div>
        <div class="mdn-card-kicker">Data source</div>
        <div class="mdn-seg" data-wc-source-seg>
          <span class="mdn-seg-opt${source === "actual" ? " active" : ""}" data-source="actual">Actual standings</span>
          <span class="mdn-seg-opt${source === "simulated" ? " active" : ""}" data-source="simulated">Simulated seeding</span>
        </div>
        <p class="mdn-hint" style="margin-top:10px">
          Actual uses real results through the cutoff week; Simulated uses the most likely seeding from the
          Monte Carlo run.
        </p>
      </div>
    </div>
  `;
}

/** Empty state shown in Simulated mode when no run is available yet. */
function _buildEmptyStateHtml() {
  return (
    '<div class="mdn-card" style="text-align:center;padding:40px 24px">' +
    '<p class="mdn-hint" style="font-size:14px">Run a simulation to see projected seeding.</p>' +
    '<a href="#simulations" class="mdn-btn mdn-btn-primary" style="text-decoration:none;margin-top:10px;display:inline-block">' +
    "Go to Simulations →</a></div>"
  );
}

/**
 * Build one conference's column: head, bye row, 3 match cards, hunt panel.
 *
 * @param {"AFC"|"NFC"} conference
 * @param {Object[]} teams - All 16 teams for this conference, sorted by seed.
 * @param {"actual"|"simulated"} source
 * @returns {string}
 */
function _buildConferenceHtml(conference, teams, source) {
  const bySeed = {};
  for (const t of teams) bySeed[t.seed] = t;

  const bye = bySeed[1];
  const matchups = [[2, 7], [3, 6], [4, 5]];
  const hunt = teams
    .filter((t) => t.seed >= 8)
    .filter((t) => (source === "simulated" ? (t.playoff_pct || 0) > 0 : !t.eliminated));

  let html = `<div><div class="mdn-conf-head"><img src="img/logos/${conference.toLowerCase()}.png" width="26" height="26" alt="${conference} logo"><h2>${conference}</h2></div>`;

  if (bye) {
    html += _buildByeRowHtml(bye);
  }

  for (const [homeSeed, awaySeed] of matchups) {
    html += _buildMatchCardHtml(homeSeed, awaySeed, bySeed[homeSeed], bySeed[awaySeed]);
  }

  html += _buildHuntPanelHtml(hunt, source);
  html += "</div>";
  return html;
}

function _buildByeRowHtml(team) {
  return (
    '<div class="mdn-wc-bye">' +
    _teamIdentityHtml(team, 26) +
    '<span class="mdn-hint" style="margin-left:10px">First-round bye</span>' +
    _statStackHtml(team) +
    "</div>"
  );
}

/**
 * Build one "N vs M" match card, highlighting the higher-strength team as
 * favorite (ties go to the higher seed, i.e. the lower seed number).
 */
function _buildMatchCardHtml(homeSeed, awaySeed, homeTeam, awayTeam) {
  if (!homeTeam || !awayTeam) return "";
  const homeFav = (homeTeam.strength || 0) >= (awayTeam.strength || 0);
  return (
    '<div class="mdn-wc-match">' +
    `<div class="mdn-wc-match-head">${homeSeed} vs ${awaySeed}</div>` +
    _buildTeamRowHtml(homeTeam, homeFav) +
    _buildTeamRowHtml(awayTeam, !homeFav) +
    "</div>"
  );
}

function _buildTeamRowHtml(team, isFavorite) {
  return (
    `<div class="mdn-wc-team${isFavorite ? " fav" : ""}">` +
    _teamIdentityHtml(team, 22) +
    _statStackHtml(team) +
    "</div>"
  );
}

/** Seed number + logo + name + inline record/division, shared by every row kind. */
function _teamIdentityHtml(team, logoSize) {
  const logoId = WC_TEAM_LOGO_IDS[team.team];
  const logoHtml = logoId
    ? `<img src="img/logos/${logoId}.png" width="${logoSize}" height="${logoSize}" alt="">`
    : "";
  return (
    `<span class="mdn-wc-seed">${team.seed}</span>` +
    logoHtml +
    `<a href="#team/${encodeURIComponent(team.team)}" class="mdn-team-link" data-wc-team-link="${_escapeHtml(team.team)}" style="margin-left:4px">${_escapeHtml(team.team)}</a>` +
    `<span class="mdn-wc-sub">${_escapeHtml(team.record || "0-0-0")} · ${_escapeHtml(team.division || "")}</span>`
  );
}

/** Last 5 / Streak / Strength stat stack (bracket + bye rows). */
function _statStackHtml(team) {
  const last5 = team.last5 && team.last5.length ? "→ " + team.last5.join("-") : "—";
  const streak = team.streak ? team.streak.result + team.streak.length : "—";
  const strength = team.strength != null ? team.strength.toFixed(3) : "1.000";
  return (
    '<div class="mdn-wc-stats">' +
    `<div class="mdn-wc-stat"><div class="mdn-wc-stat-val">${_escapeHtml(last5)}</div><div class="mdn-wc-stat-lbl">Last 5</div></div>` +
    `<div class="mdn-wc-stat"><div class="mdn-wc-stat-val">${_escapeHtml(streak)}</div><div class="mdn-wc-stat-lbl">Streak</div></div>` +
    `<div class="mdn-wc-stat"><div class="mdn-wc-stat-val">${strength}</div><div class="mdn-wc-stat-lbl">Strength</div></div>` +
    "</div>"
  );
}

/** "In the Hunt" panel: seeds 8+ still alive, one stat (Playoff % or a tag) on the right. */
function _buildHuntPanelHtml(hunt, source) {
  let html =
    '<div class="mdn-wc-hunt">' +
    '<div class="mdn-wc-hunt-head"><span>In the Hunt — Seeds 8+</span>' +
    `<span>${hunt.length} team${hunt.length === 1 ? "" : "s"}</span></div>`;

  if (hunt.length === 0) {
    html += '<div class="mdn-wc-hunt-empty">No teams outside the top 7 remain alive.</div>';
  } else {
    for (const team of hunt) {
      const right =
        source === "simulated"
          ? `<div class="mdn-wc-stat"><div class="mdn-wc-stat-val">${(team.playoff_pct || 0).toFixed(1)}%</div><div class="mdn-wc-stat-lbl">Playoff %</div></div>`
          : '<span class="mdn-tag mdn-tag-outline">Not eliminated</span>';
      html +=
        '<div class="mdn-wc-team">' +
        _teamIdentityHtml(team, 22) +
        `<div class="mdn-wc-stats">${right}</div>` +
        "</div>";
    }
  }

  html += "</div>";
  return html;
}

/**
 * Escape a string for safe insertion into an HTML template built via string
 * concatenation.
 *
 * @param {string} str
 * @returns {string}
 */
function _escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
