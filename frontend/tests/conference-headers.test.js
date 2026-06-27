/**
 * Property test: Conference header border colors
 *
 * **Validates: Requirements 8.3**
 *
 * Property 9: For any rendered conference header, the left border color
 * SHALL be #d32f2f for AFC conferences and #1565c0 for NFC conferences.
 *
 * Since JSDOM does not compute CSS, we verify that:
 * - buildConferenceSection("AFC", divisions) produces an h2 with class
 *   "conference-header conference-header--afc"
 * - buildConferenceSection("NFC", divisions) produces an h2 with class
 *   "conference-header conference-header--nfc"
 *
 * These classes map to CSS rules that set border-left-color to the
 * corresponding conference colors (#d32f2f for AFC, #1565c0 for NFC).
 *
 * Additionally we verify the CSS file defines the correct color mappings.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";
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

describe("Property 9: Conference header border colors", () => {
  it("AFC conference header has class conference-header--afc", () => {
    fc.assert(
      fc.property(nonEmptyDivisionsArbitrary, (divisions) => {
        const section = buildConferenceSection("AFC", divisions);

        const header = section.querySelector("h2");
        expect(header).not.toBeNull();
        expect(header.classList.contains("conference-header")).toBe(true);
        expect(header.classList.contains("conference-header--afc")).toBe(true);
        expect(header.classList.contains("conference-header--nfc")).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("NFC conference header has class conference-header--nfc", () => {
    fc.assert(
      fc.property(nonEmptyDivisionsArbitrary, (divisions) => {
        const section = buildConferenceSection("NFC", divisions);

        const header = section.querySelector("h2");
        expect(header).not.toBeNull();
        expect(header.classList.contains("conference-header")).toBe(true);
        expect(header.classList.contains("conference-header--nfc")).toBe(true);
        expect(header.classList.contains("conference-header--afc")).toBe(false);
      }),
      { numRuns: 100 }
    );
  });

  it("conference header data-conference attribute matches conference name", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("AFC", "NFC"),
        nonEmptyDivisionsArbitrary,
        (conference, divisions) => {
          const section = buildConferenceSection(conference, divisions);

          // The section has data-conference attribute
          expect(section.getAttribute("data-conference")).toBe(conference);

          // The header has the correct modifier class
          const header = section.querySelector("h2");
          expect(header).not.toBeNull();

          const expectedClass =
            "conference-header--" + conference.toLowerCase();
          expect(header.classList.contains(expectedClass)).toBe(true);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("CSS defines correct border-left-color for AFC (#d32f2f) and NFC (#1565c0)", () => {
    const cssPath = resolve(__dirname, "../css/styles.css");
    const css = readFileSync(cssPath, "utf-8");

    // Verify AFC border color rule exists
    expect(css).toMatch(/\.conference-header--afc\s*\{[^}]*border-left-color/);
    // Verify it uses the AFC color variable or literal
    expect(css).toMatch(
      /\.conference-header--afc\s*\{[^}]*border-left-color:\s*(var\(--color-conference-afc\)|#d32f2f)/
    );

    // Verify NFC border color rule exists
    expect(css).toMatch(/\.conference-header--nfc\s*\{[^}]*border-left-color/);
    // Verify it uses the NFC color variable or literal
    expect(css).toMatch(
      /\.conference-header--nfc\s*\{[^}]*border-left-color:\s*(var\(--color-conference-nfc\)|#1565c0)/
    );

    // Verify the custom property values
    expect(css).toMatch(/--color-conference-afc:\s*#d32f2f/);
    expect(css).toMatch(/--color-conference-nfc:\s*#1565c0/);
  });
});
