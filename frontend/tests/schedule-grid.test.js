/**
 * Property Test: Grid table structural invariants
 *
 * **Validates: Requirements 3.1, 3.2, 3.8**
 *
 * // Feature: nfl-schedule-grid, Property 1: Grid table structural invariants
 *
 * For any valid schedule grid API response containing 32 team entries each
 * with 18 week slots, the rendered HTML table SHALL have exactly 1 <thead>
 * row with 19 <th> elements (each with scope="col"), and exactly 32 <tbody>
 * rows each containing 19 <td> elements, with the first cell in each row
 * having scope="row".
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

/**
 * All 32 NFL team names used to generate valid API responses.
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
 * Team name to abbreviation mapping (mirrors the one in schedule-grid.js).
 */
const ABBREVIATIONS = {
  "Bills": "BUF", "Dolphins": "MIA", "Patriots": "NE", "Jets": "NYJ",
  "Ravens": "BAL", "Bengals": "CIN", "Browns": "CLE", "Steelers": "PIT",
  "Texans": "HOU", "Colts": "IND", "Jaguars": "JAX", "Titans": "TEN",
  "Chiefs": "KC", "Broncos": "DEN", "Chargers": "LAC", "Raiders": "LV",
  "Cowboys": "DAL", "Eagles": "PHI", "Giants": "NYG", "Commanders": "WSH",
  "Bears": "CHI", "Lions": "DET", "Packers": "GB", "Vikings": "MIN",
  "Falcons": "ATL", "Panthers": "CAR", "Saints": "NO", "Buccaneers": "TB",
  "Cardinals": "ARI", "Rams": "LAR", "49ers": "SF", "Seahawks": "SEA",
};

// --- Arbitraries ---

/**
 * Generate a random weekly entry: either null (bye) or a game object.
 */
const weekEntryArbitrary = fc.oneof(
  fc.constant(null),
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.boolean(),
    status: fc.constantFrom("scheduled", "in-progress", "completed"),
    team_score: fc.oneof(fc.constant(null), fc.integer({ min: 0, max: 60 })),
    opponent_score: fc.oneof(fc.constant(null), fc.integer({ min: 0, max: 60 })),
  })
);

/**
 * Generate a valid schedule grid API response with exactly 32 teams,
 * each with exactly 18 week entries.
 */
const scheduleGridDataArbitrary = fc.tuple(
  ...TEAM_NAMES.map((teamName) =>
    fc.array(weekEntryArbitrary, { minLength: 18, maxLength: 18 }).map((weeks) => ({
      team: teamName,
      abbreviation: ABBREVIATIONS[teamName],
      weeks,
    }))
  )
).map((teams) => ({ teams }));

// --- Property Tests ---

describe("Property 1: Grid table structural invariants", () => {
  it("rendered table has 1 thead row with 19 th elements each with scope='col'", () => {
    fc.assert(
      fc.property(scheduleGridDataArbitrary, (data) => {
        const contentEl = document.createElement("div");
        renderGrid(contentEl, data);

        const table = contentEl.querySelector("table");
        expect(table).not.toBeNull();

        // Verify thead structure
        const thead = table.querySelector("thead");
        expect(thead).not.toBeNull();

        const headerRows = thead.querySelectorAll("tr");
        expect(headerRows.length).toBe(1);

        const thElements = headerRows[0].querySelectorAll("th");
        expect(thElements.length).toBe(19);

        // Every th must have scope="col"
        for (const th of thElements) {
          expect(th.getAttribute("scope")).toBe("col");
        }
      }),
      { numRuns: 100 }
    );
  });

  it("rendered table has 32 tbody rows each with 19 td elements, first td has scope='row'", () => {
    fc.assert(
      fc.property(scheduleGridDataArbitrary, (data) => {
        const contentEl = document.createElement("div");
        renderGrid(contentEl, data);

        const table = contentEl.querySelector("table");
        expect(table).not.toBeNull();

        // Verify tbody structure
        const tbody = table.querySelector("tbody");
        expect(tbody).not.toBeNull();

        const rows = tbody.querySelectorAll("tr");
        expect(rows.length).toBe(32);

        for (const row of rows) {
          const cells = row.querySelectorAll("td");
          expect(cells.length).toBe(19);

          // First cell must have scope="row"
          expect(cells[0].getAttribute("scope")).toBe("row");
        }
      }),
      { numRuns: 100 }
    );
  });
});


// Feature: nfl-schedule-grid, Property 3: Alphabetical sort order invariant

