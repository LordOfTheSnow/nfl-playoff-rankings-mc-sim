/**
 * REST API client for the NFL Monte Carlo Playoff Simulator.
 *
 * All functions use the Fetch API, return parsed JSON on success,
 * and throw an Error with the server's error message on failure.
 * Base URL is relative (same origin).
 *
 * Requirements: 11.3, 11.4
 */

"use strict";

const API = (() => {
  /**
   * Internal helper: perform a fetch request and handle JSON responses/errors.
   *
   * @param {string} url - Relative URL path (e.g., "/api/status").
   * @param {RequestInit} [options] - Fetch options (method, body, headers).
   * @returns {Promise<Object>} Parsed JSON response data.
   * @throws {Error} With the server's error message if the response is not ok.
   */
  async function request(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (networkError) {
      throw new Error("Network error: unable to reach the server.");
    }

    let data;
    try {
      data = await response.json();
    } catch (parseError) {
      if (!response.ok) {
        throw new Error(`Server error (HTTP ${response.status})`);
      }
      throw new Error("Invalid JSON response from server.");
    }

    if (!response.ok) {
      const message = data.message || `Server error (HTTP ${response.status})`;
      throw new Error(message);
    }

    return data;
  }

  /**
   * Fetch the current cache/application status.
   * GET /api/status
   *
   * @returns {Promise<{last_fetch_time: string|null, games_cached: number, season_year: number}>}
   */
  function fetchStatus() {
    return request("/api/status");
  }

  /**
   * Trigger a data fetch from the ESPN API.
   * POST /api/fetch-data
   *
   * @returns {Promise<{games_fetched: number, warnings: string[]}>}
   */
  function fetchData() {
    return request("/api/fetch-data", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
  }

  /**
   * Run a Monte Carlo simulation.
   * POST /api/simulate
   *
   * @param {number} iterations - Number of simulation trials (100–1,000,000).
   * @param {number|null} cutoffWeek - Cutoff week (1–18) or null for auto-detect.
   * @param {number|null} noise - Per-game strength noise (0.0–1.0) or null for default.
   * @param {number|null} numWorkers - Number of parallel workers or null for auto-detect.
   * @returns {Promise<Object>} Simulation results (team_results, scenarios, etc.).
   */
  function runSimulation(iterations, cutoffWeek, noise, numWorkers) {
    const body = { iterations };
    if (cutoffWeek != null) {
      body.cutoff_week = cutoffWeek;
    }
    if (noise != null) {
      body.noise = noise;
    }
    if (numWorkers != null) {
      body.num_workers = numWorkers;
    }
    return request("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  /**
   * Get current NFL standings computed from cached data.
   * GET /api/standings
   *
   * @returns {Promise<{standings: Object[], bracket: Object}>}
   */
  function getStandings() {
    return request("/api/standings");
  }

  /**
   * Get a specific team's schedule (all games).
   * GET /api/team/<name>
   *
   * @param {string} name - Team name (e.g., "Bills", "Chiefs").
   * @returns {Promise<{team: string, games: Object[], record: Object}>}
   */
  function getTeamSchedule(name) {
    return request(`/api/team/${encodeURIComponent(name)}`);
  }

  /**
   * Get season-wide statistics.
   * GET /api/statistics
   *
   * @returns {Promise<Object>} Statistics data.
   */
  function getStatistics() {
    return request("/api/statistics");
  }

  /**
   * Get preflight estimate for clinching scenarios analysis.
   * GET /api/clinch-estimate?team=<name>&cutoff_week=<n>
   *
   * @param {string} team - Team name.
   * @param {number|null} cutoffWeek - Cutoff week or null for auto-detect.
   * @returns {Promise<{team: string, available: boolean, relevant_games: number, method: string, estimated_seconds: number}>}
   */
  function clinchEstimate(team, cutoffWeek) {
    let url = `/api/clinch-estimate?team=${encodeURIComponent(team)}`;
    if (cutoffWeek != null) url += `&cutoff_week=${cutoffWeek}`;
    return request(url);
  }

  /**
   * Compute clinching scenarios for a team.
   * POST /api/clinching-scenarios
   *
   * @param {string} team - Team name.
   * @param {number|null} cutoffWeek - Cutoff week or null for auto-detect.
   * @returns {Promise<Object>} Clinching scenarios grouped by team record.
   */
  function clinchingScenarios(team, cutoffWeek) {
    const body = { team };
    if (cutoffWeek != null) body.cutoff_week = cutoffWeek;
    return request("/api/clinching-scenarios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  /**
   * Get league-wide schedule grid data for the current season.
   * GET /api/schedule-grid
   *
   * @returns {Promise<{teams: Object[]}>}
   */
  function getScheduleGrid() {
    return request("/api/schedule-grid");
  }

  /**
   * Change the active season year on the server.
   * POST /api/set-season
   *
   * @param {number} season - NFL season year (2000–2100).
   * @returns {Promise<{season_year: number}>}
   */
  function setSeason(season) {
    return request("/api/set-season", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ season }),
    });
  }

  return {
    fetchStatus,
    fetchData,
    runSimulation,
    getStandings,
    getTeamSchedule,
    getStatistics,
    clinchEstimate,
    clinchingScenarios,
    getScheduleGrid,
    setSeason,
  };
})();
