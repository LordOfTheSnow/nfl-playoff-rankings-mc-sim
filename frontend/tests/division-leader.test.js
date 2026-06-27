/**
 * Property test: Division leader visual distinction
 *
 * **Validates: Requirements 4.2**
 *
 * Property 3: For any division standings data with at least one team,
 * the first row (division leader) SHALL have a distinguished background color
 * and a 4px left border accent on the team name cell, while all non-leader
 * rows SHALL NOT have these styles.
 *
 * In the implementation, the division leader distinction is applied via the
 * CSS class "division-leader" on the first <tr> in the tbody. We verify that:
 * - The first row has className "division-leader"
 * - All subsequent rows do NOT have className "division-leader"
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

/**
 * Arbitrary for a single team object matching the expected shape.
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
  tiebreaker: fc.constantFrom("", "H2H", "Conf", "SoV"),
});

/**
 * Arbitrary for a non-empty array of teams (1 to 6 teams per division).
 */
const teamsArbitrary = fc.array(teamArbitrary, { minLength: 1, maxLength: 6 });

describe("Property 3: Division leader visual distinction", () => {
  it("first row has 'division-leader' class and subsequent rows do not", () => {
    fc.assert(
      fc.property(teamsArbitrary, (teams) => {
        // Build the division section using the global function
        const section = buildDivisionSection("East", teams);

        // Get all rows from the tbody
        const tbody = section.querySelector("tbody");
        expect(tbody).not.toBeNull();

        const rows = tbody.querySelectorAll("tr");
        expect(rows.length).toBe(teams.length);

        // First row must have division-leader class
        expect(rows[0].className).toBe("division-leader");

        // All other rows must NOT have division-leader class
        for (let i = 1; i < rows.length; i++) {
          expect(rows[i].className).not.toContain("division-leader");
        }
      }),
      { numRuns: 100 }
    );
  });
});
