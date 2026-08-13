/**
 * Simulations page control-wiring regression tests.
 *
 * Covers a class of bug that the existing structural/property-based tests
 * (form-classes, label-input) don't reach: two different readers of the same
 * localStorage key silently falling back to *different* defaults when the
 * key was never written. This is exactly what happened with `sim-workers` —
 * the Workers slider fell back to the server's real `cpu_count`, while the
 * clinching panel's estimate line fell back to a hardcoded `4`, so a user
 * who never touched the Workers slider saw "6 cores of 6" in one place and
 * "4 cores" in the other. The fix was to persist the resolved default to
 * localStorage on first render rather than only on drag — these tests
 * assert that invariant directly, plus the Tie Probability reset button and
 * the enumeration/sampling settings-hint switch added alongside it.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";

// jsdom doesn't implement scrollIntoView (used by _showTeamDetail when the
// candidate-details panel is revealed) — only needed for this file's tests,
// since it's the first suite to call _showTeamDetail directly.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

/** A status response with enough data fetched to render the Simulation card. */
const baseStatus = {
  version: "1.0.0",
  season_year: 2025,
  total_games: 200,
  games_cached: 200,
  expected_total: 272,
  completed: 150,
  weeks_fetched: 16,
  weeks_completed: 15,
  cpu_count: 6,
  games_per_week: { 16: 16, 17: 16, 18: 16 },
  default_tie_probability: 0.0029,
};

const sampleResults = {
  iterations_run: 10000,
  cutoff_week_used: 15,
  team_results: [
    {
      team: "Ravens",
      conference: "AFC",
      division: "AFC North",
      record: "9-6-0",
      playoff_probability: 55.5,
      strength_rating: 1.05,
      seed_probabilities: { 1: 5, 2: 10, 3: 15, 4: 10, 5: 10, 6: 5, 7: 0.5 },
    },
  ],
};

describe("Simulations controls: localStorage default persistence", () => {
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

  it("persists the resolved Workers default to localStorage on first render, matching the displayed label", async () => {
    await renderSimulations(contentEl);
    expect(localStorage.getItem("sim-workers")).toBe(String(baseStatus.cpu_count));
    const label = document.getElementById("sim-workers-label-sim").textContent;
    expect(label).toBe(`${baseStatus.cpu_count} cores of ${baseStatus.cpu_count}`);
  });

  it("does not overwrite an existing custom Workers value on re-render", async () => {
    localStorage.setItem("sim-workers", "2");
    await renderSimulations(contentEl);
    expect(localStorage.getItem("sim-workers")).toBe("2");
    const label = document.getElementById("sim-workers-label-sim").textContent;
    expect(label).toBe(`2 cores of ${baseStatus.cpu_count}`);
  });

  it("persists the resolved Tie Probability default to localStorage on first render", async () => {
    await renderSimulations(contentEl);
    const expected = String(Math.round(baseStatus.default_tie_probability * 10000));
    expect(localStorage.getItem("sim-tie-probability")).toBe(expected);
  });

  it("does not overwrite an existing custom Tie Probability value on re-render", async () => {
    localStorage.setItem("sim-tie-probability", "42");
    await renderSimulations(contentEl);
    expect(localStorage.getItem("sim-tie-probability")).toBe("42");
  });

  it("regression guard: the Workers slider's displayed value and localStorage never disagree after a render", async () => {
    // This is the invariant the bug violated: some other reader of
    // sim-workers (the clinching panel) disagreed with what the slider
    // itself showed, because the key was left unset until a manual drag.
    // Asserting it's always populated to match the slider is what makes
    // every other reader agree by construction, not by coincidence.
    await renderSimulations(contentEl);
    const sliderValue = document.getElementById("sim-workers-sim").value;
    expect(localStorage.getItem("sim-workers")).toBe(sliderValue);
  });
});

