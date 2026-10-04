/**
 * Teaser image tests.
 *
 * computeMovers decides which teams appear on the Movers card, so its rules
 * are checked with property-based tests: at most `limit` movers, none with a
 * zero change, ordered by largest absolute change, and every mover's delta
 * equal to the rounded difference between the two snapshots.
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fc from "fast-check";

const probabilityArbitrary = fc.integer({ min: 0, max: 1000 }).map((n) => n / 10);

const snapshotsArbitrary = fc
  .uniqueArray(fc.stringOf(fc.constantFrom(..."ABCDEFGHIJKLMNOPQRSTUVWXYZ"), { minLength: 2, maxLength: 6 }), {
    minLength: 0,
    maxLength: 32,
  })
  .chain((teams) =>
    fc.tuple(
      fc.constant(teams),
      fc.array(probabilityArbitrary, { minLength: teams.length, maxLength: teams.length }),
      fc.array(probabilityArbitrary, { minLength: teams.length, maxLength: teams.length }),
    ),
  )
  .map(([teams, now, before]) => {
    const current = {};
    const baseline = {};
    teams.forEach((team, i) => {
      current[team] = now[i];
      baseline[team] = before[i];
    });
    return { current, baseline };
  });

describe("computeMovers", () => {
  it("returns at most the requested number of movers", () => {
    fc.assert(
      fc.property(snapshotsArbitrary, fc.integer({ min: 0, max: 10 }), ({ current, baseline }, limit) => {
        expect(computeMovers(current, baseline, limit).length).toBeLessThanOrEqual(limit);
      }),
      { numRuns: 200 },
    );
  });

  it("never includes a team whose probability did not change", () => {
    fc.assert(
      fc.property(snapshotsArbitrary, ({ current, baseline }) => {
        for (const mover of computeMovers(current, baseline, 32)) {
          expect(mover.delta).not.toBe(0);
        }
      }),
      { numRuns: 200 },
    );
  });

  it("orders movers by largest absolute change first", () => {
    fc.assert(
      fc.property(snapshotsArbitrary, ({ current, baseline }) => {
        const movers = computeMovers(current, baseline, 32);
        for (let i = 1; i < movers.length; i++) {
          expect(Math.abs(movers[i - 1].delta)).toBeGreaterThanOrEqual(Math.abs(movers[i].delta));
        }
      }),
      { numRuns: 200 },
    );
  });

  it("reports each delta as the difference between the snapshots, rounded to one decimal", () => {
    fc.assert(
      fc.property(snapshotsArbitrary, ({ current, baseline }) => {
        for (const mover of computeMovers(current, baseline, 32)) {
          expect(mover.current).toBe(current[mover.team]);
          expect(mover.previous).toBe(baseline[mover.team]);
          const expected = Math.round((current[mover.team] - baseline[mover.team]) * 10) / 10;
          expect(mover.delta).toBeCloseTo(expected, 9);
        }
      }),
      { numRuns: 200 },
    );
  });

  it("ignores teams missing from either snapshot", () => {
    const movers = computeMovers({ Lions: 50, Bears: 10 }, { Lions: 20 }, 5);
    expect(movers.map((m) => m.team)).toEqual(["Lions"]);
    expect(movers[0].delta).toBe(30);
  });

  it("breaks ties in absolute change by team name", () => {
    const movers = computeMovers({ Bears: 15, Lions: 5 }, { Bears: 5, Lions: 15 }, 5);
    expect(movers.map((m) => m.team)).toEqual(["Bears", "Lions"]);
  });

  it("treats floating-point noise as no change", () => {
    const movers = computeMovers({ Lions: 0.30000000000000004 }, { Lions: 0.3 }, 5);
    expect(movers).toEqual([]);
  });
});

describe("Teaser card on the Export page", () => {
  const simulation = {
    cutoff_week_used: 9,
    iterations_run: 5000,
    team_results: [{ team: "Lions", playoff_probability: 50, seed_probabilities: {} }],
  };
  let originalGetBaseline;

  beforeEach(() => {
    originalGetBaseline = API.getTeaserBaseline;
    window._simulationResults = null;
  });

  afterEach(() => {
    API.getTeaserBaseline = originalGetBaseline;
    window._simulationResults = null;
  });

  it("disables download until a baseline is saved, but allows saving once a simulation exists", async () => {
    API.getTeaserBaseline = () => Promise.resolve({ baseline: null });
    window._simulationResults = simulation;
    const contentEl = document.getElementById("content");

    await renderExport(contentEl);

    expect(document.getElementById("teaser-download-btn").disabled).toBe(true);
    expect(document.getElementById("teaser-save-btn").disabled).toBe(false);
    expect(document.getElementById("teaser-baseline-info").textContent).toContain("No baseline saved yet");
  });

  it("disables both teaser buttons when no simulation has run", async () => {
    API.getTeaserBaseline = () =>
      Promise.resolve({ baseline: { season: 2025, cutoff_week: 8, saved_at: "2026-09-30T12:00:00+00:00", probabilities: {} } });
    const contentEl = document.getElementById("content");

    await renderExport(contentEl);

    expect(document.getElementById("teaser-download-btn").disabled).toBe(true);
    expect(document.getElementById("teaser-save-btn").disabled).toBe(true);
    expect(document.getElementById("teaser-baseline-info").textContent).toContain("cutoff week 8");
  });
});
