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
const TEASER_LOGO_SIZE = 80;

/**
 * Card sizes the teaser can be exported in. `topSafe` keeps the header clear
 * of the phone UI at the top of a Story; `bottomSafe` is the margin below the
 * footer. `bell` adds the simulation dot plot between the rows and the footer.
 */
const TEASER_FORMATS = {
  landscape: { id: "landscape", label: "Landscape 1200×630", width: 1200, height: 630, portrait: false },
  portrait: { id: "portrait-4x5", label: "Portrait 4:5 1080×1350", width: 1080, height: 1350, topSafe: 0, bottomSafe: 48, portrait: true },
  story: { id: "portrait-9x16", label: "Story 9:16 1080×1920", width: 1080, height: 1920, topSafe: 200, bottomSafe: 48, portrait: true, bell: true },
};
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
 * Shrink a logo to fit within `maxSize` x `maxSize`, keeping its aspect ratio.
 *
 * Done in halving steps so no single draw resamples by more than 2x. A one-shot
 * downscale from 500px to 80px depends on how each browser filters the image
 * and comes out ragged in some of them.
 *
 * @param {HTMLImageElement} img
 * @param {number} maxSize
 * @returns {HTMLCanvasElement} Canvas holding the shrunken logo.
 */
function _shrinkLogo(img, maxSize) {
  const scale = Math.min(maxSize / img.naturalWidth, maxSize / img.naturalHeight, 1);
  const targetW = Math.round(img.naturalWidth * scale);
  const targetH = Math.round(img.naturalHeight * scale);

  let source = img;
  let w = img.naturalWidth;
  let h = img.naturalHeight;
  while (w / 2 >= targetW && h / 2 >= targetH) {
    w = Math.round(w / 2);
    h = Math.round(h / 2);
    const step = document.createElement("canvas");
    step.width = w;
    step.height = h;
    step.getContext("2d").drawImage(source, 0, 0, w, h);
    source = step;
  }

  const out = document.createElement("canvas");
  out.width = targetW;
  out.height = targetH;
  out.getContext("2d").drawImage(source, 0, 0, targetW, targetH);
  return out;
}

/**
 * Draw the Movers card onto a fresh canvas.
 *
 * @param {Array<{team: string, previous: number, current: number, delta: number}>} movers
 * @param {{season: number, cutoffWeek: number, baselineWeek: number, version?: string}} meta
 * @param {typeof TEASER_FORMATS[keyof typeof TEASER_FORMATS]} [format=TEASER_FORMATS.landscape]
 * @returns {Promise<HTMLCanvasElement>}
 */
