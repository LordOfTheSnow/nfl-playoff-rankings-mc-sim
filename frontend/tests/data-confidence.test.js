/**
 * Simulations page: "Data-driven ratings" indicator under the Results line.
 *
 * Shows how much of the league's team ratings comes from played games
 * rather than the league-average prior (server-computed `data_driven_pct` /
 * `data_confidence`, see doc/algorithms.md). Mirrors export.py's
 * `_data_confidence_line`.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

const baseStatus = {
  version: "1.0.0",
  season_year: 2026,
  total_games: 16,
  games_cached: 16,
  expected_total: 272,
  completed: 1,
  weeks_fetched: 1,
  weeks_completed: 0,
  cpu_count: 4,
  games_per_week: { 1: 16 },
  default_tie_probability: 0.0029,
};

const baseResult = {
  iterations_run: 10000,
  cutoff_week_used: 1,
  fixed_games: 1,
  simulated_games: 271,
  team_results: [],
  top_scenarios: [],
};

describe("Simulations: data-driven ratings indicator", () => {
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
    window._simulationResults = null;
    localStorage.clear();
  });

  it("shows percentage, label and games played directly under the Results divider", async () => {
    window._simulationResults = { ...baseResult, data_driven_pct: 11.1, data_confidence: "Very low" };
    await renderSimulations(contentEl);

    const text = contentEl.textContent;
    expect(text).toContain("Data-driven ratings: 11% — Very low");
    expect(text).toContain("1 of 272 games played (0.4%)");

    const html = contentEl.innerHTML;
    expect(html.indexOf("Results")).toBeLessThan(html.indexOf("Data-driven ratings"));
  });

  it("rounds half up like the export does", async () => {
    window._simulationResults = { ...baseResult, data_driven_pct: 12.5, data_confidence: "Very low" };
    await renderSimulations(contentEl);
    expect(contentEl.textContent).toContain("Data-driven ratings: 13%");
  });

  it("rounds the games-played percentage half up (17/272 = 6.25% -> 6.3%), same as the export", async () => {
    window._simulationResults = { ...baseResult, fixed_games: 17, simulated_games: 255, data_driven_pct: 12, data_confidence: "Very low" };
    await renderSimulations(contentEl);
    expect(contentEl.textContent).toContain("17 of 272 games played (6.3%)");
  });

  it("is omitted for results without the field", async () => {
    window._simulationResults = { ...baseResult };
    await renderSimulations(contentEl);
    expect(contentEl.textContent).not.toContain("Data-driven ratings");
  });

  it("escapes the label", async () => {
    window._simulationResults = { ...baseResult, data_driven_pct: 50, data_confidence: "<img src=x>" };
    await renderSimulations(contentEl);
    expect(contentEl.querySelector("img[src='x']")).toBeNull();
  });
});
