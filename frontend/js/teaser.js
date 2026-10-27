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
 * like a bell curve, the outer tails in red, and a caption with the total
 * number of individual game outcomes simulated across the run. Decorative,
 * not a chart of real data.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{x: number, y: number, width: number, height: number}} box
 * @param {{totalGameSimulations?: number}} meta
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

  // Caption: the real total game-outcome count when the run reports it.
  const caption = meta.totalGameSimulations
    ? `${meta.totalGameSimulations.toLocaleString("en-US")} GAME SIMULATIONS`
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

// --- Wild Card bracket card (AFC/NFC, Simulated only, 9:16 Story only) ----

const TEASER_WC_LOGO_SIZE = 100;
const TEASER_WC_MATCHUPS = [[2, 7], [3, 6], [4, 5]];

/**
 * Load a conference mark (afc.png/nfc.png) the same way team logos load.
 *
 * @param {"AFC"|"NFC"} conference
 * @returns {Promise<HTMLImageElement|null>}
 */
function _loadConferenceLogo(conference) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = `img/logos/${conference.toLowerCase()}.png`;
  });
}

/**
 * Draw one team row shared by the bye row and the matchup rows: seed, logo,
 * name, record/division, and a strength stat on the right. `tint` picks the
 * row's fill ("fav" = the matchup favorite's accent tint, "bye" = the bye
 * row's neutral tint, "" = plain white) — mirrors the live Wild Card page's
 * `.fav`/`.mdn-wc-bye`/`.mdn-wc-team` treatment.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{x: number, y: number, w: number, h: number}} box
 * @param {Object} team - One team entry from POST /api/wildcard.
 * @param {HTMLCanvasElement|null} logo
 * @param {"fav"|"bye"|""} tint
 * @param {string|null} subLabel - Extra muted line under record/division (bye row only).
 * @param {{headingFont: string, bodyFont: string}} fonts
 */
function _drawWcTeamRow(ctx, box, team, logo, tint, subLabel, fonts) {
  const { headingFont, bodyFont } = fonts;
  const { x, y, w, h } = box;

  ctx.fillStyle = tint === "fav" ? "#fdeae5" : tint === "bye" ? "#f7f6f6" : "#ffffff";
  ctx.fillRect(x, y, w, h);
  if (tint === "fav") {
    ctx.fillStyle = "#ec3013";
    ctx.fillRect(x, y, 6, h);
  }

  const padX = 24;
  const seedColW = 56;
  ctx.textBaseline = "middle";
  ctx.textAlign = "right";
  ctx.fillStyle = "#8a8785";
  ctx.font = headingFont.replace("%s", String(Math.round(h * 0.16)));
  ctx.fillText(String(team.seed), x + padX + seedColW, y + h / 2);
  ctx.textAlign = "left";

  const logoSize = Math.min(h - 28, TEASER_WC_LOGO_SIZE);
  const logoX = x + padX + seedColW + 16;
  if (logo) {
    const scale = Math.min(logoSize / logo.width, logoSize / logo.height, 1);
    const dw = logo.width * scale;
    const dh = logo.height * scale;
    ctx.drawImage(logo, logoX + (logoSize - dw) / 2, y + (h - dh) / 2, dw, dh);
  }

  const textX = logoX + logoSize + 20;
  const statW = 170;
  const rightEdge = x + w - padX;
  const nameMaxW = rightEdge - statW - 24 - textX;

  const lines = subLabel ? 3 : 2;
  const nameY = lines === 3 ? y + h * 0.3 : y + h * 0.38;
  const subY = lines === 3 ? y + h * 0.56 : y + h * 0.68;
  const subLabelY = y + h * 0.82;

  ctx.fillStyle = "#161514";
  ctx.font = _fitFont(ctx, headingFont, team.team.toUpperCase(), Math.round(h * 0.26), nameMaxW);
  ctx.textBaseline = "alphabetic";
  ctx.fillText(team.team.toUpperCase(), textX, nameY);

  ctx.fillStyle = "#6b6866";
  ctx.font = bodyFont.replace("%s", String(Math.round(h * 0.13)));
  ctx.fillText(`${team.record || "0-0-0"} · ${team.division || ""}`, textX, subY);

  if (subLabel) {
    ctx.fillStyle = "#8a8785";
    ctx.font = bodyFont.replace("%s", String(Math.round(h * 0.11)));
    ctx.fillText(subLabel, textX, subLabelY);
  }

  // Right stat: strength rating.
  ctx.textAlign = "right";
  ctx.textBaseline = "alphabetic";
  ctx.fillStyle = "#161514";
  ctx.font = headingFont.replace("%s", String(Math.round(h * 0.22)));
  ctx.fillText(team.strength != null ? team.strength.toFixed(3) : "1.000", rightEdge, y + h * 0.46);
  ctx.fillStyle = "#8a8785";
  ctx.font = bodyFont.replace("%s", String(Math.round(h * 0.1)));
  ctx.fillText("STRENGTH", rightEdge, y + h * 0.68);
  ctx.textAlign = "left";
}

