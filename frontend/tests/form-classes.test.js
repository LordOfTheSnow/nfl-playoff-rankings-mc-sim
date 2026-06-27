/**
 * Property 4: Form element Bootstrap class assignment
 *
 * For any form element rendered within the Simulation Controls (buttons, number inputs,
 * range sliders, select dropdowns), the element SHALL have the correct Bootstrap class
 * for its type: `btn btn-primary` or `btn btn-secondary` for buttons, `form-control`
 * for text/number inputs, `form-range` for range inputs, and `form-select` for select elements.
 *
 * **Validates: Requirements 5.1, 5.2, 5.3**
 */

import { describe, it, expect, beforeEach } from "vitest";
import fc from "fast-check";

describe("Property 4: Form element Bootstrap class assignment", () => {
  let contentEl;

  beforeEach(async () => {
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
    // renderSimulation is async (calls API.fetchStatus which is stubbed)
    await renderSimulation(contentEl);
  });

  it("all number inputs have form-control class", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const inputs = contentEl.querySelectorAll('input[type="number"]');
        expect(inputs.length).toBeGreaterThan(0);
        for (const input of inputs) {
          expect(input.classList.contains("form-control")).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("all range inputs have form-range class", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const inputs = contentEl.querySelectorAll('input[type="range"]');
        expect(inputs.length).toBeGreaterThan(0);
        for (const input of inputs) {
          expect(input.classList.contains("form-range")).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("all select elements have form-select class", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const selects = contentEl.querySelectorAll("select");
        expect(selects.length).toBeGreaterThan(0);
        for (const select of selects) {
          expect(select.classList.contains("form-select")).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("all buttons have btn class with correct variant (primary or secondary)", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const buttons = contentEl.querySelectorAll("button");
        expect(buttons.length).toBeGreaterThan(0);
        for (const button of buttons) {
          expect(button.classList.contains("btn")).toBe(true);
          const hasPrimary = button.classList.contains("btn-primary");
          const hasSecondary = button.classList.contains("btn-secondary");
          expect(hasPrimary || hasSecondary).toBe(true);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("form element class assignment holds for arbitrary API status responses", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          version: fc.string({ minLength: 1, maxLength: 10 }),
          total_games: fc.nat({ max: 500 }),
          games_cached: fc.nat({ max: 500 }),
          cpu_count: fc.integer({ min: 1, max: 64 }),
          games_per_week: fc.dictionary(
            fc.integer({ min: 1, max: 18 }).map(String),
            fc.integer({ min: 1, max: 16 })
          ),
        }),
        async (status) => {
          // Override API stub with generated status
          const originalFetchStatus = API.fetchStatus;
          API.fetchStatus = () => Promise.resolve(status);

          contentEl.innerHTML = "";
          await renderSimulation(contentEl);

          // Verify number inputs
          const numberInputs = contentEl.querySelectorAll('input[type="number"]');
          for (const input of numberInputs) {
            expect(input.classList.contains("form-control")).toBe(true);
          }

          // Verify range inputs
          const rangeInputs = contentEl.querySelectorAll('input[type="range"]');
          for (const input of rangeInputs) {
            expect(input.classList.contains("form-range")).toBe(true);
          }

          // Verify selects
          const selects = contentEl.querySelectorAll("select");
          for (const select of selects) {
            expect(select.classList.contains("form-select")).toBe(true);
          }

          // Verify buttons
          const buttons = contentEl.querySelectorAll("button");
          for (const button of buttons) {
            expect(button.classList.contains("btn")).toBe(true);
            const hasPrimary = button.classList.contains("btn-primary");
            const hasSecondary = button.classList.contains("btn-secondary");
            expect(hasPrimary || hasSecondary).toBe(true);
          }

          // Restore stub
          API.fetchStatus = originalFetchStatus;
        }
      ),
      { numRuns: 100 }
    );
  });
});
