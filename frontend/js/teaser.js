/**
 * Teaser image ("Movers" card) for the NFL Playoff Rankings Monte Carlo Simulator.
 *
 * A 1200x630 PNG for link previews and social posts: the five teams whose
 * playoff probability moved most since the saved baseline, each shown as a
 * tile with its change (▲/▼) and its current probability. Rendered on a
 * <canvas> in the browser, so no server-side rendering or extra dependency.
 *
 * The baseline is a snapshot the user saves explicitly on the Export page
 * (POST /api/teaser/baseline), so the deltas stay pinned to the published
 * numbers instead of shifting with each new simulation run.
 */

"use strict";

const TEASER_WIDTH = 1200;
const TEASER_HEIGHT = 630;
const TEASER_MOVER_COUNT = 5;
const TEASER_APP_NAME = "NFL Playoff Rankings Monte Carlo Simulator";

/**
 * Work out the biggest playoff-probability movers between two snapshots.
 *
 * Deltas are rounded to one decimal place (the precision the API reports) so
 * floating-point noise cannot make an unchanged team look like a mover.
 * Teams whose probability did not change, or that are missing from either
 * snapshot, are left out. Ordered by largest absolute change first, ties by
 * team name.
 *
 * @param {Object<string, number>} current - Team -> playoff probability (0-100).
 * @param {Object<string, number>} baseline - Team -> playoff probability at the saved baseline.
 * @param {number} [limit=5] - Maximum number of movers to return.
 * @returns {Array<{team: string, previous: number, current: number, delta: number}>}
 */
function computeMovers(current, baseline, limit = TEASER_MOVER_COUNT) {
  const movers = [];
  for (const team of Object.keys(current)) {
    if (!(team in baseline)) continue;
    const previous = baseline[team];
    const now = current[team];
    const delta = Math.round((now - previous) * 10) / 10;
    if (delta === 0) continue;
    movers.push({ team, previous, current: now, delta });
  }
  movers.sort((a, b) => {
    const byMagnitude = Math.abs(b.delta) - Math.abs(a.delta);
    return byMagnitude !== 0 ? byMagnitude : a.team.localeCompare(b.team);
  });
  return movers.slice(0, limit);
}

/**
 * Format a signed percentage-point change for display, e.g. "+18.4%" or "−3.0%".
 *
 * @param {number} delta
 * @returns {string}
 */
function _formatDelta(delta) {
  const sign = delta > 0 ? "+" : "−";
  return `${sign}${Math.abs(delta).toFixed(1)}%`;
}

/**
 * Pick the largest font size, at most `maxPx` and at least 20px, at which
 * `text` fits within `maxWidth`. Returns a CSS font string for ctx.font.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {string} template - Font string with a "%s" placeholder for the size.
 * @param {string} text
 * @param {number} maxPx
 * @param {number} maxWidth
 * @returns {string}
 */
function _fitFont(ctx, template, text, maxPx, maxWidth) {
  let px = maxPx;
  ctx.font = template.replace("%s", String(px));
  while (px > 20 && ctx.measureText(text).width > maxWidth) {
    px -= 1;
    ctx.font = template.replace("%s", String(px));
  }
  return ctx.font;
}

/**
 * Load a team's logo from the app's static logo files.
 *
 * @param {string} team - Team short name, e.g. "Lions".
 * @returns {Promise<HTMLImageElement|null>} null if the team has no logo or it fails to load.
 */
function _loadTeamLogo(team) {
  const logoId = TEAM_LOGO_IDS[team];
  if (!logoId) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = `img/logos/${logoId}.png`;
  });
}

/**
 * Draw the Movers card onto a fresh canvas.
 *
 * @param {Array<{team: string, previous: number, current: number, delta: number}>} movers
 * @param {{season: number, cutoffWeek: number, baselineWeek: number, version?: string}} meta
 * @returns {Promise<HTMLCanvasElement>}
 */
