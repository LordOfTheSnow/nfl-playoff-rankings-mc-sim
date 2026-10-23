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

/**
 * Matchups card color system: team names/logos always use TEAM_COLORS
 * directly (stable regardless of opponent), but the bar fill is derived
 * per matchup via _matchupBarColors, which lightens the away segment when
 * the two teams' colors are in the same hue family — otherwise two
 * same-color teams (e.g. two red-branded franchises) would render as one
 * indistinguishable block instead of a readable split.
 */
const hexColorArbitrary = fc
  .tuple(fc.integer({ min: 0, max: 255 }), fc.integer({ min: 0, max: 255 }), fc.integer({ min: 0, max: 255 }))
  .map(([r, g, b]) => `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`);

const hueArbitrary = fc.integer({ min: 0, max: 3599 }).map((n) => n / 10);

describe("_hexToHsl / _hslToHex", () => {
  it("round-trips each RGB channel within rounding tolerance", () => {
    fc.assert(
      fc.property(hexColorArbitrary, (hex) => {
        const { h, s, l } = _hexToHsl(hex);
        const result = _hslToHex(h, s, l);
        for (const start of [1, 3, 5]) {
          const original = parseInt(hex.slice(start, start + 2), 16);
          const roundTripped = parseInt(result.slice(start, start + 2), 16);
          expect(Math.abs(original - roundTripped)).toBeLessThanOrEqual(2);
        }
      }),
      { numRuns: 300 },
    );
  });
});

describe("_hueDist", () => {
  it("is always between 0 and 180", () => {
    fc.assert(
      fc.property(hueArbitrary, hueArbitrary, (a, b) => {
        const d = _hueDist(a, b);
        expect(d).toBeGreaterThanOrEqual(0);
        expect(d).toBeLessThanOrEqual(180);
      }),
      { numRuns: 200 },
    );
  });

  it("is symmetric", () => {
    fc.assert(
      fc.property(hueArbitrary, hueArbitrary, (a, b) => {
        expect(_hueDist(a, b)).toBeCloseTo(_hueDist(b, a), 9);
      }),
      { numRuns: 200 },
    );
  });

  it("is zero for identical hues", () => {
    fc.assert(
      fc.property(hueArbitrary, (a) => {
        expect(_hueDist(a, a)).toBeCloseTo(0, 9);
      }),
      { numRuns: 100 },
    );
  });
});

describe("_matchupBarColors", () => {
  it("always keeps the home bar at the team's exact canonical color", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...Object.values(TEAM_COLORS)),
        fc.constantFrom(...Object.values(TEAM_COLORS)),
        (home, away) => {
          const { homeBarColor } = _matchupBarColors(home, away);
          expect(homeBarColor).toBe(home);
        },
      ),
      { numRuns: 200 },
    );
  });

  it("keeps the away bar at its canonical color unless it clashes with home", () => {
    // Texans vs Cardinals: both dark reds (hue distance well under 30°) — lightened.
    const close = _matchupBarColors(TEAM_COLORS["Texans"], TEAM_COLORS["Cardinals"]);
    expect(close.awayBarColor).not.toBe(TEAM_COLORS["Cardinals"]);
    expect(_hexToHsl(close.awayBarColor).l).toBeCloseTo(68, 0);

    // Ravens (purple) vs Browns (brown): clearly different hue families — untouched.
    const far = _matchupBarColors(TEAM_COLORS["Ravens"], TEAM_COLORS["Browns"]);
    expect(far.awayBarColor).toBe(TEAM_COLORS["Browns"]);
  });

  it("always registers every team pair as either clashing or not, never crashing", () => {
    const teams = Object.keys(TEAM_COLORS);
    for (const home of teams) {
      for (const away of teams) {
        const { homeBarColor, awayBarColor } = _matchupBarColors(TEAM_COLORS[home], TEAM_COLORS[away]);
        expect(homeBarColor).toMatch(/^#[0-9a-f]{6}$/);
        expect(awayBarColor).toMatch(/^#[0-9a-f]{6}$/);
      }
    }
  });
});

describe("_weekdayLabel", () => {
  it("maps a date-only ISO string to its UTC weekday", () => {
    expect(_weekdayLabel("2026-10-29")).toBe("THURSDAY");
    expect(_weekdayLabel("2026-11-01")).toBe("SUNDAY");
    expect(_weekdayLabel("2026-11-02")).toBe("MONDAY");
    expect(_weekdayLabel("2026-12-25")).toBe("FRIDAY");
  });
});

describe("Matchups card on the Export page", () => {
  afterEach(() => {
    window._simulationResults = null;
  });

  it("disables the Matchups button when there are no next-week games", async () => {
    window._simulationResults = {
      cutoff_week_used: 9,
      iterations_run: 5000,
      simulated_games: 10,
      team_results: [],
      next_week_matchups: [],
    };
    const contentEl = document.getElementById("content");

    await renderExport(contentEl);

    expect(document.getElementById("matchups-teaser-btn").disabled).toBe(true);
  });

  it("enables the Matchups button once next-week matchups exist", async () => {
    window._simulationResults = {
      cutoff_week_used: 9,
      iterations_run: 5000,
      simulated_games: 10,
      team_results: [],
      next_week_matchups: [
        {
          game_id: "1",
          week: 10,
          home_team: "Lions",
          away_team: "Bears",
          home_win_probability: 60,
          away_win_probability: 39,
          tie_probability: 1,
        },
      ],
    };
    const contentEl = document.getElementById("content");

    await renderExport(contentEl);

    expect(document.getElementById("matchups-teaser-btn").disabled).toBe(false);
  });

  it("disables the Matchups button when no simulation has run", async () => {
    const contentEl = document.getElementById("content");

    await renderExport(contentEl);

    expect(document.getElementById("matchups-teaser-btn").disabled).toBe(true);
  });
});
