/**
 * Regression tests for the auto-cutoff-week frontend fixes.
 *
 * Two bugs shared one root cause: the frontend had no way to know what
 * "Auto" cutoff actually resolves to on the backend, so it guessed —
 * standings.js's header label used `weeks_completed` (a different, whole
 * -week-only stat) as a stand-in, and simulation.js's "games to simulate"
 * preview treated Auto as if the cutoff were the last week of the season
 * (always showing "0 games to simulate"). Both now read the real
 * `auto_cutoff_week` (and, for the preview, `completed_per_week`) that
 * /api/status exposes.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

describe("Standings header: Auto cutoff label", () => {
  it("uses auto_cutoff_week, not weeks_completed, when no manual cutoff is saved", () => {
    const status = {
      season_year: 2026,
      season_weeks: 18,
      expected_total: 272,
      completed: 2,
      weeks_fetched: 1,
      weeks_completed: 0, // no week is FULLY complete yet
      auto_cutoff_week: 1, // but week 1 has 2 completed games
      total_games: 16,
    };

    const html = buildSeasonDataCell(status, null);

    expect(html).toContain("Auto cutoff — week 1");
    expect(html).not.toContain("Auto cutoff — week 0");
  });

  it("still shows a manually-saved cutoff week untouched", () => {
    const status = {
      season_year: 2026,
      season_weeks: 18,
      expected_total: 272,
      completed: 20,
      weeks_fetched: 3,
      weeks_completed: 2,
      auto_cutoff_week: 2,
      total_games: 48,
    };

    const html = buildSeasonDataCell(status, "5");

    expect(html).toContain("Week 5 cutoff");
  });
});

describe("Simulations header: games-to-simulate preview", () => {
  const baseStatus = {
    version: "1.0.0",
    season_year: 2026,
    total_games: 48,
    games_cached: 48,
    expected_total: 272,
    completed: 18,
    weeks_fetched: 3,
    weeks_completed: 1,
    season_weeks: 3,
    cpu_count: 4,
    // Week 1 fully complete, week 2 half-decided, week 3 untouched.
    games_per_week: { 1: 16, 2: 16, 3: 16 },
    completed_per_week: { 1: 16, 2: 2 },
    auto_cutoff_week: 2,
    default_tie_probability: 0.005,
  };

  let contentEl;
  let originalFetchStatus;

  beforeEach(() => {
    localStorage.clear();
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
    originalFetchStatus = API.fetchStatus;
    API.fetchStatus = () => Promise.resolve(baseStatus);
  });

  afterEach(() => {
    API.fetchStatus = originalFetchStatus;
    localStorage.clear();
  });

  it("accounts for open games within the auto-detected cutoff week, not just whole weeks beyond it", async () => {
    await renderSimulations(contentEl);

    // Auto selected by default (no saved cutoff): week 1 (16-16=0) +
    // week 2 (16-2=14, the still-open games) + week 3 (16, entirely beyond
    // cutoff) = 30, at the default 10,000 iterations.
    const totalText = document.getElementById("sim-total-sim").textContent;
    expect(totalText).toContain("30 games");
    expect(totalText).toContain("game simulations");
    expect(totalText).toMatch(/300.000 game simulations/);
  });

  it("never reports 'No games to simulate' under Auto when games remain", async () => {
    await renderSimulations(contentEl);
    const totalText = document.getElementById("sim-total-sim").textContent;
    expect(totalText).not.toContain("No games to simulate");
  });

  it("recomputes correctly when a manual cutoff week is selected", async () => {
    await renderSimulations(contentEl);

    const cutoffSel = document.getElementById("sim-cutoff-sim");
    cutoffSel.value = "1";
    cutoffSel.dispatchEvent(new Event("change", { bubbles: true }));

    // Cutoff=1: week 1 (16-16=0) + week 2 (16, fully beyond cutoff) +
    // week 3 (16) = 32.
    const totalText = document.getElementById("sim-total-sim").textContent;
    expect(totalText).toContain("32 games");
  });
});