/**
 * Draw the Wild Card bracket card onto a fresh canvas: the conference's #1
 * seed on a bye, then the three 2v7/3v6/4v5 matchups with the higher-
 * strength team tinted as favorite — the same visual language as the Movers
 * card's header/footer and the live Wild Card page's row layout.
 *
 * @param {"AFC"|"NFC"} conference
 * @param {Object[]} teams - All 16 teams for this conference (POST /api/wildcard, Simulated).
 * @param {{season: number, cutoffWeek: number, version?: string, totalGameSimulations?: number}} meta
 * @param {typeof TEASER_FORMATS.story} [format=TEASER_FORMATS.story] - 9:16 only; other formats aren't supported.
 * @returns {Promise<HTMLCanvasElement>}
 */
async function renderWildcardTeaserCanvas(conference, teams, meta, format = TEASER_FORMATS.story) {
  const canvas = document.createElement("canvas");
  canvas.width = format.width;
  canvas.height = format.height;
  const ctx = canvas.getContext("2d");

  const bySeed = {};
  for (const t of teams) bySeed[t.seed] = t;
  const bye = bySeed[1];
  const matchups = TEASER_WC_MATCHUPS.map(([h, a]) => ({ homeSeed: h, awaySeed: a, home: bySeed[h], away: bySeed[a] }));
  const rowTeams = [bye, ...matchups.flatMap((m) => [m.home, m.away])].filter(Boolean);

  const [teamLogos, confLogoImg] = await Promise.all([
    Promise.all(rowTeams.map((t) => _loadTeamLogo(t.team))),
    _loadConferenceLogo(conference),
  ]);
  const logoByTeam = {};
  rowTeams.forEach((t, i) => {
    logoByTeam[t.team] = teamLogos[i] ? _shrinkLogo(teamLogos[i], TEASER_WC_LOGO_SIZE) : null;
  });
  const confLogo = confLogoImg ? _shrinkLogo(confLogoImg, 92) : null;

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

  _drawWildcardCard(ctx, conference, bye, matchups, logoByTeam, confLogo, meta, format, { headingFont, bodyFont });
  return canvas;
}

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {"AFC"|"NFC"} conference
 * @param {Object|undefined} bye
 * @param {Array<{homeSeed: number, awaySeed: number, home: Object|undefined, away: Object|undefined}>} matchups
 * @param {Object<string, HTMLCanvasElement|null>} logoByTeam
 * @param {HTMLCanvasElement|null} confLogo
 * @param {{season: number, cutoffWeek: number, version?: string, totalGameSimulations?: number}} meta
 * @param {typeof TEASER_FORMATS.story} format
 * @param {{headingFont: string, bodyFont: string}} fonts
 */
