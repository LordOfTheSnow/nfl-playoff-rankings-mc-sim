/**
 * Main application logic for the NFL Monte Carlo Playoff Simulator.
 *
 * Implements hash-based SPA routing, navigation state management,
 * global error/loading display, and view switching.
 *
 * Routes:
 *   #standings      — Standings view (default)
 *   #team/<name>    — Team schedule view
 *   #schedule-grid  — League-wide schedule grid
 *   #simulate       — Redirects to #simulations (legacy alias)
 *   #results        — Redirects to #simulations (legacy alias)
 *   #simulations    — Simulation setup + results (owns the sim controls)
 *   #export         — Export current data to standalone HTML
 *   #settings       — Settings / Info (database & runtime environment)
 *
 * Requirements: 11.3, 11.4, 11.6
 */

"use strict";

const App = (() => {
  // --- DOM element references (resolved on DOMContentLoaded) ---
  let contentEl = null;
  let notificationEl = null;
  let loadingEl = null;
  let navLinks = null;
  let footerEl = null;

  // Views whose render function already renders its own Modernist-styled
  // "Back to top" link — the app-wide footer link would otherwise duplicate it.
  const VIEWS_WITH_OWN_BACK_TO_TOP = new Set(["team", "statistics", "schedule-grid"]);

  // --- Notification timeout handle ---
  let notificationTimeout = null;

  /**
   * Render a dismissible Modernist alert into the notification area.
   *
   * @param {string} variant - "danger" or "info".
   * @param {string} message - The message to display.
   * @param {number} autoHideMs - Milliseconds before auto-dismissing.
   */
  function _renderAlert(variant, message, autoHideMs) {
    if (!notificationEl) return;
    notificationEl.innerHTML =
      '<div class="mdn-alert mdn-alert-' + variant + '" role="alert">' +
      message +
      '<button type="button" class="mdn-alert-close" aria-label="Close">' +
      '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>' +
      '</button>' +
      '</div>';
    notificationEl.classList.remove("mdn-hidden");

    const closeBtn = notificationEl.querySelector(".mdn-alert-close");
    if (closeBtn) closeBtn.addEventListener("click", hideNotification);

    if (notificationTimeout) {
      clearTimeout(notificationTimeout);
    }
    notificationTimeout = setTimeout(() => {
      hideNotification();
    }, autoHideMs);
  }

  /**
   * Display an error message in the notification area.
   *
   * @param {string} message - The error message to display.
   */
  function showError(message) {
    _renderAlert("danger", message, 8000);
  }

  /**
   * Display an informational message in the notification area.
   *
   * @param {string} message - The info message to display.
   */
  function showInfo(message) {
    _renderAlert("info", message, 5000);
  }

  /**
   * Hide the notification area.
   */
  function hideNotification() {
    if (!notificationEl) return;
    notificationEl.classList.add("mdn-hidden");
    notificationEl.innerHTML = "";
    if (notificationTimeout) {
      clearTimeout(notificationTimeout);
      notificationTimeout = null;
    }
  }

  /**
   * Show the loading/progress indicator.
   */
  function showLoading() {
    if (!loadingEl) return;
    loadingEl.innerHTML =
      '<div class="mdn-loading-overlay">' +
      '<span class="mdn-spinner mdn-spinner-lg" role="status"></span>' +
      '<span class="mdn-visually-hidden">Loading…</span>' +
      '</div>';
    loadingEl.classList.remove("mdn-hidden");
  }

  /**
   * Hide the loading/progress indicator.
   */
  function hideLoading() {
    if (!loadingEl) return;
    loadingEl.classList.add("mdn-hidden");
    loadingEl.innerHTML = "";
  }

  /**
   * Parse the current location hash into a route object.
   *
   * @returns {{view: string, param: string|null}} The parsed route.
   */
  function parseHash() {
    const hash = window.location.hash.replace(/^#/, "") || "standings";

    if (hash.startsWith("team/")) {
      const teamName = decodeURIComponent(hash.slice(5));
      return { view: "team", param: teamName };
    }

    // Known routes
    const knownRoutes = ["standings", "simulate", "results", "simulations", "statistics", "schedule-grid", "export", "settings"];
    if (knownRoutes.includes(hash)) {
      return { view: hash, param: null };
    }

    // Unknown hash — default to standings
    return { view: "standings", param: null };
  }

  /**
   * Update the active state of navigation links based on the current route.
   * Sets the `active` class and `aria-current="page"` on the matching link.
   *
   * @param {string} activeView - The current view name.
   */
  function updateNavActive(activeView) {
    if (!navLinks) return;
    navLinks.forEach((link) => {
      const href = link.getAttribute("href") || "";
      const linkView = href.replace(/^#/, "") || "standings";

      if (linkView === activeView) {
        link.classList.add("active");
        link.setAttribute("aria-current", "page");
      } else {
        link.classList.remove("active");
        link.removeAttribute("aria-current");
      }
    });
  }

  /**
   * Route to the appropriate view based on the current hash.
   * Calls the corresponding render function (defined in separate files).
   */
  async function route() {
    const { view, param } = parseHash();
    updateNavActive(view);
    hideNotification();
    if (footerEl) {
      footerEl.hidden = VIEWS_WITH_OWN_BACK_TO_TOP.has(view);
    }

    try {
      switch (view) {
        case "standings":
          if (typeof renderStandings === "function") {
            await renderStandings(contentEl);
          }
          break;

        case "team":
          if (typeof renderSchedule === "function") {
            await renderSchedule(contentEl, param);
          }
          break;

        case "simulate":
          // Legacy alias — controls live on the Simulations page now.
          App.navigate("simulations");
          break;

        case "results":
          // Legacy alias — the "Results" page was renamed to "Simulations".
          App.navigate("simulations");
          break;

        case "schedule-grid":
          if (typeof renderScheduleGrid === "function") {
            await renderScheduleGrid(contentEl);
          }
          break;

        case "statistics":
          if (typeof renderStatistics === "function") {
            await renderStatistics(contentEl);
          }
          break;

        case "simulations":
          if (typeof renderSimulations === "function") {
            await renderSimulations(contentEl);
          }
          break;

        case "export":
          if (typeof renderExport === "function") {
            await renderExport(contentEl);
          }
          break;

        case "settings":
          if (typeof renderSettings === "function") {
            await renderSettings(contentEl);
          }
          break;

        default:
          if (typeof renderStandings === "function") {
            await renderStandings(contentEl);
          }
          break;
      }
    } catch (err) {
      showError(err.message || "An unexpected error occurred.");
    }
  }

  /**
   * Navigate to a specific hash route programmatically.
   *
   * @param {string} hash - The hash to navigate to (without #).
   */
  function navigate(hash) {
    window.location.hash = hash;
  }

  /**
   * Read the app-level cutoff-week value, shared and persisted across the
   * Standings and Simulations pages.
   *
   * @returns {string|null} The saved cutoff week ("" = Auto), or null if unset.
   */
  function getCutoffWeek() {
    return localStorage.getItem("sim-cutoff");
  }

  /**
   * Persist the app-level cutoff-week value. Changing the cutoff invalidates
   * any existing simulation results (they were computed for the old cutoff),
   * so this also clears the in-memory results cache. Callers are responsible
   * for re-rendering their own page afterward.
   *
   * @param {string} value - The new cutoff week ("" for Auto).
   */
  function setCutoffWeek(value) {
    localStorage.setItem("sim-cutoff", value);
    window._simulationResults = null;
  }

  /**
   * Initialize the application on DOMContentLoaded.
   * Resolves DOM references, sets up event listeners, and performs initial routing.
   */
  function init() {
    // Resolve DOM elements
    contentEl = document.getElementById("content");
    notificationEl = document.getElementById("notification");
    loadingEl = document.getElementById("loading");
    navLinks = document.querySelectorAll(".mdn-nav-links a[data-view]");
    footerEl = document.getElementById("app-footer");

    // Listen for hash changes
    window.addEventListener("hashchange", route);

    // Display version and initialize season selector from server
    API.fetchStatus().then(status => {
      const versionEl = document.getElementById("app-version");
      if (versionEl && status && status.version) {
        versionEl.textContent = "v" + status.version;
      }
      if (status && status.season_year) {
        initSeasonSelector(status.season_year);
      }
    }).catch(() => {
      // Fallback: populate season selector with current year
      initSeasonSelector(new Date().getFullYear());
    });

    // Initial route
    route();
  }

  /**
   * Initialize the season selector dropdown with year options and wire up change handler.
   *
   * @param {number} activeSeason - The currently active season year on the server.
   */
  function initSeasonSelector(activeSeason) {
    const selector = document.getElementById("season-selector");
    if (!selector) return;

    // Populate options: current year down to 2020
    const currentYear = new Date().getFullYear();
    const startYear = Math.max(activeSeason, currentYear);
    selector.innerHTML = "";
    for (let y = startYear; y >= 2020; y--) {
      const opt = document.createElement("option");
      opt.value = y;
      opt.textContent = y;
      if (y === activeSeason) opt.selected = true;
      selector.appendChild(opt);
    }

    // Handle season change
    selector.addEventListener("change", async () => {
      const newSeason = parseInt(selector.value, 10);
      try {
        await API.setSeason(newSeason);
        showInfo("Season changed to " + newSeason + ". Click Fetch Data to load this season's games.");
        // Re-route to refresh the current view with new season context
        await route();
      } catch (err) {
        showError(err.message || "Failed to change season.");
        // Revert selector to previous value
        API.fetchStatus().then(s => { if (s) selector.value = s.season_year; }).catch(() => {});
      }
    });
  }

  // Initialize on DOMContentLoaded
  document.addEventListener("DOMContentLoaded", init);

  // Public API
  return {
    showError,
    showInfo,
    hideNotification,
    showLoading,
    hideLoading,
    navigate,
    route,
    getCutoffWeek,
    setCutoffWeek,
  };
})();
