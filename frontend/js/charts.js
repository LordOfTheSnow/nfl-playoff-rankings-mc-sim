/**
 * Chart rendering for the NFL Monte Carlo Playoff Simulator.
 *
 * Provides a canvas-based heatmap visualization showing seeding probability
 * distribution for each team within a selected conference.
 *
 * X-axis: seed positions (1–7)
 * Y-axis: team names (sorted by playoff probability descending)
 * Cell color intensity: probability value (0% = white, 100% = dark blue)
 * Cell text: probability percentage
 *
 * No external dependencies — uses the Canvas 2D API only.
 *
 * Requirements: 7.6
 */

"use strict";

/**
 * Render a seeding probability heatmap chart into the given container element.
 *
 * @param {HTMLElement} containerEl - The DOM element to render the chart into.
 * @param {Array<Object>} teamResults - Array of team result objects from the simulation.
 *   Each object has: { team, conference, division, playoff_probability, seed_probabilities, strength_rating }
 *   seed_probabilities is an object like {"1": 42.1, "2": 28.7, ...}
 * @param {string} conference - Conference filter: "AFC" or "NFC".
 */
function renderSeedingChart(containerEl, teamResults, conference) {
  if (!containerEl || !teamResults || !conference) return;

  // Clear previous content
  containerEl.innerHTML = "";

  // Filter teams by conference
  const teams = teamResults
    .filter((t) => t.conference === conference)
    .sort((a, b) => {
      // Sort by playoff_probability descending; alphabetical for ties
      if (b.playoff_probability !== a.playoff_probability) {
        return b.playoff_probability - a.playoff_probability;
      }
      return a.team.localeCompare(b.team);
    });

  if (teams.length === 0) {
    containerEl.innerHTML =
      '<p class="empty-state">No teams found for ' + conference + ".</p>";
    return;
  }

  const seeds = [1, 2, 3, 4, 5, 6, 7];

  // --- Layout constants ---
  const cellWidth = 72;
  const cellHeight = 32;
  const labelWidth = 120;
  const headerHeight = 36;
  const legendHeight = 50;
  const padding = 16;

  const chartWidth = labelWidth + seeds.length * cellWidth + padding;
  const chartHeight =
    headerHeight + teams.length * cellHeight + legendHeight + padding * 2;

  // Device pixel ratio for sharp rendering
  const dpr = window.devicePixelRatio || 1;

  // Create canvas
  const canvas = document.createElement("canvas");
  canvas.width = chartWidth * dpr;
  canvas.height = chartHeight * dpr;
  canvas.style.width = chartWidth + "px";
  canvas.style.height = chartHeight + "px";
  canvas.setAttribute("role", "img");
  canvas.setAttribute(
    "aria-label",
    conference + " seeding probability heatmap"
  );

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  // --- Color interpolation ---
  // 0% → white (#ffffff), 100% → dark blue (#1b3a6b)
  function getHeatColor(probability) {
    const t = Math.min(Math.max(probability / 100, 0), 1);
    const r = Math.round(255 + (27 - 255) * t);
    const g = Math.round(255 + (58 - 255) * t);
    const b = Math.round(255 + (107 - 255) * t);
    return "rgb(" + r + "," + g + "," + b + ")";
  }

  function getTextColor(probability) {
    // Use white text on dark cells (probability > 40%)
    return probability > 40 ? "#ffffff" : "#1a1a2e";
  }

  // --- Draw background ---
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, chartWidth, chartHeight);

  // --- Draw header (seed labels) ---
  ctx.font = "bold 12px -apple-system, BlinkMacSystemFont, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#1a1a2e";

  for (let i = 0; i < seeds.length; i++) {
    const x = labelWidth + i * cellWidth + cellWidth / 2;
    const y = headerHeight / 2;
    ctx.fillText("Seed " + seeds[i], x, y);
  }

  // --- Draw rows (teams) ---
  ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";

  for (let row = 0; row < teams.length; row++) {
    const team = teams[row];
    const y = headerHeight + row * cellHeight;

    // Team name label
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#1a1a2e";
    ctx.font = "12px -apple-system, BlinkMacSystemFont, sans-serif";
    ctx.fillText(team.team, labelWidth - 8, y + cellHeight / 2);

    // Seed cells
    for (let col = 0; col < seeds.length; col++) {
      const seed = seeds[col];
      const prob =
        team.seed_probabilities[String(seed)] ||
        team.seed_probabilities[seed] ||
        0;
      const x = labelWidth + col * cellWidth;

      // Cell background
      ctx.fillStyle = getHeatColor(prob);
      ctx.fillRect(x, y, cellWidth, cellHeight);

      // Cell border
      ctx.strokeStyle = "#dde2e8";
      ctx.lineWidth = 0.5;
      ctx.strokeRect(x, y, cellWidth, cellHeight);

      // Cell text (probability value)
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = getTextColor(prob);
      ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
      if (prob > 0) {
        ctx.fillText(prob.toFixed(1) + "%", x + cellWidth / 2, y + cellHeight / 2);
      } else {
        ctx.fillStyle = "#b0b0b0";
        ctx.fillText("—", x + cellWidth / 2, y + cellHeight / 2);
      }
    }
  }

  // --- Draw grid lines ---
  ctx.strokeStyle = "#dde2e8";
  ctx.lineWidth = 1;

  // Horizontal line below header
  ctx.beginPath();
  ctx.moveTo(labelWidth, headerHeight);
  ctx.lineTo(labelWidth + seeds.length * cellWidth, headerHeight);
  ctx.stroke();

  // Vertical line separating labels from cells
  ctx.beginPath();
  ctx.moveTo(labelWidth, 0);
  ctx.lineTo(labelWidth, headerHeight + teams.length * cellHeight);
  ctx.stroke();

  // --- Draw color legend ---
  const legendY = headerHeight + teams.length * cellHeight + padding;
  const legendBarX = labelWidth;
  const legendBarWidth = seeds.length * cellWidth;
  const legendBarHeight = 14;

  // Legend title
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillStyle = "#5a5a7a";
  ctx.font = "11px -apple-system, BlinkMacSystemFont, sans-serif";
  ctx.fillText("Probability", labelWidth, legendY - 2);

  // Gradient bar
  const gradientY = legendY + 14;
  const gradient = ctx.createLinearGradient(
    legendBarX,
    0,
    legendBarX + legendBarWidth,
    0
  );
  gradient.addColorStop(0, getHeatColor(0));
  gradient.addColorStop(0.25, getHeatColor(25));
  gradient.addColorStop(0.5, getHeatColor(50));
  gradient.addColorStop(0.75, getHeatColor(75));
  gradient.addColorStop(1, getHeatColor(100));

  ctx.fillStyle = gradient;
  ctx.fillRect(legendBarX, gradientY, legendBarWidth, legendBarHeight);

  // Legend border
  ctx.strokeStyle = "#dde2e8";
  ctx.lineWidth = 1;
  ctx.strokeRect(legendBarX, gradientY, legendBarWidth, legendBarHeight);

  // Legend labels
  ctx.fillStyle = "#5a5a7a";
  ctx.font = "10px -apple-system, BlinkMacSystemFont, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  ctx.fillText("0%", legendBarX, gradientY + legendBarHeight + 3);

  ctx.textAlign = "center";
  ctx.fillText(
    "50%",
    legendBarX + legendBarWidth / 2,
    gradientY + legendBarHeight + 3
  );

  ctx.textAlign = "right";
  ctx.fillText(
    "100%",
    legendBarX + legendBarWidth,
    gradientY + legendBarHeight + 3
  );

  // Append canvas to container
  containerEl.appendChild(canvas);
}
