/**
 * Test setup for frontend property-based and unit tests.
 *
 * Loads the app's JS files into the JSDOM environment so that
 * global functions (App, renderStandings, etc.) are available in tests.
 *
 * Bootstrap CSS is not loaded (no CDN in tests), but we verify class assignments
 * and DOM structure rather than computed styles.
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
    <nav class="navbar navbar-expand-lg navbar-dark sticky-top" style="background-color:#1b3a6b">
      <div class="container-xl">
        <a class="navbar-brand d-flex align-items-center gap-2" href="#standings">
          <img src="img/logos/nfl.png" alt="NFL" width="32" height="32">
          <span>NFL Monte Carlo Playoff Ranking Simulator</span>
          <span id="app-version" class="text-muted small ms-2"></span>
        </a>
        <div class="collapse navbar-collapse" id="navbarNav">
          <ul class="navbar-nav ms-auto">
            <li class="nav-item"><a class="nav-link active" aria-current="page" href="#standings">Standings</a></li>
            <li class="nav-item"><a class="nav-link" href="#statistics">Statistics</a></li>
            <li class="nav-item"><a class="nav-link" href="#results">Results</a></li>
          </ul>
        </div>
      </div>
    </nav>
    <div id="notification" class="container-xl mt-2 d-none" role="alert" aria-live="polite"></div>
    <div id="loading" class="d-none" aria-label="Loading"></div>
    <main id="content" class="container-xl py-4"></main>
  `;

  // Stub API module to prevent real network calls — assign BEFORE loading scripts
  globalThis.API = {
    fetchStatus: () => Promise.resolve({ version: "1.0.0", total_games: 0 }),
    getStandings: () => Promise.resolve({ conferences: {} }),
    fetchData: () => Promise.resolve({ games_fetched: 0 }),
    runSimulation: () => Promise.resolve({}),
    fetchCPClinchAll: () => Promise.resolve(null),
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
});

afterEach(() => {
  // Reset content area between tests
  const content = document.getElementById("content");
  if (content) content.innerHTML = "";

  // Reset notification
  const notification = document.getElementById("notification");
  if (notification) {
    notification.classList.add("d-none");
    notification.innerHTML = "";
  }

  // Reset loading
  const loading = document.getElementById("loading");
  if (loading) {
    loading.classList.add("d-none");
    loading.innerHTML = "";
  }
});
