/**
 * Test setup for frontend property-based and unit tests.
 *
 * Loads the app's JS files into the JSDOM environment so that
 * global functions (App, renderStandings, etc.) are available in tests.
 *
 * styles.css is not loaded (no stylesheet in tests), but we verify class
 * assignments and DOM structure rather than computed styles.
 */

import { readFileSync } from "fs";
import { resolve } from "path";
import vm from "vm";
import { beforeAll, afterEach } from "vitest";

const JS_DIR = resolve(__dirname, "../js");

/**
 * Load a JS file by evaluating it in the global context.
 * This simulates how the browser loads script tags — top-level
 * const/let declarations become properties on globalThis.
 */
function loadScript(filename) {
  const code = readFileSync(resolve(JS_DIR, filename), "utf-8");
  // Remove "use strict"; to allow script-level declarations to bind globally,
  // then wrap in a way that exposes top-level const/let to globalThis.
  const wrappedCode = code.replace(/^"use strict";\s*/m, "");
  vm.runInThisContext(wrappedCode, { filename });
}

beforeAll(() => {
  // Set up minimal DOM structure matching index.html
  document.body.innerHTML = `
    <nav class="mdn-nav">
      <a class="mdn-brand" href="#standings">
        <img src="img/logos/nfl.png" alt="NFL" width="30" height="30">
        <span>NFL PLAYOFF RANKINGS SIM</span>
        <span id="app-version" class="mdn-brand-version"></span>
      </a>
      <div class="mdn-nav-links">
        <a href="#standings" data-view="standings" class="active" aria-current="page">Standings</a>
        <a href="#statistics" data-view="statistics">Statistics</a>
        <a href="#simulations" data-view="simulations">Simulations</a>
      </div>
    </nav>
    <div id="notification" class="mdn-container mdn-hidden" role="alert" aria-live="polite"></div>
    <div id="loading" class="mdn-hidden" aria-label="Loading"></div>
    <main id="content" class="mdn-container mdn-main"></main>
  `;

  // Stub API module to prevent real network calls — assign BEFORE loading scripts
  globalThis.API = {
    fetchStatus: () => Promise.resolve({ version: "1.0.0", total_games: 0 }),
    getStandings: () => Promise.resolve({ conferences: {} }),
    fetchData: () => Promise.resolve({ games_fetched: 0 }),
    startSimulation: () => Promise.resolve({ job_id: "test-job", status: "running" }),
    getSimulationStatus: () => Promise.resolve({ status: "completed", phase: "", progress_done: 0, progress_total: 0, result: {} }),
    cancelSimulation: () => Promise.resolve({ job_id: "test-job", status: "cancelled" }),
    fetchCPClinchAll: () => Promise.resolve(null),
    exportPage: () => Promise.resolve(new Blob(["<html></html>"], { type: "text/html" })),
    exportBundle: () => Promise.resolve(new Blob([], { type: "application/zip" })),
  };

  // Load app JS files in dependency order
  // api.js is stubbed above so we skip it to avoid overwriting our stub
  loadScript("app.js");
  loadScript("standings.js");
  loadScript("schedule.js");
  loadScript("schedule-grid.js");
  loadScript("simulation.js");
  loadScript("statistics.js");
  loadScript("charts.js");
  loadScript("export.js");
});

afterEach(() => {
  // Reset content area between tests
  const content = document.getElementById("content");
  if (content) content.innerHTML = "";

  // Reset notification
  const notification = document.getElementById("notification");
  if (notification) {
    notification.classList.add("mdn-hidden");
    notification.innerHTML = "";
  }

  // Reset loading
  const loading = document.getElementById("loading");
  if (loading) {
    loading.classList.add("mdn-hidden");
    loading.innerHTML = "";
  }
});