function _drawWildcardCard(ctx, conference, bye, matchups, logoByTeam, confLogo, meta, format, fonts) {
  const { headingFont, bodyFont } = fonts;
  const W = format.width;
  const H = format.height;
  // Deliberately slimmer than the Movers card's Story topSafe (200px): this
  // card is dense with bracket content, not a short list, so a big top
  // margin reads as wasted space rather than safe-zone breathing room.
  const top = 60;
  const margin = 56;
  const contentW = W - 2 * margin;

  // Header band.
  ctx.fillStyle = "#f3f2f2";
  ctx.fillRect(0, 0, W, H);
  const bandBottom = top + 120;
  ctx.fillStyle = "#161514";
  ctx.fillRect(0, 0, W, bandBottom);
  ctx.fillStyle = "#ec3013";
  ctx.fillRect(0, bandBottom, W, 6);

  ctx.fillStyle = "#f3f2f2";
  ctx.textBaseline = "middle";
  ctx.font = headingFont.replace("%s", "44");
  ctx.fillText("NFL PLAYOFF RANKINGS SIM", margin, top + 60);
  ctx.font = bodyFont.replace("%s", "28");
  ctx.textAlign = "right";
  ctx.fillText(`${meta.season} · Week ${meta.cutoffWeek}`, W - margin, top + 60);
  ctx.textAlign = "left";

  // Headline: conference mark + "AFC/NFC WILD CARD".
  ctx.textBaseline = "alphabetic";
  let headlineX = margin;
  if (confLogo) {
    ctx.drawImage(confLogo, margin, bandBottom + 40, confLogo.width, confLogo.height);
    headlineX = margin + confLogo.width + 24;
  }
  const headline = `${conference} WILD CARD`;
  ctx.fillStyle = "#161514";
  ctx.font = _fitFont(ctx, headingFont, headline, 80, contentW - (headlineX - margin));
  ctx.fillText(headline, headlineX, bandBottom + 130);

  ctx.fillStyle = "#332f2d";
  ctx.font = bodyFont.replace("%s", "30");
  ctx.fillText("Projected seeding — Simulated", margin, bandBottom + 184);

  // Footer baselines (same convention as the Movers card).
  const footerNameY = H - format.bottomSafe - 40;
  const footerDiscY = H - format.bottomSafe;
  const footerTop = footerNameY - 28;

  // Stylised "simulation" bell panel (same as the Movers Story card), sized
  // down slightly to leave more room for the bracket content.
  const bellH = 200;
  const bellBottom = footerTop - 40;
  const bellTop = bellBottom - bellH;

  // Layout the bye row + 3 matchups (label strip + 2 team rows each) to fill
  // the space between the subtitle and the bell panel.
  const bodyTop = bandBottom + 230;
  const availableH = bellTop - 32 - bodyTop;
  const blockGap = 14;
  const labelH = 46;
  const rowGap = 3;
  const byeH = 190;
  const teamRowH = (availableH - byeH - 3 * blockGap - 3 * labelH - 6 * rowGap) / 6;

  let y = bodyTop;
  if (bye) {
    _drawWcTeamRow(ctx, { x: margin, y, w: contentW, h: byeH }, bye, logoByTeam[bye.team], "bye", "FIRST-ROUND BYE", fonts);
  }
  y += byeH + blockGap;

  for (const m of matchups) {
    if (!m.home || !m.away) continue;
    ctx.fillStyle = "#ebe9e8";
    ctx.fillRect(margin, y, contentW, labelH);
    ctx.fillStyle = "#6b6866";
    ctx.font = headingFont.replace("%s", "22");
    ctx.textBaseline = "middle";
    ctx.fillText(`${m.homeSeed} VS ${m.awaySeed}`, margin + 24, y + labelH / 2);
    y += labelH;

    const homeFav = (m.home.strength || 0) >= (m.away.strength || 0);
    _drawWcTeamRow(ctx, { x: margin, y, w: contentW, h: teamRowH }, m.home, logoByTeam[m.home.team], homeFav ? "fav" : "", null, fonts);
    y += teamRowH + rowGap;
    _drawWcTeamRow(ctx, { x: margin, y, w: contentW, h: teamRowH }, m.away, logoByTeam[m.away.team], homeFav ? "" : "fav", null, fonts);
    y += teamRowH + blockGap;
  }

  _drawBellPanel(ctx, { x: margin, y: bellTop, width: contentW, height: bellH }, meta, fonts);

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
 * Render the Wild Card bracket card and encode it as a PNG Blob.
 *
 * @param {"AFC"|"NFC"} conference
 * @param {Object[]} teams - All 16 teams for this conference (POST /api/wildcard, Simulated).
 * @param {{season: number, cutoffWeek: number, version?: string, totalGameSimulations?: number}} meta
 * @param {typeof TEASER_FORMATS.story} [format=TEASER_FORMATS.story]
 * @returns {Promise<Blob>}
 */
async function buildWildcardTeaserBlob(conference, teams, meta, format = TEASER_FORMATS.story) {
  const canvas = await renderWildcardTeaserCanvas(conference, teams, meta, format);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not encode the Wild Card image."));
    }, "image/png");
  });
}

// --- Matchups card (next week's games, win/loss/tie odds, Story only) -----

// One brand color per team (by short name, same keys as TEAM_LOGO_IDS):
// the darker/more-saturated member of each team's two-color identity, so it
// stays legible as text on the card's light background — several teams'
// brighter accent (Steelers gold, Broncos/Bengals orange, Chargers powder
// blue, Dolphins aqua) fails text contrast at full brightness and is
// swapped for a deeper shade of the same hue instead.
const TEAM_COLORS = {
  "Steelers": "#101820", "Saints": "#9f8958", "Ravens": "#241773", "Browns": "#582c0e",
  "Bengals": "#c13d0f", "Jaguars": "#006778", "Texans": "#a71930", "Titans": "#0c2340",
  "Colts": "#002c5f", "Patriots": "#8c1d2b", "Bills": "#00338d", "Dolphins": "#00707a",
  "Lions": "#0076b6", "Vikings": "#4f2683", "Packers": "#203731", "Panthers": "#006ba6",
  "Rams": "#003594", "Cardinals": "#97233f", "49ers": "#aa0000", "Seahawks": "#002244",
  "Chiefs": "#c41230", "Broncos": "#b3480f", "Cowboys": "#041e42", "Giants": "#7a1726",
  "Eagles": "#004c54", "Commanders": "#5a1414", "Chargers": "#0066a1", "Buccaneers": "#b8090a",
  "Bears": "#0b162a", "Jets": "#115740", "Raiders": "#1a1d22", "Falcons": "#9e1a2d",
};

/**
 * Convert a "#rrggbb" hex color to {h, s, l} (h in degrees, s/l in 0-100).
 * @param {string} hex
 * @returns {{h: number, s: number, l: number}}
 */
function _hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0, s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  return { h, s: s * 100, l: l * 100 };
}

