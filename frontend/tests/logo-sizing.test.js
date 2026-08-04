/**
 * Property test: Team logo sizing by context
 *
 * **Validates: Requirements 8.4**
 *
 * Property 10: For any team logo <img> element rendered in the application,
 * its width and height attributes SHALL be 20×20 when inside a standings
 * table row, 26×26 when inside a conference header, and 30×30 when inside
 * the site header/navbar (Modernist "Ledger" redesign — see
 * design_handoff_standings_redesign/).
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

/**
 * All valid NFL team names (keys of TEAM_LOGO_IDS).
 * Defined statically so arbitraries can be built at module evaluation time.
 */
const TEAM_NAMES = [
  "Bills", "Dolphins", "Patriots", "Jets",
  "Ravens", "Bengals", "Browns", "Steelers",
  "Texans", "Colts", "Jaguars", "Titans",
  "Chiefs", "Broncos", "Chargers", "Raiders",
  "Cowboys", "Eagles", "Giants", "Commanders",
  "Bears", "Lions", "Packers", "Vikings",
  "Falcons", "Panthers", "Saints", "Buccaneers",
  "Cardinals", "Rams", "49ers", "Seahawks",
];

/**
 * Arbitrary that picks a random valid team name.
 */
const teamNameArbitrary = fc.constantFrom(...TEAM_NAMES);

/**
 * Arbitrary for a team object with a valid team name (ensures logo rendering).
 */
const teamArbitrary = fc.record({
  team: teamNameArbitrary,
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
 * Arbitrary for a non-empty array of teams (1 to 4 per division).
 */
const teamsArbitrary = fc.array(teamArbitrary, { minLength: 1, maxLength: 4 });

/**
 * Arbitrary for conference name.
 */
const conferenceArbitrary = fc.constantFrom("AFC", "NFC");

describe("Property 10: Team logo sizing by context", () => {
  it("table row logos are 20×20", () => {
    fc.assert(
      fc.property(teamArbitrary, fc.boolean(), (team, isLeader) => {
        const row = buildTeamRow(team, isLeader);
        const img = row.querySelector("img");

        expect(img).not.toBeNull();
        expect(img.width).toBe(20);
        expect(img.height).toBe(20);
      }),
      { numRuns: 100 }
    );
  });

  it("conference header logos are 26×26", () => {
    fc.assert(
      fc.property(conferenceArbitrary, teamsArbitrary, (conf, teams) => {
        const divisions = { East: teams };
        const section = buildConferenceSection(conf, divisions);

        // The conference header img is a sibling of the <h2>, inside .mdn-conf-head
        const headerImg = section.querySelector(".mdn-conf-head img");

        expect(headerImg).not.toBeNull();
        expect(headerImg.width).toBe(26);
        expect(headerImg.height).toBe(26);
      }),
      { numRuns: 100 }
    );
  });

  it("navbar logo is 30×30", () => {
    // The navbar logo is static HTML set up in setup.js.
    // We verify it once — it's not generated dynamically, so a single
    // assertion suffices (no randomized input dimension).
    const navbarImg = document.querySelector("nav.mdn-nav img");

    expect(navbarImg).not.toBeNull();
    expect(navbarImg.getAttribute("width")).toBe("30");
    expect(navbarImg.getAttribute("height")).toBe("30");
  });
});