async function renderTeaserCanvas(movers, meta) {
  const canvas = document.createElement("canvas");
  canvas.width = TEASER_WIDTH;
  canvas.height = TEASER_HEIGHT;
  const ctx = canvas.getContext("2d");

  const logos = await Promise.all(movers.map((mover) => _loadTeamLogo(mover.team)));

  // Archivo is loaded by index.html; wait for it so the text is measured and
  // drawn in the house font rather than the fallback. Failure just means the
  // fallback font is used.
  try {
    if (document.fonts && document.fonts.load) {
      await document.fonts.load('800 56px "Archivo"');
      await document.fonts.load('400 24px "Archivo"');
    }
  } catch (_err) {
    // Fall back to the system sans-serif below.
  }

  const headingFont = '800 %spx "Archivo", "Helvetica Neue", Arial, sans-serif';
  const bodyFont = '400 %spx "Archivo", "Helvetica Neue", Arial, sans-serif';

  // Paper background and ink header band, matching the app's nav bar.
  ctx.fillStyle = "#f3f2f2";
  ctx.fillRect(0, 0, TEASER_WIDTH, TEASER_HEIGHT);
  ctx.fillStyle = "#161514";
  ctx.fillRect(0, 0, TEASER_WIDTH, 120);
  ctx.fillStyle = "#ec3013";
  ctx.fillRect(0, 120, TEASER_WIDTH, 6);

  ctx.fillStyle = "#f3f2f2";
  ctx.font = headingFont.replace("%s", "40");
  ctx.textBaseline = "middle";
  ctx.fillText("NFL PLAYOFF RANKINGS SIM", 56, 60);

  ctx.font = bodyFont.replace("%s", "24");
  ctx.textAlign = "right";
  ctx.fillText(`${meta.season} · Week ${meta.cutoffWeek}`, TEASER_WIDTH - 56, 60);
  ctx.textAlign = "left";

  // Headline.
  ctx.fillStyle = "#161514";
  ctx.font = headingFont.replace("%s", "64");
  ctx.textBaseline = "alphabetic";
  ctx.fillText("BIGGEST MOVERS", 56, 260);

  ctx.fillStyle = "#332f2d";
  ctx.font = bodyFont.replace("%s", "24");
  ctx.fillText(
    `Playoff probability change since week ${meta.baselineWeek}`,
    56,
    300,
  );

  // One tile per mover.
  const tileGap = 16;
  const tileCount = TEASER_MOVER_COUNT;
  const tileWidth = (TEASER_WIDTH - 112 - tileGap * (tileCount - 1)) / tileCount;
  const tileTop = 340;
  const tileHeight = 220;

  for (let i = 0; i < movers.length; i++) {
    const mover = movers[i];
    const x = 56 + i * (tileWidth + tileGap);
    const up = mover.delta > 0;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x, tileTop, tileWidth, tileHeight);
    ctx.fillStyle = up ? "#161514" : "#ec3013";
    ctx.fillRect(x, tileTop, tileWidth, 8);

    const logo = logos[i];
    const logoSize = 44;
    if (logo) {
      const scale = Math.min(logoSize / logo.naturalWidth, logoSize / logo.naturalHeight);
      const drawWidth = logo.naturalWidth * scale;
      const drawHeight = logo.naturalHeight * scale;
      ctx.drawImage(
        logo,
        x + 18 + (logoSize - drawWidth) / 2,
        tileTop + 22 + (logoSize - drawHeight) / 2,
        drawWidth,
        drawHeight,
      );
    }

    const nameX = x + 18 + logoSize + 12;
    ctx.fillStyle = "#161514";
    ctx.font = _fitFont(ctx, headingFont, mover.team.toUpperCase(), 26, x + tileWidth - 14 - nameX);
    ctx.fillText(mover.team.toUpperCase(), nameX, tileTop + 52);

    ctx.fillStyle = up ? "#161514" : "#ec3013";
    const deltaText = `${up ? "▲" : "▼"} ${_formatDelta(mover.delta)}`;
    ctx.font = _fitFont(ctx, headingFont, deltaText, 34, tileWidth - 36);
    ctx.fillText(deltaText, x + 18, tileTop + 120);

    ctx.fillStyle = "#6b6866";
    ctx.font = bodyFont.replace("%s", "20");
    ctx.fillText(
      `${mover.previous.toFixed(1)}% → ${mover.current.toFixed(1)}%`,
      x + 18,
      tileTop + 170,
    );
  }

  if (movers.length === 0) {
    ctx.fillStyle = "#6b6866";
    ctx.font = bodyFont.replace("%s", "28");
    ctx.fillText("No playoff probabilities changed since the baseline.", 56, tileTop + 80);
  }

  // Footer: official app name and version on the left, disclaimer on the right.
  const footerName = meta.version ? `${TEASER_APP_NAME} v${meta.version}` : TEASER_APP_NAME;
  ctx.fillStyle = "#332f2d";
  ctx.font = headingFont.replace("%s", "20");
  ctx.textBaseline = "alphabetic";
  ctx.fillText(footerName, 56, TEASER_HEIGHT - 36);

  ctx.fillStyle = "#6b6866";
  ctx.font = bodyFont.replace("%s", "20");
  ctx.textAlign = "right";
  ctx.fillText("Independent project, not affiliated with the NFL", TEASER_WIDTH - 56, TEASER_HEIGHT - 36);
  ctx.textAlign = "left";

  return canvas;
}

/**
 * Render the Movers card and encode it as a PNG Blob.
 *
 * @param {Array<{team: string, previous: number, current: number, delta: number}>} movers
 * @param {{season: number, cutoffWeek: number, baselineWeek: number}} meta
 * @returns {Promise<Blob>}
 */
async function buildTeaserBlob(movers, meta) {
  const canvas = await renderTeaserCanvas(movers, meta);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not encode the teaser image."));
    }, "image/png");
  });
}