/**
 * Property 3: Alphabetical sort order invariant
 *
 * **Validates: Requirements 3.3**
 *
 * For any valid schedule grid response with teams in any order, the rendered
 * table rows SHALL be sorted in ascending alphabetical order by team abbreviation
 * (e.g., "ARI" before "ATL" before "BAL" ... before "WSH").
 */

// All 32 NFL teams with their abbreviations
const ALL_TEAMS = [
  { team: "Bills", abbreviation: "BUF" },
  { team: "Dolphins", abbreviation: "MIA" },
  { team: "Patriots", abbreviation: "NE" },
  { team: "Jets", abbreviation: "NYJ" },
  { team: "Ravens", abbreviation: "BAL" },
  { team: "Bengals", abbreviation: "CIN" },
  { team: "Browns", abbreviation: "CLE" },
  { team: "Steelers", abbreviation: "PIT" },
  { team: "Texans", abbreviation: "HOU" },
  { team: "Colts", abbreviation: "IND" },
  { team: "Jaguars", abbreviation: "JAX" },
  { team: "Titans", abbreviation: "TEN" },
  { team: "Chiefs", abbreviation: "KC" },
  { team: "Broncos", abbreviation: "DEN" },
  { team: "Chargers", abbreviation: "LAC" },
  { team: "Raiders", abbreviation: "LV" },
  { team: "Cowboys", abbreviation: "DAL" },
  { team: "Eagles", abbreviation: "PHI" },
  { team: "Giants", abbreviation: "NYG" },
  { team: "Commanders", abbreviation: "WSH" },
  { team: "Bears", abbreviation: "CHI" },
  { team: "Lions", abbreviation: "DET" },
  { team: "Packers", abbreviation: "GB" },
  { team: "Vikings", abbreviation: "MIN" },
  { team: "Falcons", abbreviation: "ATL" },
  { team: "Panthers", abbreviation: "CAR" },
  { team: "Saints", abbreviation: "NO" },
  { team: "Buccaneers", abbreviation: "TB" },
  { team: "Cardinals", abbreviation: "ARI" },
  { team: "Rams", abbreviation: "LAR" },
  { team: "49ers", abbreviation: "SF" },
  { team: "Seahawks", abbreviation: "SEA" },
];

/**
 * Generate a schedule grid API response with 32 teams in random (shuffled) order.
 * Each team has 18 week slots (all null/bye — sort order is independent of game data).
 */
const shuffledScheduleGridArbitrary = fc
  .shuffledSubarray(ALL_TEAMS, { minLength: 32, maxLength: 32 })
  .map((shuffledTeams) => ({
    teams: shuffledTeams.map((t) => ({
      team: t.team,
      abbreviation: t.abbreviation,
      weeks: Array(18).fill(null),
    })),
  }));

describe("Property 3: Alphabetical sort order invariant", () => {
  it("rendered rows are sorted ascending by abbreviation regardless of input order", () => {
    fc.assert(
      fc.property(shuffledScheduleGridArbitrary, (data) => {
        const contentEl = document.createElement("div");
        renderGrid(contentEl, data);

        // Extract the abbreviation text from each row's first cell (TEAM column)
        const rows = contentEl.querySelectorAll("tbody tr");
        const renderedAbbreviations = [];
        for (const row of rows) {
          const teamCell = row.querySelector("td");
          // The team cell contains a link with logo img + abbreviation text node
          const link = teamCell.querySelector("a");
          const textNodes = [];
          for (const node of link.childNodes) {
            if (node.nodeType === Node.TEXT_NODE) {
              textNodes.push(node.textContent.trim());
            }
          }
          renderedAbbreviations.push(textNodes.join(""));
        }

        // Verify ascending alphabetical order
        for (let i = 1; i < renderedAbbreviations.length; i++) {
          expect(
            renderedAbbreviations[i - 1].localeCompare(renderedAbbreviations[i])
          ).toBeLessThanOrEqual(0);
        }
      }),
      { numRuns: 100 }
    );
  });
});


// Feature: nfl-schedule-grid, Property 2: Cell content matches game type

/**
 * Property 2: Cell content matches game type (home/away/bye)
 *
 * **Validates: Requirements 3.5, 3.6, 3.7, 5.5**
 *
 * For any weekly entry in a schedule grid response: if the entry is null,
 * the corresponding cell SHALL display "BYE" with the text-muted CSS class;
 * if the entry has home=true, the cell SHALL display the opponent abbreviation
 * without an "@" prefix; if the entry has home=false, the cell SHALL display
 * the opponent abbreviation prefixed with exactly "@".
 */

/**
 * Generate a random weekly entry specifically for cell content testing:
 * null (bye), home game (home=true), or away game (home=false).
 * Uses "scheduled" status with null scores to isolate cell content behavior.
 */