/** @param {number} h @param {number} s @param {number} l @returns {string} "#rrggbb" */
function _hslToHex(h, s, l) {
  s /= 100; l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  let r = 0, g = 0, b = 0;
  if (h < 60) [r, g, b] = [c, x, 0];
  else if (h < 120) [r, g, b] = [x, c, 0];
  else if (h < 180) [r, g, b] = [0, c, x];
  else if (h < 240) [r, g, b] = [0, x, c];
  else if (h < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const toHex = (v) => Math.round((v + m) * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

/** Circular distance between two hues in degrees (0-180). */
function _hueDist(h1, h2) {
  const d = Math.abs(h1 - h2) % 360;
  return d > 180 ? 360 - d : d;
}

/**
 * Group-header label for an instant's calendar day in `timeZone`, e.g.
 * "SUNDAY OCT 25, 2026" (assembled from parts, since en-US's own long
 * format puts a comma after the weekday).
 *
 * @param {Date} instant
 * @param {string} timeZone
 * @returns {string}
 */
function _dayHeaderLabel(instant, timeZone) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      weekday: "long", month: "short", day: "numeric", year: "numeric", timeZone,
    })
      .formatToParts(instant)
      .map((p) => [p.type, p.value]),
  );
  return `${parts.weekday} ${parts.month} ${parts.day}, ${parts.year}`.toUpperCase();
}

/**
 * Day group header for a matchup ("SUNDAY OCT 25, 2026"), from its kickoff
 * in Eastern Time — NFL broadcast days (Thursday/Sunday/Monday Night
 * Football) are named in ET wherever the viewer is, and a night game's UTC
 * date is already the next day. Falls back to the UTC `date` for results
 * without a kickoff (simulated before the field existed), parsed as UTC
 * midnight so it doesn't depend on the browser's timezone.
 *
 * @param {{kickoff?: string|null, date: string}} matchup
 * @returns {string}
 */
function _matchupDayLabel(matchup) {
  if (!matchup.kickoff) return _dayHeaderLabel(new Date(`${matchup.date}T00:00:00Z`), "UTC");
  return _dayHeaderLabel(new Date(matchup.kickoff), "America/New_York");
}

const _MATCHUP_BAR_LIGHTNESS_CLASH = 68;

/**
 * Bar-fill colors for one matchup row. Both the bar and the team
 * name/logo normally use the exact same canonical TEAM_COLORS entry — the
 * bar is only ever touched when the home and away team's hues are within
 * 30° of each other (same color family, e.g. two red-branded teams),
 * in which case the away segment alone is lightened to a pale tint so the
 * two segments still read as visually distinct. Home never changes.
 *
 * @param {string} homeHex
 * @param {string} awayHex
 * @returns {{homeBarColor: string, awayBarColor: string}}
 */
function _matchupBarColors(homeHex, awayHex) {
  const home = _hexToHsl(homeHex);
  const away = _hexToHsl(awayHex);
  const clash = _hueDist(home.h, away.h) < 30;
  return {
    homeBarColor: homeHex,
    awayBarColor: clash ? _hslToHex(away.h, Math.max(away.s, 35), _MATCHUP_BAR_LIGHTNESS_CLASH) : awayHex,
  };
}

// One-line method note on the Matchups card (must fit the card's 968px
// content width at 24px; _fitFont shrinks it otherwise).
const TEASER_MATCHUPS_METHOD_NOTE =
  "Team strength from this season's results only — no home field, weather, injuries, stats.";

const _FINAL_SCORE_LOSER_COLOR = "#b5b2b0";
const _FINAL_SCORE_TIE_COLOR = "#332f2d";

/**
 * Score colors for a completed matchup row: the winner's number in their
 * team color, the loser's grayed out; both a neutral dark on a tie.
 *
 * @param {{home_score: number, away_score: number}} matchup
 * @param {string} homeHex
 * @param {string} awayHex
 * @returns {{homeScoreColor: string, awayScoreColor: string}}
 */
function _finalScoreColors(matchup, homeHex, awayHex) {
  if (matchup.home_score === matchup.away_score) {
    return { homeScoreColor: _FINAL_SCORE_TIE_COLOR, awayScoreColor: _FINAL_SCORE_TIE_COLOR };
  }
  const homeWon = matchup.home_score > matchup.away_score;
  return {
    homeScoreColor: homeWon ? homeHex : _FINAL_SCORE_LOSER_COLOR,
    awayScoreColor: homeWon ? _FINAL_SCORE_LOSER_COLOR : awayHex,
  };
}

/**
 * Draw a completed game's middle section in place of the probability bar:
 * a large "home – away" score on the row's vertical midline (the same line
 * the team names are drawn on), with a small "FINAL" label just above it.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{barX: number, barW: number, midY: number, barH: number, h: number}} geom
 * @param {{home_score: number, away_score: number}} matchup
 * @param {string} homeColor
 * @param {string} awayColor
 * @param {{headingFont: string, bodyFont: string}} fonts
 */
