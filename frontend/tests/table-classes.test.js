/**
 * Property Test: Table Bootstrap class assignment
 *
 * **Validates: Requirements 4.1, 4.3, 4.4**
 *
 * Property 2: For any table rendered by the application (standings, results
 * probability, schedule), the table element SHALL contain the Bootstrap `table`
 * class plus the context-appropriate modifier classes (`table-striped table-hover`
 * for standings and probability tables, `table-hover` for schedule tables).
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

// --- Arbitraries ---

/**
 * Generate a random team object with all required fields for standings.
 */
const teamArbitrary = fc.record({
  team: fc.stringOf(fc.char(), { minLength: 1, maxLength: 12 }),
  wins: fc.integer({ min: 0, max: 17 }),
  losses: fc.integer({ min: 0, max: 17 }),
  ties: fc.integer({ min: 0, max: 17 }),
  win_percentage: fc.double({ min: 0, max: 1, noNaN: true }),
  games_behind: fc.double({ min: 0, max: 10, noNaN: true }),
  division_record: fc.constant("0-0-0"),
  conference_record: fc.constant("0-0-0"),
  strength: fc.double({ min: 0.5, max: 1.5, noNaN: true }),
  tiebreaker: fc.constantFrom("", "H2H", "Conf"),
});

/**
 * Generate a random array of 2-6 teams for a division section.
 */
const teamsArrayArbitrary = fc.array(teamArbitrary, { minLength: 2, maxLength: 6 });

/**
 * Generate a random division name.
 */
const divisionNameArbitrary = fc.constantFrom("East", "North", "South", "West");

/**
 * Generate a random game object for the schedule view.
 */
const gameArbitrary = fc.record({
  week: fc.integer({ min: 1, max: 18 }),
  opponent: fc.stringOf(fc.char(), { minLength: 1, maxLength: 12 }),
  home: fc.boolean(),
  status: fc.constantFrom("completed", "scheduled", "in-progress"),
  result: fc.constantFrom("win", "loss", "tie", null),
  home_score: fc.integer({ min: 0, max: 60 }),
  away_score: fc.integer({ min: 0, max: 60 }),
});

/**
 * Generate a random schedule data payload.
 */
const scheduleDataArbitrary = fc.record({
  team: fc.stringOf(fc.char(), { minLength: 1, maxLength: 12 }),
  record: fc.record({
    wins: fc.integer({ min: 0, max: 17 }),
    losses: fc.integer({ min: 0, max: 17 }),
    ties: fc.integer({ min: 0, max: 17 }),
    win_percentage: fc.double({ min: 0, max: 1, noNaN: true }),
  }),
  games: fc.array(gameArbitrary, { minLength: 1, maxLength: 17 }),
});

// --- Property Tests ---

describe("Property 2: Table Bootstrap class assignment", () => {
  it("standings tables have 'table table-striped table-hover' classes", () => {
    fc.assert(
      fc.property(divisionNameArbitrary, teamsArrayArbitrary, (divName, teams) => {
        const section = buildDivisionSection(divName, teams);
        const table = section.querySelector("table");

        expect(table).not.toBeNull();
        expect(table.classList.contains("table")).toBe(true);
        expect(table.classList.contains("table-striped")).toBe(true);
        expect(table.classList.contains("table-hover")).toBe(true);
      }),
      { numRuns: 100 }
    );
  });

  it("schedule tables have 'table table-hover' but NOT 'table-striped'", () => {
    fc.assert(
      fc.property(scheduleDataArbitrary, (data) => {
        const contentEl = document.createElement("div");
        renderScheduleContent(contentEl, data);
        const table = contentEl.querySelector("table");

        expect(table).not.toBeNull();
        expect(table.classList.contains("table")).toBe(true);
        expect(table.classList.contains("table-hover")).toBe(true);
        expect(table.classList.contains("table-striped")).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("results probability tables have 'table table-striped table-hover' classes", () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 16 }),
        (teamCount) => {
          // Build mock simulation results with random teams
          const teamResults = [];
          for (let i = 0; i < teamCount; i++) {
            teamResults.push({
              team: "Team" + i,
              conference: i < teamCount / 2 ? "AFC" : "NFC",
              division: "East",
              playoff_probability: Math.random() * 100,
              strength_rating: 0.8 + Math.random() * 0.4,
              seed_probabilities: { "1": 10, "2": 20, "3": 30, "4": 15, "5": 10, "6": 10, "7": 5 },
            });
          }

          window._simulationResults = {
            iterations_run: 1000,
            cutoff_week_used: 10,
            fixed_games: 100,
            simulated_games: 50,
            low_confidence: false,
            convergence_achieved: true,
            team_results: teamResults,
            top_scenarios: [],
          };

          const contentEl = document.createElement("div");
          renderResults(contentEl);

          const tables = contentEl.querySelectorAll("table");
          expect(tables.length).toBeGreaterThan(0);

          tables.forEach((table) => {
            expect(table.classList.contains("table")).toBe(true);
            expect(table.classList.contains("table-striped")).toBe(true);
            expect(table.classList.contains("table-hover")).toBe(true);
          });
        }
      ),
      { numRuns: 100 }
    );
  });
});