const cellContentEntryArbitrary = fc.oneof(
  fc.constant(null),
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.constant(true),
    status: fc.constant("scheduled"),
    team_score: fc.constant(null),
    opponent_score: fc.constant(null),
  }),
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.constant(false),
    status: fc.constant("scheduled"),
    team_score: fc.constant(null),
    opponent_score: fc.constant(null),
  })
);

/**
 * Generate a full 18-week schedule array with random cell content entries.
 */
const cellContentWeeksArbitrary = fc.array(cellContentEntryArbitrary, { minLength: 18, maxLength: 18 });

describe("Property 2: Cell content matches game type", () => {
  it("null → BYE with text-muted class; home=true → abbreviation without @; home=false → abbreviation with @", () => {
    fc.assert(
      fc.property(cellContentWeeksArbitrary, (weeks) => {
        // Build a minimal grid with a single team using generated weeks
        const data = {
          teams: [{
            team: "Bills",
            abbreviation: "BUF",
            weeks,
          }],
        };

        const contentEl = document.createElement("div");
        renderGrid(contentEl, data);

        const row = contentEl.querySelector("tbody tr");
        const cells = row.querySelectorAll("td");

        // Week cells start at index 1 (index 0 is the TEAM column)
        for (let w = 0; w < 18; w++) {
          const cell = cells[w + 1];
          const entry = weeks[w];

          if (entry === null) {
            // Bye week: span with class "text-muted" and text "BYE"
            const byeSpan = cell.querySelector("span.text-muted");
            expect(byeSpan).not.toBeNull();
            expect(byeSpan.textContent).toBe("BYE");
          } else if (entry.home === true) {
            // Home game: opponent abbreviation WITHOUT "@" prefix
            expect(cell.textContent).toBe(entry.opponent);
            expect(cell.textContent.startsWith("@")).toBe(false);
          } else {
            // Away game: opponent abbreviation WITH "@" prefix
            expect(cell.textContent).toBe("@" + entry.opponent);
            expect(cell.textContent.startsWith("@")).toBe(true);
          }
        }
      }),
      { numRuns: 100 }
    );
  });
});


// Feature: nfl-schedule-grid, Property 4: Team column rendering (logo, abbreviation, link)

/**
 * Property 4: Team column rendering (logo, abbreviation, link)
 *
 * **Validates: Requirements 3.4, 4.1, 4.3**
 *
 * For any team entry in the schedule grid response, the "TEAM" column cell
 * SHALL contain: an <img> element with width=28 and height=28 for the team logo,
 * the team's uppercase abbreviation as visible text, and an <a> element whose
 * href attribute equals #team/<URI-encoded team_name>.
 */

/**
 * Generate a random subset of teams (at least 1) for team column testing.
 */
const teamSubsetArbitrary = fc.shuffledSubarray(ALL_TEAMS, { minLength: 1 });

/**
 * Build a minimal valid schedule grid API response from a team subset.
 * Each team gets 18 null weeks (all byes) to keep focus on team column rendering.
 */
function buildTeamColumnGridResponse(teams) {
  return {
    teams: teams.map((t) => ({
      team: t.team,
      abbreviation: t.abbreviation,
      weeks: Array(18).fill(null),
    })),
  };
}

describe("Property 4: Team column rendering (logo, abbreviation, link)", () => {
  it("each TEAM cell contains img (28x28), uppercase abbreviation, and correct link", () => {
    fc.assert(
      fc.property(teamSubsetArbitrary, (teamSubset) => {
        // Arrange: render the grid with the random team subset
        const contentEl = document.createElement("div");
        const data = buildTeamColumnGridResponse(teamSubset);
        renderGrid(contentEl, data);

        // The grid sorts by abbreviation — build expected order
        const sorted = teamSubset
          .slice()
          .sort((a, b) => a.abbreviation.localeCompare(b.abbreviation));

        // Get all data rows from tbody
        const rows = contentEl.querySelectorAll("tbody tr");
        expect(rows.length).toBe(sorted.length);

        for (let i = 0; i < sorted.length; i++) {
          const entry = sorted[i];
          const row = rows[i];
          const teamCell = row.querySelector("td");

          // 1. Contains an <img> with width=28, height=28
          const img = teamCell.querySelector("img");
          expect(img).not.toBeNull();
          expect(img.width).toBe(28);
          expect(img.height).toBe(28);

          // 2. Contains the team's uppercase abbreviation as visible text
          const cellText = teamCell.textContent;
          expect(cellText).toContain(entry.abbreviation);
          // Abbreviation should be uppercase
          expect(entry.abbreviation).toBe(entry.abbreviation.toUpperCase());

          // 3. Contains an <a> element with href matching #team/<URI-encoded team_name>
          const anchor = teamCell.querySelector("a");
          expect(anchor).not.toBeNull();
          const expectedHref = "#team/" + encodeURIComponent(entry.team);
          expect(anchor.getAttribute("href")).toBe(expectedHref);
        }
      }),
      { numRuns: 100 }
    );
  });
});


