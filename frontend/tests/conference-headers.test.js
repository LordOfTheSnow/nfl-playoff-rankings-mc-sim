/**
 * Property test: Conference header structure
 *
 * **Validates: Requirements 8.3**
 *
 * Property 9 (superseded by the Modernist "Ledger" redesign — see
 * design_handoff_standings_redesign/): the design system is single-accent
 * ("mono scheme"), so AFC and NFC conference headers are no longer
 * color-differentiated. Instead we verify the structural contract:
 * - buildConferenceSection(conf, divisions) produces a `.mdn-conf-head`
 *   wrapper with a conference logo <img> and an <h2> whose text is the
 *   conference name.
 * - The section carries a `data-conference` attribute matching the
 *   conference passed in (used by the conference filter).
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
 * Arbitrary for a divisions object with 1-4 divisions, each with 1-4 teams.
 */
const divisionsArbitrary = fc.record(
  {
    East: fc.array(teamArbitrary, { minLength: 1, maxLength: 4 }),
    North: fc.array(teamArbitrary, { minLength: 1, maxLength: 4 }),
    South: fc.array(teamArbitrary, { minLength: 1, maxLength: 4 }),
    West: fc.array(teamArbitrary, { minLength: 1, maxLength: 4 }),
  },
  { requiredKeys: [] }
);

/**
 * Arbitrary that produces at least one division (so the section is non-empty).
 */
const nonEmptyDivisionsArbitrary = divisionsArbitrary.filter(
  (divs) => Object.keys(divs).length > 0
);

describe("Property 9: Conference header structure (mono-accent design)", () => {
  it("conference section has a .mdn-conf-head with logo and heading text", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("AFC", "NFC"),
        nonEmptyDivisionsArbitrary,
        (conference, divisions) => {
          const section = buildConferenceSection(conference, divisions);

          const header = section.querySelector(".mdn-conf-head");
          expect(header).not.toBeNull();

          const h2 = header.querySelector("h2");
          expect(h2).not.toBeNull();
          expect(h2.textContent).toBe(conference);

          const logo = header.querySelector("img");
          expect(logo).not.toBeNull();
          expect(logo.getAttribute("alt")).toBe(conference + " logo");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("section data-conference attribute matches the conference passed in", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("AFC", "NFC"),
        nonEmptyDivisionsArbitrary,
        (conference, divisions) => {
          const section = buildConferenceSection(conference, divisions);
          expect(section.getAttribute("data-conference")).toBe(conference);
          expect(section.classList.contains("mdn-conf-section")).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });
});