async function renderTeaserCanvas(movers, meta, format = TEASER_FORMATS.landscape) {
  const canvas = document.createElement("canvas");
  canvas.width = format.width;
  canvas.height = format.height;
  const ctx = canvas.getContext("2d");

  const logos = (await Promise.all(movers.map((mover) => _loadTeamLogo(mover.team)))).map(
    (img) => (img ? _shrinkLogo(img, TEASER_LOGO_SIZE) : null),
  );

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

  if (format.portrait) {
    _drawPortraitCard(ctx, movers, logos, meta, format, { headingFont, bodyFont });
    return canvas;
  }

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
  ctx.fillText("BIGGEST MOVERS", 56, 240);

  ctx.fillStyle = "#332f2d";
  ctx.font = bodyFont.replace("%s", "24");
  ctx.fillText(
    `Playoff probability change since week ${meta.baselineWeek}`,
    56,
    280,
  );

  // One tile per mover: logo centred at the top, team name centred below it,
  // then the change and the before/after probabilities.
  const tileGap = 16;
  const tileCount = TEASER_MOVER_COUNT;
  const tileWidth = (TEASER_WIDTH - 112 - tileGap * (tileCount - 1)) / tileCount;
  const tileTop = 316;
  const tileHeight = 250;
  const tilePadding = 12;

  for (let i = 0; i < movers.length; i++) {
    const mover = movers[i];
    const x = 56 + i * (tileWidth + tileGap);
    const centerX = x + tileWidth / 2;
    const up = mover.delta > 0;

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(x, tileTop, tileWidth, tileHeight);
    ctx.fillStyle = up ? "#161514" : "#ec3013";
    ctx.fillRect(x, tileTop, tileWidth, 8);

    const logo = logos[i];
    const logoSize = TEASER_LOGO_SIZE;
    const logoTop = tileTop + 24;
    if (logo) {
      ctx.drawImage(
        logo,
        centerX - logo.width / 2,
        logoTop + (logoSize - logo.height) / 2,
      );
    }

    // Name below the logo, shrunk until it fits the tile's inner width.
    const teamName = mover.team.toUpperCase();
    ctx.fillStyle = "#161514";
    ctx.font = _fitFont(ctx, headingFont, teamName, 26, tileWidth - 2 * tilePadding);
    ctx.textAlign = "center";
    ctx.fillText(teamName, centerX, logoTop + logoSize + 34);

    ctx.fillStyle = up ? "#161514" : "#ec3013";
    const deltaText = `${up ? "▲" : "▼"} ${_formatDelta(mover.delta)}`;
    ctx.font = _fitFont(ctx, headingFont, deltaText, 34, tileWidth - 2 * tilePadding);
    ctx.fillText(deltaText, centerX, tileTop + 196);

    ctx.fillStyle = "#6b6866";
    ctx.font = bodyFont.replace("%s", "20");
    ctx.fillText(
      `${mover.previous.toFixed(1)}% → ${mover.current.toFixed(1)}%`,
      centerX,
      tileTop + 228,
    );
    ctx.textAlign = "left";
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
 * Draw the portrait Movers card: the five movers as full-width rows (logo,
 * name and before/after on the left, change on the right), in the layout the
 * Export page previews as "A · Vertical ledger". The 9:16 format keeps the
 * header and footer clear of the phone's UI and gives the rows the extra height.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<{team: string, previous: number, current: number, delta: number}>} movers
 * @param {Array<HTMLCanvasElement|null>} logos - Shrunken logos, index-aligned with movers.
 * @param {{season: number, cutoffWeek: number, baselineWeek: number, version?: string}} meta
 * @param {typeof TEASER_FORMATS.portrait} format
 * @param {{headingFont: string, bodyFont: string}} fonts - Font templates with a "%s" size placeholder.
 */
function _drawPortraitCard(ctx, movers, logos, meta, format, fonts) {
  const { headingFont, bodyFont } = fonts;
  const W = format.width;
  const H = format.height;
  const top = format.topSafe;
  const margin = 56;
  const contentW = W - 2 * margin;
  const rowPad = 40;

  // Paper background, then the ink header band below the top safe zone.
  ctx.fillStyle = "#f3f2f2";
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "#161514";
  ctx.fillRect(0, 0, W, top + 170);
  ctx.fillStyle = "#ec3013";
  ctx.fillRect(0, top + 170, W, 6);

  ctx.fillStyle = "#f3f2f2";
  ctx.textBaseline = "middle";
  ctx.font = headingFont.replace("%s", "44");
  ctx.fillText("NFL PLAYOFF RANKINGS SIM", margin, top + 85);
  ctx.font = bodyFont.replace("%s", "28");
  ctx.textAlign = "right";
  ctx.fillText(`${meta.season} · Week ${meta.cutoffWeek}`, W - margin, top + 85);
  ctx.textAlign = "left";

  // Headline and subtitle.
  ctx.fillStyle = "#161514";
  ctx.textBaseline = "alphabetic";
  ctx.font = _fitFont(ctx, headingFont, "BIGGEST MOVERS", 96, contentW);
  ctx.fillText("BIGGEST MOVERS", margin, top + 300);
  ctx.fillStyle = "#332f2d";
  ctx.font = bodyFont.replace("%s", "32");
  ctx.fillText(`Playoff probability change since week ${meta.baselineWeek}`, margin, top + 360);

  // Footer baselines sit at the bottom edge; the bell panel (Story only) goes
  // above them and the rows fill whatever space is left.
  const footerNameY = H - format.bottomSafe - 40;
  const footerDiscY = H - format.bottomSafe;
  const footerTop = footerNameY - 28;
  const bellH = format.bell ? 240 : 0;
  const bellBottom = footerTop - 48;
  const bellTop = bellBottom - bellH;

  // Rows fill the space between the subtitle and the footer (or the bell panel).
  const gap = 16;
  const listTop = top + 400;
  const listBottom = format.bell ? bellTop - 40 : footerTop - 48;
  const rowH = (listBottom - listTop - gap * (TEASER_MOVER_COUNT - 1)) / TEASER_MOVER_COUNT;
  const tall = rowH >= 170;

  if (movers.length === 0) {
    ctx.fillStyle = "#6b6866";
    ctx.font = bodyFont.replace("%s", "32");
    ctx.fillText("No playoff probabilities changed since the baseline.", margin, listTop + 60);
  }

  const logoBox = Math.min(rowH - 40, 120);
  const rightEdge = margin + contentW - rowPad;

  for (let i = 0; i < movers.length; i++) {
    const mover = movers[i];
    const y = listTop + i * (rowH + gap);
    const up = mover.delta > 0;
    const accent = up ? "#161514" : "#ec3013";

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(margin, y, contentW, rowH);
    ctx.fillStyle = accent;
    ctx.fillRect(margin, y, contentW, 8);

    const logo = logos[i];
    if (logo) {
      ctx.drawImage(
        logo,
        margin + rowPad + (logoBox - logo.width) / 2,
        y + (rowH - logo.height) / 2,
      );
    }

    // Change: measured first so the team name can leave room for it.
    const deltaText = `${up ? "▲" : "▼"} ${_formatDelta(mover.delta)}`;
    const deltaFont = _fitFont(ctx, headingFont, deltaText, tall ? 76 : 66, 420);
    const deltaW = ctx.measureText(deltaText).width;

    const textX = margin + rowPad + logoBox + 32;
    const nameMaxW = rightEdge - deltaW - 32 - textX;
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#161514";
    ctx.font = _fitFont(ctx, headingFont, mover.team.toUpperCase(), tall ? 64 : 52, nameMaxW);
    ctx.fillText(mover.team.toUpperCase(), textX, y + rowH * 0.4);

    ctx.fillStyle = "#6b6866";
    ctx.font = bodyFont.replace("%s", tall ? "34" : "30");
    ctx.fillText(`${mover.previous.toFixed(1)}% → ${mover.current.toFixed(1)}%`, textX, y + rowH * 0.68);

    ctx.fillStyle = accent;
    ctx.font = deltaFont;
    ctx.textAlign = "right";
    ctx.fillText(deltaText, rightEdge, y + rowH / 2);
    ctx.textAlign = "left";
  }

  if (format.bell) {
    _drawBellPanel(ctx, { x: margin, y: bellTop, width: contentW, height: bellH }, meta, fonts);
  }

  // Footer, left-aligned, at the bottom edge.
  ctx.textBaseline = "alphabetic";
  const footerName = meta.version ? `${TEASER_APP_NAME} v${meta.version}` : TEASER_APP_NAME;
  ctx.fillStyle = "#332f2d";
  ctx.font = _fitFont(ctx, headingFont, footerName, 28, contentW);
  ctx.fillText(footerName, margin, footerNameY);
  ctx.fillStyle = "#6b6866";
  ctx.font = bodyFont.replace("%s", "24");
  ctx.fillText("Independent project, not affiliated with the NFL", margin, footerDiscY);
}

/**
 * Draw the stylised "simulation" panel: an ink block with a dot plot shaped
 * like a bell curve, the outer tails in red, and a caption with the number of
 * Monte Carlo iterations behind the run. Decorative, not a chart of real data.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{x: number, y: number, width: number, height: number}} box
 * @param {{iterations?: number}} meta
 * @param {{headingFont: string, bodyFont: string}} fonts
 */
function _drawBellPanel(ctx, box, meta, fonts) {
  const { x, y, width, height } = box;
  const pad = 32;
  const bins = 25;
  const maxDots = 9;
  const pitch = 15;
  const dotR = 6;
  const colW = (width - 2 * pad) / bins;
  const baseY = y + height - 24;

  ctx.fillStyle = "#161514";
  ctx.fillRect(x, y, width, height);
  ctx.fillStyle = "#ec3013";
  ctx.fillRect(x, y, width, 8);

  // Caption: the real iteration count when the run reports it.
  const caption = meta.iterations
    ? `${meta.iterations.toLocaleString("en-US")} SIMULATIONS PER GAME`
    : "MONTE CARLO SIMULATION";
  ctx.fillStyle = "#f3f2f2";
  ctx.textBaseline = "alphabetic";
  ctx.font = _fitFont(ctx, fonts.headingFont, caption, 26, width - 2 * pad);
  ctx.fillText(caption, x + pad, y + 50);

  // Dot plot: column heights follow a normal curve centred on the middle bin.
  const centre = (bins - 1) / 2;
  const sigma = bins / 6;
  for (let b = 0; b < bins; b++) {
    const z = (b - centre) / sigma;
    const count = Math.round(maxDots * Math.exp(-(z * z) / 2));
    const fill = Math.abs(z) > 1.5 ? "#ec3013" : "#f3f2f2";
    ctx.fillStyle = fill;
    for (let k = 0; k < count; k++) {
      ctx.beginPath();
      ctx.arc(x + pad + b * colW + colW / 2, baseY - k * pitch - pitch / 2, dotR, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}

/**
 * Render the Movers card and encode it as a PNG Blob.
 *
 * @param {Array<{team: string, previous: number, current: number, delta: number}>} movers
 * @param {{season: number, cutoffWeek: number, baselineWeek: number}} meta
 * @param {typeof TEASER_FORMATS[keyof typeof TEASER_FORMATS]} [format=TEASER_FORMATS.landscape]
 * @returns {Promise<Blob>}
 */
async function buildTeaserBlob(movers, meta, format = TEASER_FORMATS.landscape) {
  const canvas = await renderTeaserCanvas(movers, meta, format);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not encode the teaser image."));
    }, "image/png");
  });
}
