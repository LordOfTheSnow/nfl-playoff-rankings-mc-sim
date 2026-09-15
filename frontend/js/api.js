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
   * Start a Monte Carlo simulation as a background job.
   * POST /api/simulate
   *
   * A simulation can take minutes (see CHANGELOG), so it doesn't run
   * synchronously — this returns a job_id immediately. Poll
   * getSimulationStatus(jobId) for progress and the eventual result, and
   * use cancelSimulation(jobId) to request a best-effort stop.
   *
   * @param {number} iterations - Number of simulation trials (100–1,000,000).
   * @param {number|null} cutoffWeek - Cutoff week (1–18) or null for auto-detect.
   * @param {number|null} noise - Per-game strength noise (0.0–1.0) or null for default.
   * @param {number|null} numWorkers - Number of parallel workers or null for auto-detect.
   * @param {number|null} [tieProbability] - Per-game tie probability (0.0–1.0) or null
   *   for the server's empirical estimate (see GET /api/status's default_tie_probability).
   * @returns {Promise<{job_id: string, status: string}>}
   */
  function startSimulation(iterations, cutoffWeek, noise, numWorkers, tieProbability) {
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
    if (tieProbability != null) {
      body.tie_probability = tieProbability;
    }
    return request("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  /**
   * Poll a background simulation job's progress and (once complete) result.
   * GET /api/simulate/status/{jobId}
   *
   * @param {string} jobId
   * @returns {Promise<{status: string, phase: string, progress_done: number,
   *   progress_total: number, result?: Object, error?: string}>}
   */
  function getSimulationStatus(jobId) {
    return request(`/api/simulate/status/${encodeURIComponent(jobId)}`);
  }

  /**
   * Request a best-effort stop of a running simulation job. Already-
   * dispatched worker batches finish rather than being killed outright, so
   * the job's status may stay "running" for a moment after this resolves —
   * keep polling getSimulationStatus until it settles.
   * POST /api/simulate/cancel/{jobId}
   *
   * @param {string} jobId
   * @returns {Promise<{job_id: string, status: string}>}
   */
  function cancelSimulation(jobId) {
    return request(`/api/simulate/cancel/${encodeURIComponent(jobId)}`, {
      method: "POST",
    });
  }

  /**
   * Get current NFL standings computed from cached data.
   * GET /api/standings?cutoff_week=<n>
   *
   * @param {number|null} cutoffWeek - Optional cutoff week (1-18). Only games up to this week are included.
   * @returns {Promise<{standings: Object[], bracket: Object}>}
   */
  function getStandings(cutoffWeek) {
    let url = "/api/standings";
    if (cutoffWeek != null) url += "?cutoff_week=" + cutoffWeek;
    return request(url);
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
   * @param {number|null} [enumerationThreshold] - Max other games for brute-force enumeration.
   * @param {number|null} [numSamples] - Number of MC samples when using sampling method.
   * @param {number|null} [noise] - Per-game strength noise sigma (0.0-1.0); should match
   *   the main simulation's Noise setting for consistent results.
   * @param {number|null} [tieProbability] - Per-game tie probability (0.0-1.0); should
   *   match the main simulation's effective tie probability for consistent results.
   * @returns {Promise<Object>} Clinching scenarios grouped by team record.
   */
  function clinchingScenarios(team, cutoffWeek, enumerationThreshold, numSamples, noise, tieProbability) {
    const body = { team };
    if (cutoffWeek != null) body.cutoff_week = cutoffWeek;
    if (enumerationThreshold != null) body.enumeration_threshold = enumerationThreshold;
    if (numSamples != null) body.num_samples = numSamples;
    if (noise != null) body.noise = noise;
    if (tieProbability != null) body.tie_probability = tieProbability;
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

  /**
   * Get CP solver clinch/elimination status for all 32 teams.
   * GET /api/cp-clinch-all?cutoff_week=<n>
   *
   * Returns null if the endpoint is unavailable (503, 409, or network error).
   *
   * @param {number|null} cutoffWeek - Optional cutoff week (1-18).
   * @returns {Promise<Object|null>} Clinch data grouped by conference, or null on error.
   */
  async function fetchCPClinchAll(cutoffWeek) {
    try {
      let url = "/api/cp-clinch-all";
      if (cutoffWeek != null) url += "?cutoff_week=" + cutoffWeek;
      const response = await fetch(url);
      if (!response.ok) return null;
      return await response.json();
    } catch (_) {
      return null;
    }
  }

  /**
   * Get solver timing history.
   * GET /api/solver-timings
   *
   * @returns {Promise<{timings: Object[], count: number, avg_ms_per_eval: number}>}
   */
  function solverTimings() {
    return request("/api/solver-timings");
  }

  /**
   * Get database metadata and runtime environment info.
   * GET /api/system-info
   *
   * @returns {Promise<Object>} Database (path, size, per-season completeness) and runtime (CPU, Python, platform) info.
   */
  function getSystemInfo() {
    return request("/api/system-info");
  }

  /**
   * Reset the lifetime run counters (games simulated, clinching resolver
   * evaluations) shown on Settings / Info back to 0.
   * POST /api/reset-counters
   *
   * @returns {Promise<{games_simulated_total: number, clinching_resolver_evals_total: number}>}
   */
  function resetCounters() {
    return request("/api/reset-counters", { method: "POST" });
  }

  /**
   * Internal helper: POST JSON and return the raw response body as a Blob,
   * for endpoints that return a file (HTML page or ZIP) rather than JSON.
   *
   * @param {string} url
   * @param {Object} payload
   * @returns {Promise<Blob>}
   */
  async function _fetchBlob(url, payload) {
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
      });
    } catch (networkError) {
      throw new Error("Network error: unable to reach the server.");
    }
    if (!response.ok) {
      let message = `Server error (HTTP ${response.status})`;
      try {
        const data = await response.json();
        if (data && data.message) message = data.message;
      } catch (_) {
        // response body wasn't JSON — keep the generic message
      }
      throw new Error(message);
    }
    return response.blob();
  }

  /**
   * Export a single standalone HTML page combining Standings, Statistics,
   * Schedule Grid, and (if supplied) Simulation results.
   * POST /api/export/page
   *
   * @param {{simulation_result?: Object|null, cutoff_week?: number|null}} payload
   * @returns {Promise<Blob>} The HTML file contents.
   */
  function exportPage(payload) {
    return _fetchBlob("/api/export/page", payload);
  }

  /**
   * Export a ZIP bundle: an index page, one page per section, and one page
   * per team, all linking to a shared styles.css.
   * POST /api/export/bundle
   *
   * @param {{simulation_result?: Object|null, cutoff_week?: number|null}} payload
   * @returns {Promise<Blob>} The ZIP file contents.
   */
  function exportBundle(payload) {
    return _fetchBlob("/api/export/bundle", payload);
  }

  return {
    fetchStatus,
    fetchData,
    startSimulation,
    getSimulationStatus,
    cancelSimulation,
    getStandings,
    getTeamSchedule,
    getStatistics,
    clinchEstimate,
    clinchingScenarios,
    getScheduleGrid,
    setSeason,
    fetchCPClinchAll,
    solverTimings,
    getSystemInfo,
    resetCounters,
    exportPage,
    exportBundle,
  };
})();