function _drawFinalScore(ctx, geom, matchup, homeColor, awayColor, fonts) {
  const { headingFont, bodyFont } = fonts;
  const { barX, barW, midY, barH, h } = geom;
  const centerX = barX + barW / 2;
  const { homeScoreColor, awayScoreColor } = _finalScoreColors(matchup, homeColor, awayColor);
  // Capped so a short week's tall rows don't blow the score up past the
  // team names (which are width-capped by _fitFont the same way).
  const scorePx = Math.min(56, Math.max(20, Math.round(barH * 1.5)));

  ctx.textBaseline = "alphabetic";
  ctx.textAlign = "center";
  ctx.font = headingFont.replace("%s", String(Math.min(18, Math.max(11, Math.round(h * 0.13)))));
  ctx.fillStyle = "#8a8785";
  ctx.fillText("FINAL", centerX, midY - scorePx * 0.45 - 6);

  const homeText = String(matchup.home_score);
  const awayText = String(matchup.away_score);
  const sepText = " – ";
  ctx.font = headingFont.replace("%s", String(scorePx));
  const homeW = ctx.measureText(homeText).width;
  const sepW = ctx.measureText(sepText).width;
  const awayW = ctx.measureText(awayText).width;
  let x = centerX - (homeW + sepW + awayW) / 2;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  const scoreY = midY;
  ctx.fillStyle = homeScoreColor;
  ctx.fillText(homeText, x, scoreY);
  x += homeW;
  ctx.fillStyle = "#8a8785";
  ctx.fillText(sepText, x, scoreY);
  x += sepW;
  ctx.fillStyle = awayScoreColor;
  ctx.fillText(awayText, x, scoreY);
  ctx.textBaseline = "alphabetic";
}

/**
 * Draw one matchup row: home logo + name, a stacked home/tie/away
 * probability bar, away name + logo. The home% and away% labels sit flush
 * with the bar's left and right edges; the tie% label is centered over the
 * tie segment, clamped between them (measured with the real font metrics
 * via ctx.measureText, not estimated). A completed game
 * (matchup.completed) shows its final score there instead of the bar.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {{x: number, y: number, w: number, h: number}} box
 * @param {{home_team: string, away_team: string, home_win_probability: number, away_win_probability: number, tie_probability: number}} matchup
 * @param {HTMLCanvasElement|null} homeLogo
 * @param {HTMLCanvasElement|null} awayLogo
 * @param {{headingFont: string, bodyFont: string}} fonts
 */
function _drawMatchupRow(ctx, box, matchup, homeLogo, awayLogo, fonts) {
  const { headingFont, bodyFont } = fonts;
  const { x, y, w, h } = box;

  const homeColor = TEAM_COLORS[matchup.home_team] || "#161514";
  const awayColor = TEAM_COLORS[matchup.away_team] || "#161514";
  const { homeBarColor, awayBarColor } = _matchupBarColors(homeColor, awayColor);

  const teamColW = Math.min(240, w * 0.26);
  const gap = 16;
  const barX = x + teamColW + gap;
  const barW = w - 2 * teamColW - 2 * gap;
  const logoSize = Math.min(h - 20, 56);

  // Home team: logo, then name to its right.
  if (homeLogo) {
    const scale = Math.min(logoSize / homeLogo.width, logoSize / homeLogo.height, 1);
    const dw = homeLogo.width * scale, dh = homeLogo.height * scale;
    ctx.drawImage(homeLogo, x + (logoSize - dw) / 2, y + (h - dh) / 2, dw, dh);
  }
  ctx.textBaseline = "middle";
  ctx.fillStyle = homeColor;
  ctx.font = _fitFont(ctx, headingFont, matchup.home_team, Math.round(h * 0.34), teamColW - logoSize - 16);
  ctx.fillText(matchup.home_team, x + logoSize + 16, y + h / 2);

  // Away team: name right-aligned, then logo at the row's right edge.
  if (awayLogo) {
    const scale = Math.min(logoSize / awayLogo.width, logoSize / awayLogo.height, 1);
    const dw = awayLogo.width * scale, dh = awayLogo.height * scale;
    ctx.drawImage(awayLogo, x + w - logoSize + (logoSize - dw) / 2, y + (h - dh) / 2, dw, dh);
  }
  ctx.textAlign = "right";
  ctx.fillStyle = awayColor;
  ctx.font = _fitFont(ctx, headingFont, matchup.away_team, Math.round(h * 0.34), teamColW - logoSize - 16);
  ctx.fillText(matchup.away_team, x + w - logoSize - 16, y + h / 2);
  ctx.textAlign = "left";

  // Stacked bar: home | away | tie, left to right.
  const barH = Math.max(18, Math.round(h * 0.3));
  const barY = y + h / 2 + 4;
  const labelY = barY - 10;

  if (matchup.completed) {
    _drawFinalScore(ctx, { barX, barW, midY: y + h / 2, barH, h }, matchup, homeColor, awayColor, fonts);
    return;
  }

  const homeW = (matchup.home_win_probability / 100) * barW;
  const awayW = (matchup.away_win_probability / 100) * barW;
  const tieW = Math.max(0, barW - homeW - awayW);
  ctx.fillStyle = homeBarColor;
  ctx.fillRect(barX, barY, homeW, barH);
  ctx.fillStyle = "#c9c6c4";
  ctx.fillRect(barX + homeW, barY, tieW, barH);
  ctx.fillStyle = awayBarColor;
  ctx.fillRect(barX + homeW + tieW, barY, awayW, barH);

  // Percent labels above the bar, in the same order as its segments: home
  // flush with the left edge, away flush with the right edge, and tie
  // centered over its own segment — clamped so it keeps clear of both.
  const labelFontPx = Math.max(13, Math.round(h * 0.16));
  ctx.textBaseline = "alphabetic";

  const homeText = `${matchup.home_win_probability.toFixed(1)}%`;
  const awayText = `${matchup.away_win_probability.toFixed(1)}%`;
  const tieText = `${matchup.tie_probability.toFixed(1)}%`;

  ctx.font = headingFont.replace("%s", String(labelFontPx));
  ctx.fillStyle = homeColor;
  ctx.fillText(homeText, barX, labelY);
  const homeTextW = ctx.measureText(homeText).width;

  ctx.fillStyle = awayColor;
  const awayTextW = ctx.measureText(awayText).width;
  ctx.fillText(awayText, barX + barW - awayTextW, labelY);

  ctx.font = bodyFont.replace("%s", String(Math.max(11, labelFontPx - 3)));
  ctx.fillStyle = "#8a8785";
  const tieTextW = ctx.measureText(tieText).width;
  const minLeft = barX + homeTextW + 10;
  const maxLeft = barX + barW - awayTextW - 10 - tieTextW;
  const tieLeft = barX + homeW + tieW / 2 - tieTextW / 2;
  ctx.fillText(tieText, Math.min(Math.max(tieLeft, minLeft), maxLeft), labelY);
}