// Feature: nfl-schedule-grid, Property 6: Score display rules by game status

/**
 * Property 6: Score display rules by game status
 *
 * **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**
 *
 * For any non-null weekly entry rendered in the grid: if status is "completed"
 * and scores are present, the cell SHALL display the score in format
 * "TeamScore-OpponentScore" and the cell SHALL be a clickable link to
 * #team/<team_name>; if status is "in-progress" and scores are present, the cell
 * SHALL display the score in format "TeamScore-OpponentScore (r)" and the cell
 * SHALL be a clickable link; if status is "scheduled", the cell SHALL display
 * only the opponent abbreviation with no score text and no link.
 */

/**
 * Generate weekly entries with specific statuses and score combinations for
 * score display testing.
 */
const scoreEntryArbitrary = fc.oneof(
  // Completed with scores
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.boolean(),
    status: fc.constant("completed"),
    team_score: fc.integer({ min: 0, max: 60 }),
    opponent_score: fc.integer({ min: 0, max: 60 }),
  }),
  // In-progress with scores
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.boolean(),
    status: fc.constant("in-progress"),
    team_score: fc.integer({ min: 0, max: 60 }),
    opponent_score: fc.integer({ min: 0, max: 60 }),
  }),
  // Scheduled (no scores)
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.boolean(),
    status: fc.constant("scheduled"),
    team_score: fc.constant(null),
    opponent_score: fc.constant(null),
  }),
  // Completed/in-progress with missing scores
  fc.record({
    opponent: fc.constantFrom(...Object.values(ABBREVIATIONS)),
    home: fc.boolean(),
    status: fc.constantFrom("completed", "in-progress"),
    team_score: fc.constant(null),
    opponent_score: fc.constant(null),
  })
);

describe("Property 6: Score display rules by game status", () => {
  it("completed+scores → score displayed + link; in-progress+scores → score with (r) + link; scheduled → no score, no link", () => {
    fc.assert(
      fc.property(scoreEntryArbitrary, (entry) => {
        // Build a minimal grid with one team and one week entry
        const weeks = Array(18).fill(null);
        weeks[0] = entry;

        const data = {
          teams: [{
            team: "Bills",
            abbreviation: "BUF",
            weeks,
          }],
        };

        const contentEl = document.createElement("div");
        renderGrid(contentEl, data);

        const row = contentEl.querySelector("tbody tr");
        const cells = row.querySelectorAll("td");
        const cell = cells[1]; // First week cell (index 0 is TEAM column)

        const hasScores = entry.team_score != null && entry.opponent_score != null;

        if (entry.status === "completed" && hasScores) {
          // Should have a link
          const link = cell.querySelector("a");
          expect(link).not.toBeNull();
          expect(link.getAttribute("href")).toBe("#team/Bills");

          // Should display score in format "TeamScore-OpponentScore"
          const scoreText = entry.team_score + "-" + entry.opponent_score;
          expect(cell.textContent).toContain(scoreText);
          // Should NOT have "(r)" suffix
          expect(cell.textContent).not.toContain("(r)");
        } else if (entry.status === "in-progress" && hasScores) {
          // Should have a link
          const link = cell.querySelector("a");
          expect(link).not.toBeNull();
          expect(link.getAttribute("href")).toBe("#team/Bills");

          // Should display score with "(r)" suffix
          const scoreText = entry.team_score + "-" + entry.opponent_score + " (r)";
          expect(cell.textContent).toContain(scoreText);
        } else if (entry.status === "scheduled") {
          // No link, no score
          const link = cell.querySelector("a");
          expect(link).toBeNull();

          // Should only show opponent abbreviation (with or without @)
          const expectedText = entry.home ? entry.opponent : "@" + entry.opponent;
          expect(cell.textContent.trim()).toBe(expectedText);
        } else {
          // Completed/in-progress with missing scores — no link, just opponent
          const link = cell.querySelector("a");
          expect(link).toBeNull();

          const expectedText = entry.home ? entry.opponent : "@" + entry.opponent;
          expect(cell.textContent.trim()).toBe(expectedText);
        }
      }),
      { numRuns: 100 }
    );
  });
});
