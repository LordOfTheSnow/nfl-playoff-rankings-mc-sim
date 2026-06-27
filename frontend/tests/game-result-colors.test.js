/**
 * Property 11: Game result color indicators
 *
 * For any game result cell rendered in the schedule view, the text color SHALL be
 * #16a34a for wins, #e63946 for losses, and #d97706 for ties.
 *
 * Since JSDOM doesn't compute CSS, we verify CSS class assignment:
 * - win → game-result--win (maps to color: #16a34a)
 * - loss → game-result--loss (maps to color: #e63946)
 * - tie → game-result--tie (maps to color: #d97706)
 *
 * **Validates: Requirements 8.5**
 */

import { describe, it, expect, beforeEach } from "vitest";
import fc from "fast-check";

/** Expected mapping from result to CSS class */
const RESULT_CLASS_MAP = {
  win: "game-result--win",
  loss: "game-result--loss",
  tie: "game-result--tie",
};

/** Arbitrary for NFL team names */
const arbTeamName = fc.constantFrom(
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WSH"
);

/** Arbitrary for a game result */
const arbResult = fc.constantFrom("win", "loss", "tie");

/** Arbitrary for a completed game */
const arbCompletedGame = fc.record({
  week: fc.integer({ min: 1, max: 18 }),
  opponent: arbTeamName,
  home: fc.boolean(),
  status: fc.constant("completed"),
  result: arbResult,
  home_score: fc.integer({ min: 0, max: 60 }),
  away_score: fc.integer({ min: 0, max: 60 }),
  opponent_strength: fc.double({ min: 0, max: 1, noNaN: true }),
});

/** Arbitrary for a list of completed games (1 to 17 games) */
const arbCompletedGames = fc.array(arbCompletedGame, { minLength: 1, maxLength: 17 })
  .map((games) => games.map((g, i) => ({ ...g, week: i + 1 })));

/** Arbitrary for schedule data with only completed games */
const arbScheduleData = fc.record({
  team: arbTeamName,
  record: fc.record({
    wins: fc.integer({ min: 0, max: 17 }),
    losses: fc.integer({ min: 0, max: 17 }),
    ties: fc.integer({ min: 0, max: 17 }),
    win_percentage: fc.double({ min: 0, max: 1, noNaN: true }),
  }),
  games: arbCompletedGames,
});

describe("Property 11: Game result color indicators", () => {
  let contentEl;

  beforeEach(() => {
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
  });

  it("each completed game result cell has the correct CSS class for its result type", () => {
    fc.assert(
      fc.property(arbScheduleData, (data) => {
        contentEl.innerHTML = "";
        renderScheduleContent(contentEl, data);

        // Get all table body rows (excluding header and bye week rows)
        const tbody = contentEl.querySelector("tbody");
        expect(tbody).not.toBeNull();

        const rows = tbody.querySelectorAll("tr");
        let gameRowIndex = 0;

        for (const row of rows) {
          const cells = row.querySelectorAll("td");
          // Bye week rows have a cell with colSpan=5, skip them
          if (cells.length === 2 && cells[1].colSpan === 5) {
            continue;
          }

          // This is a game row — the 6th cell (index 5) is the result cell
          const resultCell = cells[5];
          const game = data.games[gameRowIndex];

          expect(resultCell.className).toBe(RESULT_CLASS_MAP[game.result]);
          gameRowIndex++;
        }

        // Ensure we checked all games
        expect(gameRowIndex).toBe(data.games.length);
      }),
      { numRuns: 100 }
    );
  });

  it("win result always maps to game-result--win class", () => {
    fc.assert(
      fc.property(
        fc.record({
          week: fc.integer({ min: 1, max: 18 }),
          opponent: arbTeamName,
          home: fc.boolean(),
          home_score: fc.integer({ min: 0, max: 60 }),
          away_score: fc.integer({ min: 0, max: 60 }),
          opponent_strength: fc.double({ min: 0, max: 1, noNaN: true }),
        }),
        (gameProps) => {
          const scheduleData = {
            team: "BUF",
            record: { wins: 1, losses: 0, ties: 0, win_percentage: 1.0 },
            games: [{ ...gameProps, status: "completed", result: "win" }],
          };

          contentEl.innerHTML = "";
          renderScheduleContent(contentEl, scheduleData);

          const tbody = contentEl.querySelector("tbody");
          const rows = tbody.querySelectorAll("tr");
          // Find the game row (skip potential bye week rows)
          for (const row of rows) {
            const cells = row.querySelectorAll("td");
            if (cells.length === 2 && cells[1].colSpan === 5) continue;
            expect(cells[5].className).toBe("game-result--win");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("loss result always maps to game-result--loss class", () => {
    fc.assert(
      fc.property(
        fc.record({
          week: fc.integer({ min: 1, max: 18 }),
          opponent: arbTeamName,
          home: fc.boolean(),
          home_score: fc.integer({ min: 0, max: 60 }),
          away_score: fc.integer({ min: 0, max: 60 }),
          opponent_strength: fc.double({ min: 0, max: 1, noNaN: true }),
        }),
        (gameProps) => {
          const scheduleData = {
            team: "BUF",
            record: { wins: 0, losses: 1, ties: 0, win_percentage: 0.0 },
            games: [{ ...gameProps, status: "completed", result: "loss" }],
          };

          contentEl.innerHTML = "";
          renderScheduleContent(contentEl, scheduleData);

          const tbody = contentEl.querySelector("tbody");
          const rows = tbody.querySelectorAll("tr");
          for (const row of rows) {
            const cells = row.querySelectorAll("td");
            if (cells.length === 2 && cells[1].colSpan === 5) continue;
            expect(cells[5].className).toBe("game-result--loss");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("tie result always maps to game-result--tie class", () => {
    fc.assert(
      fc.property(
        fc.record({
          week: fc.integer({ min: 1, max: 18 }),
          opponent: arbTeamName,
          home: fc.boolean(),
          home_score: fc.integer({ min: 0, max: 60 }),
          away_score: fc.integer({ min: 0, max: 60 }),
          opponent_strength: fc.double({ min: 0, max: 1, noNaN: true }),
        }),
        (gameProps) => {
          const scheduleData = {
            team: "BUF",
            record: { wins: 0, losses: 0, ties: 1, win_percentage: 0.0 },
            games: [{ ...gameProps, status: "completed", result: "tie" }],
          };

          contentEl.innerHTML = "";
          renderScheduleContent(contentEl, scheduleData);

          const tbody = contentEl.querySelector("tbody");
          const rows = tbody.querySelectorAll("tr");
          for (const row of rows) {
            const cells = row.querySelectorAll("td");
            if (cells.length === 2 && cells[1].colSpan === 5) continue;
            expect(cells[5].className).toBe("game-result--tie");
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
