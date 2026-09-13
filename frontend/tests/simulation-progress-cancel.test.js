/**
 * Simulations page: background-job progress and cancel UI.
 *
 * POST /api/simulate now starts a background job instead of blocking for
 * the run's full duration (which can take minutes — see CHANGELOG); the
 * frontend polls GET /api/simulate/status/{job_id} and can request a
 * cancellation. These tests cover the click-to-poll-to-result wiring in
 * simulation.js: progress text updates across poll ticks, the Cancel
 * button's behavior, and terminal-state handling (completed/cancelled/
 * failed) restoring the controls.
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach } from "vitest";

const baseStatus = {
  version: "1.0.0",
  season_year: 2025,
  total_games: 200,
  games_cached: 200,
  expected_total: 272,
  completed: 150,
  weeks_fetched: 16,
  weeks_completed: 15,
  cpu_count: 6,
  games_per_week: { 16: 16, 17: 16, 18: 16 },
  default_tie_probability: 0.0029,
};

const sampleResult = {
  iterations_run: 10000,
  cutoff_week_used: 15,
  team_results: [
    {
      team: "Ravens",
      conference: "AFC",
      division: "AFC North",
      record: "9-6-0",
      playoff_probability: 55.5,
      strength_rating: 1.05,
      seed_probabilities: { 1: 5, 2: 10, 3: 15, 4: 10, 5: 10, 6: 5, 7: 0.5 },
    },
  ],
};

describe("Simulations: background-job progress and cancel", () => {
  let contentEl;
  let originalFetchStatus;
  let originalStartSimulation;
  let originalGetSimulationStatus;
  let originalCancelSimulation;

  beforeAll(() => {
    // App's notification element reference is resolved on DOMContentLoaded
    // (see app.js) -- re-dispatch it so App.showInfo/showError actually
    // render into #notification (mirrors error-alert.test.js).
    document.dispatchEvent(new Event("DOMContentLoaded"));
  });

  beforeEach(() => {
    localStorage.clear();
    contentEl = document.getElementById("content");
    contentEl.innerHTML = "";
    originalFetchStatus = API.fetchStatus;
    originalStartSimulation = API.startSimulation;
    originalGetSimulationStatus = API.getSimulationStatus;
    originalCancelSimulation = API.cancelSimulation;
    API.fetchStatus = () => Promise.resolve(baseStatus);
  });

  afterEach(() => {
    vi.useRealTimers();
    API.fetchStatus = originalFetchStatus;
    API.startSimulation = originalStartSimulation;
    API.getSimulationStatus = originalGetSimulationStatus;
    API.cancelSimulation = originalCancelSimulation;
    localStorage.clear();
    App.hideNotification();
  });

  it("shows the Cancel button and progress text while running, then restores UI and renders results on completion", async () => {
    vi.useFakeTimers();
    let statusCall = 0;
    API.startSimulation = () => Promise.resolve({ job_id: "job-1", status: "running" });
    API.getSimulationStatus = () => {
      statusCall += 1;
      if (statusCall === 1) {
        return Promise.resolve({ status: "running", phase: "Simulating games", progress_done: 0, progress_total: 5 });
      }
      if (statusCall === 2) {
        return Promise.resolve({ status: "running", phase: "Ranking impact games", progress_done: 3, progress_total: 20 });
      }
      return Promise.resolve({ status: "completed", phase: "", progress_done: 0, progress_total: 0, result: sampleResult });
    };

    await renderSimulations(contentEl);
    const runBtn = document.getElementById("btn-run-sim");
    const cancelBtn = document.getElementById("btn-cancel-sim");
    const fetchBtn = document.getElementById("btn-fetch-data-sim");
    const progressEl = document.getElementById("sim-progress-sim");
    const progressTextEl = document.getElementById("sim-progress-text-sim");

    runBtn.click();
    await vi.advanceTimersByTimeAsync(0); // startSimulation + first poll

    expect(progressEl.style.display).toBe("flex");
    expect(cancelBtn.style.display).not.toBe("none");
    expect(runBtn.disabled).toBe(true);
    expect(fetchBtn.disabled).toBe(true);
    expect(progressTextEl.textContent).toBe("Simulating games… (0/5)");

    await vi.advanceTimersByTimeAsync(600); // second poll tick
    expect(progressTextEl.textContent).toBe("Ranking impact games… (3/20)");

    await vi.advanceTimersByTimeAsync(600); // third poll tick -> completed

    // renderSimulations re-renders the whole card on completion, so query
    // fresh elements rather than reusing the (now-replaced) originals.
    expect(window._simulationResults.team_results).toEqual(sampleResult.team_results);
    const newProgressEl = document.getElementById("sim-progress-sim");
    expect(newProgressEl.style.display).toBe("none");
    const newRunBtn = document.getElementById("btn-run-sim");
    expect(newRunBtn.disabled).toBe(false);
  });

  it("Cancel calls API.cancelSimulation with the active job and resets UI once status becomes cancelled", async () => {
    vi.useFakeTimers();
    let statusCall = 0;
    let cancelledCalledWith = null;
    API.startSimulation = () => Promise.resolve({ job_id: "job-2", status: "running" });
    API.getSimulationStatus = () => {
      statusCall += 1;
      if (statusCall <= 1) {
        return Promise.resolve({ status: "running", phase: "Simulating games", progress_done: 0, progress_total: 5 });
      }
      return Promise.resolve({ status: "cancelled", phase: "", progress_done: 0, progress_total: 0 });
    };
    API.cancelSimulation = (jobId) => {
      cancelledCalledWith = jobId;
      return Promise.resolve({ job_id: jobId, status: "running" });
    };

    await renderSimulations(contentEl);
    const runBtn = document.getElementById("btn-run-sim");
    runBtn.click();
    await vi.advanceTimersByTimeAsync(0);

    const cancelBtn = document.getElementById("btn-cancel-sim");
    cancelBtn.click();
    await vi.advanceTimersByTimeAsync(0);

    expect(cancelledCalledWith).toBe("job-2");

    await vi.advanceTimersByTimeAsync(600); // next poll tick observes "cancelled"

    expect(cancelBtn.style.display).toBe("none");
    expect(runBtn.disabled).toBe(false);
    const notification = document.getElementById("notification");
    expect(notification.textContent).toContain("Simulation cancelled");
  });

  it("shows an error and restores controls when the job status is 'failed'", async () => {
    vi.useFakeTimers();
    API.startSimulation = () => Promise.resolve({ job_id: "job-3", status: "running" });
    API.getSimulationStatus = () => Promise.resolve({
      status: "failed", phase: "", progress_done: 0, progress_total: 0, error: "Parallel simulation failed: boom",
    });

    await renderSimulations(contentEl);
    const runBtn = document.getElementById("btn-run-sim");
    runBtn.click();
    await vi.advanceTimersByTimeAsync(0);

    expect(runBtn.disabled).toBe(false);
    const progressEl = document.getElementById("sim-progress-sim");
    expect(progressEl.style.display).toBe("none");
    const notification = document.getElementById("notification");
    expect(notification.textContent).toContain("Parallel simulation failed: boom");
    expect(notification.querySelector(".mdn-alert-danger")).not.toBeNull();
  });
});
