/**
 * Statistics view for the NFL Monte Carlo Playoff Simulator.
 *
 * "Ledger" design (Modernist system): a Game Outcomes stats ledger and a
 * Score Margin Distribution card, side by side, reusing the same
 * `.mdn-led-table`/`.mdn-card` components as Standings/Team Detail/Results —
 * see design_handoff_standings_redesign/ for the source spec (Option 5a).
 */

"use strict";

/**
 * Render the statistics view.
 *
 * @param {HTMLElement} contentEl - The main content container.
 */
async function renderStatistics(contentEl) {
  App.showLoading();

  let data;
  try {
    data = await API.getStatistics();
  } catch (err) {
    App.hideLoading();
    contentEl.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<p>Unable to load statistics. Please fetch data first.</p>";
    contentEl.appendChild(empty);
    return;
  }

  App.hideLoading();

  contentEl.innerHTML = `
    <div class="mdn-page">
      <h1 style="font:800 34px var(--mdn-font-heading);margin:0 0 6px">Season Statistics</h1>
      <p class="mdn-hint" style="margin:0 0 20px">Based on ${data.total_games} completed games</p>
      <div style="display:flex;flex-wrap:wrap;gap:28px;align-items:flex-start">
        ${_renderGameOutcomesCard(data)}
        ${_renderMarginDistributionCard(data)}
      </div>
      <div style="text-align:center;padding:28px 0 24px">
        <a href="#" class="mdn-back-to-top" id="stats-back-to-top">↑ Back to top</a>
      </div>
    </div>
  `;

  const backTop = document.getElementById("stats-back-to-top");
  if (backTop) {
    backTop.addEventListener("click", (e) => {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
}

/**
 * Render the Game Outcomes card (percentage-bar rows + streak rows).
 *
 * @param {Object} data - The statistics API response.
 * @returns {string} HTML string.
 */
function _renderGameOutcomesCard(data) {
  const rows = [
    _barRow("Home Wins", data.home_wins, data.home_wins_pct),
    _barRow("Away Wins", data.away_wins, data.away_wins_pct),
    _barRow("Ties", data.ties, data.ties_pct),
    _barRow("Overtime Games", data.overtime_games, data.overtime_pct),
    _barRow("One-Score Games (≤8 pts)", data.one_score_games, data.one_score_pct),
    _plainRow("Average Score", `${data.avg_winner_score}:${data.avg_loser_score}`, "(winner:loser)"),
    _streakRow("Longest Winning Streak", data.longest_win_streak),
    _streakRow("Longest Losing Streak", data.longest_lose_streak),
  ];

  return `
    <div class="mdn-card" style="flex:1 1 560px;min-width:480px;margin:0">
      <div class="mdn-card-kicker">Overview</div>
      <div class="mdn-card-title" style="font-size:17px;margin-bottom:14px">Game Outcomes</div>
      <table class="mdn-led-table" style="width:100%">
        <thead><tr><th>Statistic</th><th class="mdn-num" style="width:280px">Value</th></tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table>
    </div>
  `;
}

/**
 * Build a ledger row with an inline percentage bar.
 *
 * @param {string} label - Row label.
 * @param {number} value - Raw count.
 * @param {number} pct - Percentage of total games.
 * @returns {string} HTML string for a single `<tr>`.
 */
function _barRow(label, value, pct) {
  return `
    <tr>
      <td>${_escapeHtml(label)}</td>
      <td class="mdn-num">
        <div style="display:grid;grid-template-columns:100px 110px;column-gap:10px;align-items:center;justify-content:end">
          <div class="mdn-bar-track" style="width:100px">
            <div class="mdn-bar-fill" style="width:${pct}%"></div>
          </div>
          <span><span style="font-weight:700">${value}</span> <span class="mdn-hint">(${pct}%)</span></span>
        </div>
      </td>
    </tr>
  `;
}

/**
 * Build a ledger row with a plain value + detail, no bar (e.g. Average Score).
 *
 * @param {string} label - Row label.
 * @param {string} value - Value text.
 * @param {string} detail - Trailing detail text.
 * @returns {string} HTML string for a single `<tr>`.
 */
function _plainRow(label, value, detail) {
  return `
    <tr>
      <td>${_escapeHtml(label)}</td>
      <td class="mdn-num"><span style="font-weight:700">${_escapeHtml(value)}</span> <span class="mdn-hint">${_escapeHtml(detail)}</span></td>
    </tr>
  `;
}

/**
 * Build a ledger row showing the team(s) tied for a streak, with logo,
 * name, and detail for each — all tied teams share the same streak length,
 * but each keeps its own week range.
 *
 * @param {string} label - Row label.
 * @param {Object[]} streaks - Array of {team, streak, from_week, to_week}, one per tied team.
 * @returns {string} HTML string for a single `<tr>`.
 */
function _streakRow(label, streaks) {
  if (!streaks || streaks.length === 0) {
    return `
      <tr>
        <td>${_escapeHtml(label)}</td>
        <td class="mdn-num"><span class="mdn-hint">No data</span></td>
      </tr>
    `;
  }

  const chips = streaks
    .map((streak) => {
      const logoId = TEAM_LOGO_IDS[streak.team] || "";
      const logoHtml = logoId ? `<img src="img/logos/${logoId}.png" alt="" width="18" height="18">` : "";
      const detail = `${streak.streak} games (week ${streak.from_week}–${streak.to_week})`;
      return `
        <span style="display:inline-flex;align-items:center;gap:6px">
          ${logoHtml}
          <a href="#team/${encodeURIComponent(streak.team)}" class="mdn-team-link">${_escapeHtml(streak.team)}</a>
          <span class="mdn-hint">— ${_escapeHtml(detail)}</span>
        </span>
      `;
    })
    .join("");

  return `
    <tr>
      <td>${_escapeHtml(label)}</td>
      <td class="mdn-num">
        <div style="display:flex;flex-wrap:wrap;gap:6px 10px;justify-content:flex-end">
          ${chips}
        </div>
      </td>
    </tr>
  `;
}

/**
 * Render the Score Margin Distribution card.
 *
 * @param {Object} data - The statistics API response.
 * @returns {string} HTML string.
 */
function _renderMarginDistributionCard(data) {
  const buckets = data.margin_distribution || [];
  const rows = buckets
    .map(
      (m) => `
        <div style="display:grid;grid-template-columns:80px 1fr 100px;column-gap:12px;align-items:center;padding:6px 0;border-bottom:1px solid var(--mdn-divider)">
          <span style="font-size:12px;font-weight:700">${_escapeHtml(m.label)}</span>
          <div class="mdn-bar-track">
            <div class="mdn-bar-fill" style="width:${m.pct}%"></div>
          </div>
          <span style="text-align:right;font-size:12px;font-variant-numeric:tabular-nums"><span style="font-weight:700">${m.count}</span> <span class="mdn-hint">(${m.pct}%)</span></span>
        </div>
      `
    )
    .join("");

  return `
    <div class="mdn-card" style="flex:1 1 380px;min-width:340px;margin:0">
      <div class="mdn-card-kicker">Distribution</div>
      <div class="mdn-card-title" style="font-size:17px;margin-bottom:14px">Score Margin Distribution</div>
      ${rows}
    </div>
  `;
}
