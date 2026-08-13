/**
 * Property 5: Label-input association
 *
 * For any label element rendered in the Simulations page's "Simulation" card
 * that has a `for` attribute, there SHALL exist an input/select element
 * whose `id` attribute matches the label's `for` value.
 *
 * The simulation controls used to live on a standalone Bootstrap-styled
 * `#simulate` view (`renderSimulation` in simulation.js), then moved onto
 * Standings during the Modernist redesign; the Simulation Flow Restructure
 * (design_handoff_simulation_flow_v2/) moved them again, onto the renamed
 * Simulations page (`renderSimulations`), so this test now targets that.
 *
 * **Validates: Requirements 5.6**
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

/** A status response with enough data fetched to render the Simulation card. */
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

describe("Property 5: Label-input association", () => {
  it("all labels with `for` attribute have a matching input/select/textarea element", async () => {
    const originalFetchStatus = API.fetchStatus;
    API.fetchStatus = () => Promise.resolve(baseStatus);

    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 200 }), async (_iteration) => {
        const contentEl = document.getElementById("content");
        contentEl.innerHTML = "";
        await renderSimulations(contentEl);

        const labels = contentEl.querySelectorAll("label[for]");

        // There must be at least one label (sanity check)
        expect(labels.length).toBeGreaterThan(0);

        for (const label of labels) {
          const forValue = label.getAttribute("for");

          expect(forValue).toBeTruthy();

          const target = document.getElementById(forValue);
          expect(target).not.toBeNull();

          const tagName = target.tagName.toLowerCase();
          expect(["input", "select", "textarea"]).toContain(tagName);
        }
      }),
      { numRuns: 100 }
    );

    API.fetchStatus = originalFetchStatus;
  });

  it("each label `for` value is unique (no duplicate associations)", async () => {
    const originalFetchStatus = API.fetchStatus;
    API.fetchStatus = () => Promise.resolve(baseStatus);

    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 200 }), async (_iteration) => {
        const contentEl = document.getElementById("content");
        contentEl.innerHTML = "";
        await renderSimulations(contentEl);

        const labels = contentEl.querySelectorAll("label[for]");
        const forValues = Array.from(labels).map((l) => l.getAttribute("for"));

        const uniqueValues = new Set(forValues);
        expect(uniqueValues.size).toBe(forValues.length);
      }),
      { numRuns: 100 }
    );

    API.fetchStatus = originalFetchStatus;
  });

  it("every form control with an id has a corresponding label", async () => {
    const originalFetchStatus = API.fetchStatus;
    API.fetchStatus = () => Promise.resolve(baseStatus);

    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 200 }), async (_iteration) => {
        const contentEl = document.getElementById("content");
        contentEl.innerHTML = "";
        await renderSimulations(contentEl);

        // Get all form controls with ids (excluding buttons)
        const controls = contentEl.querySelectorAll(
          "input[id], select[id], textarea[id]"
        );

        for (const control of controls) {
          const id = control.getAttribute("id");
          const label = contentEl.querySelector(`label[for="${id}"]`);
          expect(label).not.toBeNull();
        }
      }),
      { numRuns: 100 }
    );

    API.fetchStatus = originalFetchStatus;
  });
});
