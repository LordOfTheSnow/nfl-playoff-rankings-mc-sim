/**
 * Property 11: Game result tag indicators
 *
 * For any completed game rendered in the Team Detail schedule ledger, the
 * Result/Status cell SHALL contain a `.mdn-tag` element with the
 * Modernist-system variant class for its result — win → `mdn-tag-win-o`,
 * loss → `mdn-tag-elim` (shared with the Standings ELIMINATED badge), tie →
 * `mdn-tag-tie` — and the tag's text SHALL be the full word ("Win" / "Loss" /
 * "Tie"), not a single letter.
 *
 * **Validates: Requirements 8.5**
 */

import { describe, it, expect, beforeEach } from "vitest";
import fc from "fast-check";

/** Expected mapping from result to Modernist tag variant class */
const RESULT_TAG_CLASS_MAP = {
  win: "mdn-tag-win-o",
  loss: "mdn-tag-elim",
  tie: "mdn-tag-tie",
};

/** Expected mapping from result to full-word tag text */
const RESULT_TAG_TEXT_MAP = {
  win: "Win",
  loss: "Loss",
  tie: "Tie",
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

/** Arbitrary for a list of completed games (1 to 17 games), contiguous weeks starting at 1 */
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

/**
 * Extract the non-bye-week game rows from a rendered schedule tbody.
 * Bye rows have exactly 2 cells whose second cell carries the "mdn-bye" class.
 */
function gameRowsOf(tbody) {
  return Array.from(tbody.querySelectorAll("tr")).filter((row) => {
    const cells = row.querySelectorAll("td");
    return !(cells.length === 2 && cells[1].classList.contains("mdn-bye"));
  });
}

describe("Property 11: Game result tag indicators", () => {
  let contentEl;

  beforeEach(() => {
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
  });

  it("each completed game's Result/Status cell has the correct tag class and text for its result", () => {
    fc.assert(
      fc.property(arbScheduleData, (data) => {
        contentEl.innerHTML = "";
        renderScheduleContent(contentEl, data);

        const tbody = contentEl.querySelector("tbody");
        expect(tbody).not.toBeNull();

        const rows = gameRowsOf(tbody);
        expect(rows.length).toBe(data.games.length);

        rows.forEach((row, i) => {
          const game = data.games[i];
          const resultCell = row.querySelectorAll("td")[5];
          const tag = resultCell.querySelector(".mdn-tag");

          expect(tag).not.toBeNull();
          expect(tag.classList.contains(RESULT_TAG_CLASS_MAP[game.result])).toBe(true);
          expect(tag.textContent).toBe(RESULT_TAG_TEXT_MAP[game.result]);
        });
      }),
      { numRuns: 100 }
    );
  });

  it("win result always renders an 'mdn-tag-win-o' tag reading 'Win'", () => {
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
          for (const row of gameRowsOf(tbody)) {
            const tag = row.querySelectorAll("td")[5].querySelector(".mdn-tag");
            expect(tag.classList.contains("mdn-tag-win-o")).toBe(true);
            expect(tag.textContent).toBe("Win");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("loss result always renders an 'mdn-tag-elim' tag reading 'Loss'", () => {
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
          for (const row of gameRowsOf(tbody)) {
            const tag = row.querySelectorAll("td")[5].querySelector(".mdn-tag");
            expect(tag.classList.contains("mdn-tag-elim")).toBe(true);
            expect(tag.textContent).toBe("Loss");
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("tie result always renders an 'mdn-tag-tie' tag reading 'Tie'", () => {
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
          for (const row of gameRowsOf(tbody)) {
            const tag = row.querySelectorAll("td")[5].querySelector(".mdn-tag");
            expect(tag.classList.contains("mdn-tag-tie")).toBe(true);
            expect(tag.textContent).toBe("Tie");
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