/**
 * "Data-driven ratings: N% — <label>" line for the Matchups card, the same
 * simulation-quality indicator the Simulations page shows under its Results
 * line (_renderDataConfidence in simulation.js). Empty when the result
 * lacks the field (e.g. produced before it existed).
 *
 * @param {{dataDrivenPct?: number, dataConfidence?: string}} meta
 * @returns {string}
 */
function _matchupsQualityLine(meta) {
  const pct = meta.dataDrivenPct;
  if (typeof pct !== "number" || !Number.isFinite(pct)) return "";
  const label = meta.dataConfidence ? ` — ${meta.dataConfidence}` : "";
  return `Data-driven ratings: ${Math.round(pct)}%${label}`;
}

/**
 * Draw the Matchups card onto a fresh canvas: one row per game in the
 * matchups week (see matchups_week in doc/api.md), each a stacked home/away/tie probability bar between the
 * two teams' logo and name — or, for a game already played, its final
 * score. Same header/footer/bell-panel language as the Movers and Wild
 * Card cards.
 *
 * @param {Array<{game_id: string, week: number, date: string, home_team: string, away_team: string, home_win_probability: number, away_win_probability: number, tie_probability: number}>} matchups
 * @param {{season: number, cutoffWeek: number, nextWeek: number, version?: string, iterations?: number, totalGameSimulations?: number, dataDrivenPct?: number, dataConfidence?: string}} meta
 * @param {typeof TEASER_FORMATS.story} [format=TEASER_FORMATS.story] - 9:16 only; other formats aren't supported.
 * @returns {Promise<HTMLCanvasElement>}
 */
async function renderMatchupsTeaserCanvas(matchups, meta, format = TEASER_FORMATS.story) {
  const canvas = document.createElement("canvas");
  canvas.width = format.width;
  canvas.height = format.height;
  const ctx = canvas.getContext("2d");

  const teams = Array.from(new Set(matchups.flatMap((m) => [m.home_team, m.away_team])));
  const logos = (await Promise.all(teams.map((t) => _loadTeamLogo(t)))).map(
    (img) => (img ? _shrinkLogo(img, 112) : null),
  );
  const logoByTeam = {};
  teams.forEach((t, i) => { logoByTeam[t] = logos[i]; });

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

  _drawMatchupsCard(ctx, matchups, logoByTeam, meta, format, { headingFont, bodyFont });
  return canvas;
}

/**
 * @param {CanvasRenderingContext2D} ctx
 * @param {Array<Object>} matchups
 * @param {Object<string, HTMLCanvasElement|null>} logoByTeam
 * @param {{season: number, cutoffWeek: number, nextWeek: number, version?: string, iterations?: number, totalGameSimulations?: number, dataDrivenPct?: number, dataConfidence?: string}} meta
 * @param {typeof TEASER_FORMATS.story} format
 * @param {{headingFont: string, bodyFont: string}} fonts
 */