describe("Tie Probability reset button", () => {
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

  it("restores the slider, label, and localStorage to the calculated default after a manual override", async () => {
    await renderSimulations(contentEl);

    const slider = document.getElementById("sim-tie-prob-sim");
    slider.value = "80";
    slider.dispatchEvent(new Event("input", { bubbles: true }));
    expect(localStorage.getItem("sim-tie-probability")).toBe("80");
    expect(document.getElementById("sim-tie-prob-label-sim").textContent).toContain("custom");

    const resetBtn = document.getElementById("sim-tie-prob-reset-sim");
    resetBtn.dispatchEvent(new Event("click", { bubbles: true }));

    const expectedDefault = String(Math.round(baseStatus.default_tie_probability * 10000));
    expect(slider.value).toBe(expectedDefault);
    expect(localStorage.getItem("sim-tie-probability")).toBe(expectedDefault);
    expect(document.getElementById("sim-tie-prob-label-sim").textContent).toContain("estimated");
  });
});

describe("Clinching panel settings hint (enumeration vs. sampling)", () => {
  let contentEl;
  let originalFetchStatus;
  let originalClinchEstimate;

  beforeEach(async () => {
    localStorage.clear();
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
    originalFetchStatus = API.fetchStatus;
    originalClinchEstimate = API.clinchEstimate;
    API.fetchStatus = () => Promise.resolve(baseStatus);
    // team-detail-panel only exists after a render — _showTeamDetail below
    // writes into it directly, mirroring how a real team-name click would.
    await renderSimulations(contentEl);
  });

  afterEach(() => {
    API.fetchStatus = originalFetchStatus;
    API.clinchEstimate = originalClinchEstimate;
    localStorage.clear();
  });

  it("omits Noise/Tie Probability from the estimate line and hint when relevant games fit within the enumeration threshold", async () => {
    API.clinchEstimate = () => Promise.resolve({
      available: true,
      relevant_games: 6, // <= default threshold of 9 -> enumeration
      team_record_combos: 3,
      ms_per_eval: 1.0,
      cpu_count: 4,
    });

    _showTeamDetail("Ravens", sampleResults);
    await new Promise((resolve) => setTimeout(resolve, 0));

    const info = document.getElementById("clinch-enum-info").textContent;
    expect(info).toContain("enumeration");
    expect(info).not.toContain("tie");
    expect(info).not.toContain("noise");

    const hint = document.getElementById("clinch-settings-hint").textContent;
    expect(hint).toContain("Enumeration tries every outcome exhaustively");
    expect(hint).toContain("don't apply");
  });

  it("includes Tie Probability in the estimate line and hint when relevant games exceed the enumeration threshold", async () => {
    API.clinchEstimate = () => Promise.resolve({
      available: true,
      relevant_games: 12, // > default threshold of 9 -> sampling
      team_record_combos: 5,
      ms_per_eval: 1.0,
      cpu_count: 4,
    });

    _showTeamDetail("Ravens", sampleResults);
    await new Promise((resolve) => setTimeout(resolve, 0));

    const info = document.getElementById("clinch-enum-info").textContent;
    expect(info).toContain("sampling");
    expect(info).toContain("tie");

    const hint = document.getElementById("clinch-settings-hint").textContent;
    expect(hint).toContain("Trials, Noise, Tie Probability");
  });

  it("falls back to the estimate endpoint's cpu_count for the cores label when sim-workers is unset", async () => {
    expect(localStorage.getItem("sim-workers")).toBeTruthy(); // persisted by renderSimulations above
    localStorage.removeItem("sim-workers");

    API.clinchEstimate = () => Promise.resolve({
      available: true,
      relevant_games: 6,
      team_record_combos: 3,
      ms_per_eval: 1.0,
      cpu_count: 4,
    });

    _showTeamDetail("Ravens", sampleResults);
    await new Promise((resolve) => setTimeout(resolve, 0));

    const info = document.getElementById("clinch-enum-info").textContent;
    expect(info).toContain("4 cores");
  });
});
