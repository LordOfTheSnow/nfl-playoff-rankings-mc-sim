/**
 * Property 5: Label-input association
 *
 * For any label element rendered in the Simulation Controls that has a `for`
 * attribute, there SHALL exist an input element whose `id` attribute matches
 * the label's `for` value.
 *
 * **Validates: Requirements 5.6**
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

describe("Property 5: Label-input association", () => {
  it("all labels with `for` attribute have a matching input/select/textarea element", async () => {
    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 200 }), async (_iteration) => {
        // Render simulation controls into a fresh container
        const contentEl = document.getElementById("content");
        contentEl.innerHTML = "";
        await renderSimulation(contentEl);

        // Gather all labels with a `for` attribute
        const labels = contentEl.querySelectorAll("label[for]");

        // There must be at least one label (sanity check)
        expect(labels.length).toBeGreaterThan(0);

        for (const label of labels) {
          const forValue = label.getAttribute("for");

          // The `for` attribute must be non-empty
          expect(forValue).toBeTruthy();

          // A matching element with that id must exist in the document
          const target = document.getElementById(forValue);
          expect(target).not.toBeNull();

          // The target must be a form control element (input, select, or textarea)
          const tagName = target.tagName.toLowerCase();
          expect(["input", "select", "textarea"]).toContain(tagName);
        }
      }),
      { numRuns: 100 }
    );
  });

  it("each label `for` value is unique (no duplicate associations)", async () => {
    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 200 }), async (_iteration) => {
        const contentEl = document.getElementById("content");
        contentEl.innerHTML = "";
        await renderSimulation(contentEl);

        const labels = contentEl.querySelectorAll("label[for]");
        const forValues = Array.from(labels).map((l) => l.getAttribute("for"));

        // All for values should be unique
        const uniqueValues = new Set(forValues);
        expect(uniqueValues.size).toBe(forValues.length);
      }),
      { numRuns: 100 }
    );
  });

  it("every form control with an id has a corresponding label", async () => {
    await fc.assert(
      fc.asyncProperty(fc.integer({ min: 1, max: 200 }), async (_iteration) => {
        const contentEl = document.getElementById("content");
        contentEl.innerHTML = "";
        await renderSimulation(contentEl);

        // Get all form controls with ids (excluding buttons)
        const controls = contentEl.querySelectorAll(
          "input[id], select[id], textarea[id]"
        );

        for (const control of controls) {
          const id = control.getAttribute("id");
          // Find label with for=<id>
          const label = contentEl.querySelector(`label[for="${id}"]`);
          expect(label).not.toBeNull();
        }
      }),
      { numRuns: 100 }
    );
  });
});