function _drawMatchupsCard(ctx, matchups, logoByTeam, meta, format, fonts) {
  const { headingFont, bodyFont } = fonts;
  const W = format.width;
  const H = format.height;
  // Tighter than the Movers/Wild Card cards' 60: the band has no content
  // above the header art, and the list below needs the room more.
  const top = 28;
  const margin = 56;
  const contentW = W - 2 * margin;

  // Header band (brand + season only — the headline below already states
  // the week, so repeating it in the header badge is redundant).
  ctx.fillStyle = "#eeece9";
  ctx.fillRect(0, 0, W, H);
  const bandBottom = top + 120;
  ctx.fillStyle = "#161514";
  ctx.fillRect(0, 0, W, bandBottom);
  ctx.fillStyle = "#ec3013";
  ctx.fillRect(0, bandBottom, W, 6);
  _drawMatchupsHeaderArt(ctx, top);

  ctx.fillStyle = "#f3f2f2";
  ctx.textBaseline = "middle";
  ctx.font = headingFont.replace("%s", "44");
  ctx.fillText("NFL PLAYOFF RANKINGS SIM", margin, top + 60);
  ctx.font = bodyFont.replace("%s", "28");
  ctx.textAlign = "right";
  ctx.fillText(`${meta.season} SEASON`, W - margin, top + 60);
  ctx.textAlign = "left";

  // Headline + subtitle.
  ctx.textBaseline = "alphabetic";
  const headline = `WEEK ${meta.nextWeek} MATCHUPS`;
  ctx.fillStyle = "#161514";
  ctx.font = _fitFont(ctx, headingFont, headline, 80, contentW);
  ctx.fillText(headline, margin, bandBottom + 100);
  ctx.fillStyle = "#332f2d";
  const finalCount = matchups.filter((m) => m.completed).length;
  let subtitle = meta.iterations
    ? `Win probabilities across ${meta.iterations.toLocaleString("en-US")} simulations per game (home vs. tie vs. away)`
    : "Win probabilities across simulated games (home vs. tie vs. away)";
  if (finalCount > 0) subtitle += ` · ${finalCount} ${finalCount === 1 ? "game" : "games"} final`;
  ctx.font = _fitFont(ctx, bodyFont, subtitle, 28, contentW);
  ctx.fillText(subtitle, margin, bandBottom + 148);

  // Simulation-quality line, then the method explainer for viewers who
  // see the card on social media without any context about the app. The
  // game list starts below whichever lines were drawn.
  let textY = bandBottom + 148;
  const qualityLine = _matchupsQualityLine(meta);
  if (qualityLine) {
    textY += 38;
    ctx.font = _fitFont(ctx, headingFont, qualityLine, 24, contentW);
    ctx.fillText(qualityLine, margin, textY);
  }
  textY += 36;
  ctx.fillStyle = "#6b6866";
  ctx.font = _fitFont(ctx, bodyFont, TEASER_MATCHUPS_METHOD_NOTE, 24, contentW);
  ctx.fillText(TEASER_MATCHUPS_METHOD_NOTE, margin, textY);

  // Footer baselines (same convention as Movers/Wild Card). Unlike those
  // two cards, there's no "stylised simulation" bell panel here — this
  // card already has its own simulation-themed art in the header, and the
  // row list needs the extra vertical room more than a second decoration.
  const footerNameY = H - format.bottomSafe - 40;
  const footerDiscY = H - format.bottomSafe;
  const footerTop = footerNameY - 28;

  const listTop = textY + 42;
  const listBottom = footerTop - 32;
  const gap = 6;
  const n = matchups.length;

  if (n === 0) {
    ctx.fillStyle = "#6b6866";
    ctx.font = bodyFont.replace("%s", "28");
    ctx.fillText("No games scheduled for this week.", margin, listTop + 50);
  } else {
    // Group consecutive games by Eastern Time day ("SUNDAY OCT 25, 2026",
    // etc.); games already arrive in kickoff order.
    const groupLabelAt = matchups.map((m) => _matchupDayLabel(m));
    const groupStartLabel = [];
    let prevLabel = null;
    let groupCount = 0;
    for (let i = 0; i < n; i++) {
      if (groupLabelAt[i] !== prevLabel) {
        groupStartLabel[i] = groupLabelAt[i];
        groupCount++;
        prevLabel = groupLabelAt[i];
      }
    }

    // The day label sits at the bottom of its (short) header band so it
    // reads as belonging to the games below it, not floating between groups.
    const groupHeaderH = 30;
    const rowH = (listBottom - listTop - gap * (n - 1) - groupCount * groupHeaderH) / n;

    let y = listTop;
    for (let i = 0; i < n; i++) {
      const m = matchups[i];
      const label = groupStartLabel[i];
      if (label !== undefined) {
        ctx.textBaseline = "alphabetic";
        ctx.fillStyle = "#8a8785";
        ctx.font = headingFont.replace("%s", "18");
        ctx.fillText(label, margin, y + 24);
        const labelW = ctx.measureText(label).width;
        ctx.fillStyle = "#ebe9e8";
        ctx.fillRect(margin + labelW + 16, y + 17, contentW - labelW - 16, 1.5);
        y += groupHeaderH;
      } else {
        // Thin separator between games of the same day.
        ctx.fillStyle = "#d6d3d0";
        ctx.fillRect(margin, y, contentW, 1);
      }
      _drawMatchupRow(
        ctx,
        { x: margin, y: y + 8, w: contentW, h: rowH - 8 },
        m,
        logoByTeam[m.home_team],
        logoByTeam[m.away_team],
        fonts,
      );
      y += rowH + gap;
    }
  }

  // Footer band: black like the header, with the same red accent stripe
  // mirrored to its top edge, and text colors inverted to stay legible.
  ctx.fillStyle = "#ec3013";
  ctx.fillRect(0, footerTop - 6, W, 6);
  ctx.fillStyle = "#161514";
  ctx.fillRect(0, footerTop, W, H - footerTop);

  ctx.textBaseline = "alphabetic";
  const footerName = meta.version ? `${TEASER_APP_NAME} v${meta.version}` : TEASER_APP_NAME;
  ctx.fillStyle = "#f3f2f2";
  ctx.font = _fitFont(ctx, headingFont, footerName, 28, contentW);
  ctx.fillText(footerName, margin, footerNameY);
  ctx.fillStyle = "#c9c6c4";
  ctx.font = bodyFont.replace("%s", "24");
  ctx.fillText("Independent project, not affiliated with the NFL", margin, footerDiscY);
}

