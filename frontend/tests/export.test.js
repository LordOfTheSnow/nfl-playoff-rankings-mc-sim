/**
 * Export view tests.
 *
 * Covers the payload-building contract with the backend export endpoints:
 * the last simulation result (window._simulationResults, if any) and the
 * app's current cutoff week must be forwarded verbatim, and a missing
 * simulation result must not block either export button.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach } from "vitest";

// jsdom doesn't implement the Blob URL API used by the download helper, and
// treats a real anchor click as page navigation (which it also doesn't
// implement) -- stub both, matching the download-trigger pattern used in
// real browsers without jsdom logging "not implemented" noise.
if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:mock-url";
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => {};
}
HTMLAnchorElement.prototype.click = function () {};

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("Export view", () => {
  let contentEl;
  let originalExportPage;
  let originalExportBundle;

  beforeAll(() => {
    // Trigger DOMContentLoaded so App.init() resolves notificationEl etc. —
    // needed here since this suite asserts on App.showError's output.
    document.dispatchEvent(new Event("DOMContentLoaded"));
  });

  beforeEach(() => {
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
    localStorage.clear();
    window._simulationResults = null;
    originalExportPage = API.exportPage;
    originalExportBundle = API.exportBundle;
  });

  afterEach(() => {
    API.exportPage = originalExportPage;
    API.exportBundle = originalExportBundle;
    localStorage.clear();
    window._simulationResults = null;
  });

  it("renders both export buttons and a note when no simulation has run", async () => {
    await renderExport(contentEl);
    expect(document.getElementById("export-page-btn")).toBeTruthy();
    expect(document.getElementById("export-bundle-btn")).toBeTruthy();
    expect(contentEl.textContent).toContain("No simulation results available yet");
  });

  it("mentions the last simulation run when one is available", async () => {
    window._simulationResults = { cutoff_week_used: 9, iterations_run: 5000, team_results: [] };
    await renderExport(contentEl);
    expect(contentEl.textContent).toContain("cutoff week 9");
    expect(contentEl.textContent).not.toContain("No simulation results available yet");
  });

  it("forwards the current simulation result and cutoff week when exporting a page", async () => {
    window._simulationResults = { cutoff_week_used: 9, iterations_run: 5000, team_results: [] };
    localStorage.setItem("sim-cutoff", "9");
    let capturedPayload = null;
    API.exportPage = (payload) => {
      capturedPayload = payload;
      return Promise.resolve(new Blob(["<html></html>"], { type: "text/html" }));
    };

    await renderExport(contentEl);
    document.getElementById("export-page-btn").click();
    await flush();

    expect(capturedPayload.simulation_result).toBe(window._simulationResults);
    expect(capturedPayload.cutoff_week).toBe(9);
  });

  it("still allows exporting the bundle when no simulation result exists", async () => {
    let capturedPayload = null;
    API.exportBundle = (payload) => {
      capturedPayload = payload;
      return Promise.resolve(new Blob([], { type: "application/zip" }));
    };

    await renderExport(contentEl);
    document.getElementById("export-bundle-btn").click();
    await flush();

    expect(capturedPayload).not.toBeNull();
    expect(capturedPayload.simulation_result).toBeNull();
    expect(capturedPayload.cutoff_week).toBeUndefined();
  });

  it("shows an error notification if the export request fails", async () => {
    API.exportPage = () => Promise.reject(new Error("Server error (HTTP 409)"));
    await renderExport(contentEl);
    document.getElementById("export-page-btn").click();
    await flush();

    const notification = document.getElementById("notification");
    expect(notification.textContent).toContain("Server error (HTTP 409)");
  });
});
