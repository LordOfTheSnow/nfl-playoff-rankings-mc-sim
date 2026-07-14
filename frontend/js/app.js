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
 *   #simulate       — Simulation controls
 *   #results        — Simulation results
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

  // --- Notification timeout handle ---
  let notificationTimeout = null;

  /**
   * Display an error message in the notification area.
   * Renders a Bootstrap alert-danger dismissible alert.
   *
   * @param {string} message - The error message to display.
   */
  function showError(message) {
    if (!notificationEl) return;
    notificationEl.innerHTML =
      '<div class="alert alert-danger alert-dismissible fade show" role="alert">' +
      message +
      '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>' +
      '</div>';
    notificationEl.classList.remove("d-none");

    // Auto-hide after 8 seconds
    if (notificationTimeout) {
      clearTimeout(notificationTimeout);
    }
    notificationTimeout = setTimeout(() => {
      hideNotification();
    }, 8000);
  }

  /**
   * Display an informational message in the notification area.
   * Renders a Bootstrap alert-info dismissible alert.
   *
   * @param {string} message - The info message to display.
   */
  function showInfo(message) {
    if (!notificationEl) return;
    notificationEl.innerHTML =
      '<div class="alert alert-info alert-dismissible fade show" role="alert">' +
      message +
      '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>' +
      '</div>';
    notificationEl.classList.remove("d-none");

    if (notificationTimeout) {
      clearTimeout(notificationTimeout);
    }
    notificationTimeout = setTimeout(() => {
      hideNotification();
    }, 5000);
  }

  /**
   * Hide the notification area.
   */
  function hideNotification() {
    if (!notificationEl) return;
    notificationEl.classList.add("d-none");
    notificationEl.innerHTML = "";
    if (notificationTimeout) {
      clearTimeout(notificationTimeout);
      notificationTimeout = null;
    }
  }

  /**
   * Show the loading/progress indicator.
   * Renders a Bootstrap spinner-border inside a fixed overlay.
   */
  function showLoading() {
    if (!loadingEl) return;
    loadingEl.innerHTML =
      '<div class="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center" style="background:rgba(0,0,0,0.5);z-index:1055">' +
      '<div class="spinner-border text-primary" role="status">' +
      '<span class="visually-hidden">Loading…</span>' +
      '</div>' +
      '</div>';
    loadingEl.classList.remove("d-none");
  }

  /**
   * Hide the loading/progress indicator.
   */
  function hideLoading() {
    if (!loadingEl) return;
    loadingEl.classList.add("d-none");
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
    const knownRoutes = ["standings", "simulate", "results", "statistics", "schedule-grid"];
    if (knownRoutes.includes(hash)) {
      return { view: hash, param: null };
    }

    // Unknown hash — default to standings
    return { view: "standings", param: null };
  }

  /**
   * Update the active state of navigation links based on the current route.
   * Sets Bootstrap `active` class and `aria-current="page"` on the matching link.
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
          // Redirect to standings (controls are now there)
          App.navigate("standings");
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

        case "results":
          if (typeof renderResults === "function") {
            await renderResults(contentEl);
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
   * Initialize the application on DOMContentLoaded.
   * Resolves DOM references, sets up event listeners, and performs initial routing.
   */
  function init() {
    // Resolve DOM elements
    contentEl = document.getElementById("content");
    notificationEl = document.getElementById("notification");
    loadingEl = document.getElementById("loading");
    navLinks = document.querySelectorAll(".navbar-nav .nav-link");

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
  };
})();
