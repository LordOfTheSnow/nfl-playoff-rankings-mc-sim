/**
 * Property 4: Form element Modernist class assignment
 *
 * For any form element rendered within the Standings page's "Simulation"
 * card (buttons, number inputs, range sliders, select dropdowns), the
 * element SHALL have the correct Modernist design-system class for its
 * type: `mdn-btn` + `mdn-btn-primary`/`mdn-btn-secondary` for buttons,
 * `mdn-input` for text/number inputs, range inputs, and select elements.
 *
 * The simulation controls used to live on a standalone Bootstrap-styled
 * `#simulate` view (`renderSimulation` in simulation.js); that view was
 * removed as dead code once Standings absorbed the controls in Modernist
 * style, so this test now targets `renderStandings` instead.
 *
 * **Validates: Requirements 5.1, 5.2, 5.3**
 */

import { describe, it, expect, beforeEach } from "vitest";
import fc from "fast-check";

/** A status response with enough data fetched to render the Simulation card (see buildStatusPanel in standings.js — it renders a "Fetch data" empty state instead when total_games is 0). */
const baseStatus = {
  version: "1.0.0",
  season_year: 2025,
  total_games: 200,
  games_cached: 200,
  expected_total: 272,
  completed: 150,
  weeks_fetched: 16,
  weeks_completed: 15,
  cpu_count: 8,
  games_per_week: { 16: 16, 17: 16, 18: 16 },
};

describe("Property 4: Form element Modernist class assignment", () => {
  let contentEl;
  let originalFetchStatus;

  beforeEach(async () => {
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
    originalFetchStatus = API.fetchStatus;
    API.fetchStatus = () => Promise.resolve(baseStatus);
    await renderStandings(contentEl);
  });

  it("all number inputs have mdn-input class", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const inputs = contentEl.querySelectorAll('input[type="number"]');
        expect(inputs.length).toBeGreaterThan(0);
        for (const input of inputs) {
          expect(input.classList.contains("mdn-input")).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("all range inputs have mdn-input class", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const inputs = contentEl.querySelectorAll('input[type="range"]');
        expect(inputs.length).toBeGreaterThan(0);
        for (const input of inputs) {
          expect(input.classList.contains("mdn-input")).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("all select elements have mdn-input class", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const selects = contentEl.querySelectorAll("select");
        expect(selects.length).toBeGreaterThan(0);
        for (const select of selects) {
          expect(select.classList.contains("mdn-input")).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("all buttons have mdn-btn class with correct variant (primary or secondary)", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const buttons = contentEl.querySelectorAll("button");
        expect(buttons.length).toBeGreaterThan(0);
        for (const button of buttons) {
          expect(button.classList.contains("mdn-btn")).toBe(true);
          const hasPrimary = button.classList.contains("mdn-btn-primary");
          const hasSecondary = button.classList.contains("mdn-btn-secondary");
          expect(hasPrimary || hasSecondary).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("form element class assignment holds for arbitrary (data-fetched) API status responses", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          version: fc.string({ minLength: 1, maxLength: 10 }),
          season_year: fc.integer({ min: 2000, max: 2100 }),
          total_games: fc.integer({ min: 1, max: 272 }),
          games_cached: fc.nat({ max: 272 }),
          expected_total: fc.integer({ min: 1, max: 272 }),
          completed: fc.nat({ max: 272 }),
          weeks_fetched: fc.integer({ min: 1, max: 18 }),
          weeks_completed: fc.integer({ min: 0, max: 18 }),
          cpu_count: fc.integer({ min: 1, max: 64 }),
          games_per_week: fc.dictionary(
            fc.integer({ min: 1, max: 18 }).map(String),
            fc.integer({ min: 1, max: 16 })
          ),
        }),
        async (status) => {
          API.fetchStatus = () => Promise.resolve(status);

          contentEl.innerHTML = "";
          await renderStandings(contentEl);

          const numberInputs = contentEl.querySelectorAll('input[type="number"]');
          for (const input of numberInputs) {
            expect(input.classList.contains("mdn-input")).toBe(true);
          }

          const rangeInputs = contentEl.querySelectorAll('input[type="range"]');
          for (const input of rangeInputs) {
            expect(input.classList.contains("mdn-input")).toBe(true);
          }

          const selects = contentEl.querySelectorAll("select");
          for (const select of selects) {
            expect(select.classList.contains("mdn-input")).toBe(true);
          }

          const buttons = contentEl.querySelectorAll("button");
          for (const button of buttons) {
            expect(button.classList.contains("mdn-btn")).toBe(true);
            const hasPrimary = button.classList.contains("mdn-btn-primary");
            const hasSecondary = button.classList.contains("mdn-btn-secondary");
            expect(hasPrimary || hasSecondary).toBe(true);
          }
        }
      ),
      { numRuns: 100 }
    );

    // Restore stub for any tests that run after this one
    API.fetchStatus = originalFetchStatus;
  });
});
