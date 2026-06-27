/**
 * Smoke test to verify the testing framework setup.
 * Confirms that vitest, jsdom, fast-check, and app JS modules are loaded correctly.
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

describe("Test framework setup", () => {
  it("jsdom provides document and window globals", () => {
    expect(document).toBeDefined();
    expect(window).toBeDefined();
    expect(document.getElementById("content")).not.toBeNull();
  });

  it("app JS modules are loaded in global scope", () => {
    expect(typeof App).toBe("object");
    expect(typeof App.showError).toBe("function");
    expect(typeof App.showLoading).toBe("function");
    expect(typeof App.navigate).toBe("function");
  });

  it("standings functions are available globally", () => {
    expect(typeof renderStandings).toBe("function");
    expect(typeof buildFilterBar).toBe("function");
    expect(typeof buildDivisionSection).toBe("function");
    expect(typeof buildTeamRow).toBe("function");
  });

  it("fast-check runs property tests with 100+ iterations", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 1000 }), (n) => {
        return n >= 1 && n <= 1000;
      }),
      { numRuns: 100 }
    );
  });

  it("fast-check integrates with vitest expect", () => {
    fc.assert(
      fc.property(fc.string(), (s) => {
        expect(typeof s).toBe("string");
        return true;
      }),
      { numRuns: 100 }
    );
  });
});
