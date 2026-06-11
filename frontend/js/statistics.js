/**
 * Statistics view for the NFL Monte Carlo Playoff Simulator.
 *
 * Displays season-wide statistics: home/away win rates, ties,
 * average score, and longest winning/losing streaks.
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

  const winLogoId = TEAM_LOGO_IDS[data.longest_win_streak.team] || "";
  const winLogo = winLogoId ? `<img src="img/logos/${winLogoId}.png" alt="" width="20" height="20" style="vertical-align:middle;margin-right:0.3rem">` : "";
  const loseLogoId = TEAM_LOGO_IDS[data.longest_lose_streak.team] || "";
  const loseLogo = loseLogoId ? `<img src="img/logos/${loseLogoId}.png" alt="" width="20" height="20" style="vertical-align:middle;margin-right:0.3rem">` : "";

  contentEl.innerHTML = `
    <div class="controls-panel" style="margin-bottom:1.5rem">
      <h2 style="margin-bottom:1rem">Season Statistics</h2>
      <p class="cutoff-label" style="margin-bottom:1.5rem">Based on ${data.total_games} completed games</p>

      <table class="probability-table" style="max-width:600px">
        <thead>
          <tr>
            <th style="text-align:left">Statistic</th>
            <th style="text-align:right">Value</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td style="text-align:left">Home Wins</td>
            <td style="text-align:right"><strong>${data.home_wins}</strong> (${data.home_wins_pct}%)</td>
          </tr>
          <tr>
            <td style="text-align:left">Away Wins</td>
            <td style="text-align:right"><strong>${data.away_wins}</strong> (${data.away_wins_pct}%)</td>
          </tr>
          <tr>
            <td style="text-align:left">Ties</td>
            <td style="text-align:right"><strong>${data.ties}</strong> (${data.ties_pct}%)</td>
          </tr>
          <tr>
            <td style="text-align:left">Overtime Games</td>
            <td style="text-align:right"><strong>${data.overtime_games}</strong> (${data.overtime_pct}%)</td>
          </tr>
          <tr>
            <td style="text-align:left">One-Score Games (≤8 pts)</td>
            <td style="text-align:right"><strong>${data.one_score_games}</strong> (${data.one_score_pct}%)</td>
          </tr>
          <tr>
            <td style="text-align:left">Average Score</td>
            <td style="text-align:right"><strong>${data.avg_winner_score}:${data.avg_loser_score}</strong> (winner:loser)</td>
          </tr>
          <tr>
            <td style="text-align:left">Longest Winning Streak</td>
            <td style="text-align:right">${winLogo}<a href="#team/${encodeURIComponent(data.longest_win_streak.team)}" class="team-link"><strong>${data.longest_win_streak.team}</strong></a> — ${data.longest_win_streak.streak} games (week ${data.longest_win_streak.from_week}–${data.longest_win_streak.to_week})</td>
          </tr>
          <tr>
            <td style="text-align:left">Longest Losing Streak</td>
            <td style="text-align:right">${loseLogo}<a href="#team/${encodeURIComponent(data.longest_lose_streak.team)}" class="team-link"><strong>${data.longest_lose_streak.team}</strong></a> — ${data.longest_lose_streak.streak} games (week ${data.longest_lose_streak.from_week}–${data.longest_lose_streak.to_week})</td>
          </tr>
        </tbody>
      </table>
    </div>
  `;
}