/**
 * Header-band art for the Matchups card, ported from the design mockup:
 * a faint yard-line field texture, a bell-shaped outcome histogram (peak
 * picked out in accent red — the "statistical" half of the motif), and a
 * tilted laced-football silhouette (the "American football" half). All at
 * low opacity so the white header text stays fully legible on top.
 *
 * @param {CanvasRenderingContext2D} ctx
 * @param {number} top - The header band's own top (format.topSafe-style offset).
 */
function _drawMatchupsHeaderArt(ctx, top) {
  ctx.save();
  ctx.strokeStyle = "#f3f2f2";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([3, 16]);
  ctx.globalAlpha = 0.05;
  ctx.beginPath();
  ctx.moveTo(0, top + 24);
  ctx.lineTo(1080, top + 24);
  ctx.moveTo(0, top + 116);
  ctx.lineTo(1080, top + 116);
  ctx.stroke();
  ctx.restore();

  const bars = [
    { x: 610, h: 8, op: 0.22, color: "#f3f2f2" },
    { x: 630, h: 14, op: 0.28, color: "#f3f2f2" },
    { x: 650, h: 22, op: 0.35, color: "#f3f2f2" },
    { x: 670, h: 34, op: 0.45, color: "#f3f2f2" },
    { x: 690, h: 48, op: 0.55, color: "#ec3013" },
    { x: 710, h: 60, op: 0.85, color: "#ec3013" },
    { x: 730, h: 68, op: 0.98, color: "#ec3013" },
    { x: 750, h: 60, op: 0.85, color: "#ec3013" },
    { x: 770, h: 48, op: 0.55, color: "#ec3013" },
    { x: 790, h: 34, op: 0.45, color: "#f3f2f2" },
    { x: 810, h: 22, op: 0.35, color: "#f3f2f2" },
    { x: 830, h: 14, op: 0.28, color: "#f3f2f2" },
    { x: 850, h: 8, op: 0.22, color: "#f3f2f2" },
  ];
  const baseY = top + 118;
  ctx.save();
  for (const bar of bars) {
    ctx.globalAlpha = bar.op;
    ctx.fillStyle = bar.color;
    ctx.fillRect(bar.x, baseY - bar.h, 14, bar.h);
  }
  ctx.restore();

  ctx.save();
  ctx.strokeStyle = "#f3f2f2";
  ctx.lineWidth = 1.5;
  ctx.setLineDash([2, 6]);
  ctx.globalAlpha = 0.4;
  ctx.beginPath();
  ctx.moveTo(600, baseY);
  ctx.lineTo(872, baseY);
  ctx.stroke();
  ctx.restore();

  ctx.save();
  ctx.translate(730, top + 24);
  ctx.rotate((-20 * Math.PI) / 180);
  ctx.globalAlpha = 0.45;
  ctx.strokeStyle = "#f3f2f2";
  ctx.lineWidth = 2.2;
  ctx.beginPath();
  ctx.ellipse(0, 0, 22, 11, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ctx.moveTo(-14, 0);
  ctx.lineTo(14, 0);
  ctx.stroke();
  ctx.lineWidth = 1.3;
  for (const lx of [-5.5, 0, 5.5]) {
    ctx.beginPath();
    ctx.moveTo(lx, -3.5);
    ctx.lineTo(lx, 3.5);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * Render the Matchups card and encode it as a PNG Blob.
 *
 * @param {Array<Object>} matchups
 * @param {{season: number, cutoffWeek: number, nextWeek: number, version?: string, iterations?: number, totalGameSimulations?: number}} meta
 * @param {typeof TEASER_FORMATS.story} [format=TEASER_FORMATS.story]
 * @returns {Promise<Blob>}
 */
async function buildMatchupsTeaserBlob(matchups, meta, format = TEASER_FORMATS.story) {
  const canvas = await renderMatchupsTeaserCanvas(matchups, meta, format);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not encode the Matchups image."));
    }, "image/png");
  });
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
