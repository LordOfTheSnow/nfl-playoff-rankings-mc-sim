"""Standalone HTML export rendering.

Turns already-computed data (the same dicts the JSON API endpoints produce)
into static, self-contained HTML in the "Modernist" design system used by the
frontend. Two consumers in src/server.py drive this module:

- POST /api/export/page: a single combined page with inline CSS.
- POST /api/export/bundle: a ZIP of an index page, one page per section, and
  one page per team, all linking to a shared styles.css.

Every render function here is pure (data in, HTML string out) so the same
section renderers serve both modes — the caller supplies a `team_link`
callback that returns either an href for a team name (bundle mode) or None
(single-page mode, where team names render as plain text by design: a full
per-team breakdown on every mention would make that page unwieldy), and a
`logo` callback for team/conference logos (bundle mode: real `<img>` tags
against copied-in files; single-page mode: `<span>`s against CSS classes
whose `background-image` is a base64 data URI, defined once in the shared
`<style>` block so each logo's bytes appear once regardless of how many
times that team is mentioned — see `_build_logo_css`).

Markup deliberately mirrors the structural classes AND content the live
frontend uses for the same page (`.mdn-conf-head`, `.mdn-div-grid`,
`.mdn-card`, `.mdn-team-cell` logo+link wrapper, the `font:800 34px ...`
page-title style, the Tiebreaker column, etc. — see standings.js/
statistics.js/schedule-grid.js/simulation.js/schedule.js) rather than
inventing a simplified layout, so an export is a faithful static copy of
the corresponding live view, not an approximation of it.
"""

from __future__ import annotations

import base64
import io
import zipfile
from datetime import datetime
from html import escape
from importlib.metadata import metadata as _package_metadata
from typing import Any, Callable

from src.nfl_teams import ALL_TEAMS, get_team_conference, get_team_division

TeamLink = Callable[[str], "str | None"]
LogoRenderer = Callable[[str, int, int], str]

try:
    _PROJECT_META = _package_metadata("nfl-monte-carlo-simulator")
    _PROJECT_NAME = _PROJECT_META["Name"]
    _PROJECT_VERSION = _PROJECT_META["Version"]
except Exception:
    _PROJECT_NAME = "nfl-monte-carlo-simulator"
    _PROJECT_VERSION = "unknown"

_GITHUB_REPO_URL = "https://github.com/LordOfTheSnow/nfl-playoff-rankings-mc-sim"

# Primer Octicons "mark-github", inlined so the export stays fully
# self-contained (no external icon fetch needed to render offline).
_GITHUB_ICON_SVG = (
    '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" '
    'style="vertical-align:-2px" aria-hidden="true">'
    '<path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 '
    "0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 "
    "1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 "
    "0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 "
    "1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 "
    '1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8Z"></path></svg>'
)

_EXPORT_FOOTER = (
    '<div style="border-top:2px solid var(--mdn-divider);margin-top:32px"></div>'
    '<p class="mdn-hint" style="margin-top:12px;display:flex;align-items:center;gap:6px;flex-wrap:wrap">'
    f"Created by {escape(_PROJECT_NAME)} v{escape(_PROJECT_VERSION)}. — "
    f'<a href="{_GITHUB_REPO_URL}" target="_blank" rel="noopener noreferrer" '
    'style="color:inherit;display:inline-flex;align-items:center;gap:4px">'
    f"View on GitHub {_GITHUB_ICON_SVG}</a>"
    "</p>"
)

_CONFERENCES = ["AFC", "NFC"]
_DIVISIONS = ["East", "North", "South", "West"]

_GOOGLE_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" '
    'href="https://fonts.googleapis.com/css2?family=Archivo:ital,wght@0,400;0,700;0,800;1,400&display=swap">'
)

# Mirrors frontend/js/standings.js's TEAM_LOGO_IDS exactly (ESPN team logo
# ids, also the frontend/img/logos/<id>.png filenames).
TEAM_LOGO_IDS: dict[str, str] = {
    "Bills": "buf", "Dolphins": "mia", "Patriots": "ne", "Jets": "nyj",
    "Ravens": "bal", "Bengals": "cin", "Browns": "cle", "Steelers": "pit",
    "Texans": "hou", "Colts": "ind", "Jaguars": "jax", "Titans": "ten",
    "Chiefs": "kc", "Broncos": "den", "Chargers": "lac", "Raiders": "lv",
    "Cowboys": "dal", "Eagles": "phi", "Giants": "nyg", "Commanders": "wsh",
    "Bears": "chi", "Lions": "det", "Packers": "gb", "Vikings": "min",
    "Falcons": "atl", "Panthers": "car", "Saints": "no", "Buccaneers": "tb",
    "Cardinals": "ari", "Rams": "lar", "49ers": "sf", "Seahawks": "sea",
}

# Every logo id an export might reference: all 32 team ids plus the two
# conference marks (afc.png/nfc.png) shown in conference headers.
ALL_LOGO_IDS: list[str] = sorted(set(TEAM_LOGO_IDS.values()) | {"afc", "nfc"})


def _slug(team_name: str) -> str:
    """Filesystem/URL-safe id for a team, e.g. "Kansas City Chiefs" isn't a
    real case here (all 32 names in nfl_teams.py are single tokens like
    "Chiefs" or "49ers"), so a plain lowercase is sufficient and collision-free."""
    return team_name.lower()


def bundle_team_link(team_name: str) -> str:
    return f"team-{_slug(team_name)}.html"


def bundle_logo(logo_id: str, width: int, height: int) -> str:
    """Real <img> tag against a file copied into the bundle's img/logos/ —
    the same relative path convention the live frontend uses."""
    if not logo_id:
        return ""
    return f'<img src="img/logos/{logo_id}.png" width="{width}" height="{height}" alt="">'


def _build_logo_css(logos: dict[str, bytes]) -> str:
    """One `.logo-<id>{background-image:url(data:...)}` rule per logo, so a
    single-page export embeds each logo's bytes exactly once no matter how
    many rows/headers reference it."""
    rules = []
    for logo_id, content in logos.items():
        b64 = base64.b64encode(content).decode("ascii")
        rules.append(f".logo-{logo_id}{{background-image:url(data:image/png;base64,{b64})}}")
    return "".join(rules)


def make_inline_logo_renderer() -> LogoRenderer:
    """Logo renderer for the single-page export: a <span> sized inline,
    painted via the `.logo-<id>` background-image class (see _build_logo_css)."""

    def _inline(logo_id: str, width: int, height: int) -> str:
        if not logo_id:
            return ""
        return (
            f'<span class="logo-{logo_id}" style="display:inline-block;width:{width}px;'
            f"height:{height}px;background-size:contain;background-repeat:no-repeat;"
            'background-position:center;vertical-align:middle"></span>'
        )

    return _inline


def _team_ref(
    team_name: str,
    team_link: TeamLink,
    logo: LogoRenderer,
    *,
    logo_size: int = 20,
    link_class: str = "mdn-team-link",
) -> str:
    logo_html = logo(TEAM_LOGO_IDS.get(team_name, ""), logo_size, logo_size)
    safe = escape(team_name)
    href = team_link(team_name)
    if href is None:
        return f"{logo_html} {safe}" if logo_html else safe
    return f'<a class="{link_class}" href="{escape(href)}">{logo_html} {safe}</a>'


def _page_shell(
    title: str,
    body: str,
    *,
    inline_css: str | None = None,
    css_href: str | None = None,
    logo_css: str = "",
) -> str:
    if inline_css is not None:
        style_tag = f"<style>{inline_css}{logo_css}</style>"
    else:
        style_tag = f'<link rel="stylesheet" href="{escape(css_href or "styles.css")}">'
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{escape(title)}</title>"
        f"{_GOOGLE_FONT_LINK}{style_tag}</head>"
        '<body><main class="mdn-container mdn-main"><div class="mdn-page">'
        f"{body}{_EXPORT_FOOTER}</div></main></body></html>"
    )


def _page_title(text: str, subtitle: str = "") -> str:
    """The branded page-title treatment used by every live page's own <h1>
    (see e.g. schedule-grid.js's `font:800 34px var(--mdn-font-heading)`)."""
    sub = f'<p class="mdn-hint" style="margin:0 0 20px">{escape(subtitle)}</p>' if subtitle else ""
    return (
        f'<h1 style="font:800 34px var(--mdn-font-heading);margin:0 0 6px">{escape(text)}</h1>'
        f"{sub}"
    )


def _section_divider(kicker: str) -> str:
    """A labeled rule breaking up sections on the combined single page,
    mirroring the "Results" divider on the live Simulations page."""
    return (
        '<div style="display:flex;align-items:baseline;justify-content:space-between;margin:28px 0 2px">'
        f'<span class="mdn-card-kicker" style="font-size:11px">{escape(kicker)}</span></div>'
        '<div style="border-top:2px solid var(--mdn-divider);margin-bottom:18px"></div>'
    )


def _conf_head(conf: str, logo: LogoRenderer, title: str | None = None) -> str:
    """Conference header with logo + <h2>, matching standings.js's
    buildConferenceSection (and simulation.js's per-conference tables)."""
    logo_html = logo(conf.lower(), 26, 26)
    return f'<div class="mdn-conf-head">{logo_html}<h2>{escape(title or conf)}</h2></div>'


def _tiebreaker_tag(tiebreaker: str | None) -> str:
    """Bordered "Tiebreaker" badge — the server only sends a short code
    (e.g. "Pts +13"), same as live's _buildTiebreakerTag but without the
    hover tooltip (no rival-team/rule-name context to add in a static export)."""
    if not tiebreaker:
        return ""
    return f'<span class="mdn-tag mdn-tag-outline">{escape(tiebreaker)}</span>'


def _division_table(teams: list[dict[str, Any]], team_link: TeamLink, logo: LogoRenderer) -> str:
    rows = []
    for t in teams:
        leader_cls = ' class="mdn-leader"' if t.get("is_division_champion") else ""
        rows.append(
            f"<tr{leader_cls}>"
            f'<td class="mdn-tm"><div class="mdn-team-cell">{_team_ref(t["team"], team_link, logo)}</div></td>'
            f'<td class="mdn-num">{t["wins"]}</td>'
            f'<td class="mdn-num">{t["losses"]}</td>'
            f'<td class="mdn-num">{t["ties"]}</td>'
            f'<td class="mdn-num">{t["win_percentage"]:.3f}</td>'
            f'<td class="mdn-num">{escape(t["division_record"])}</td>'
            f'<td class="mdn-num">{escape(t["conference_record"])}</td>'
            f'<td class="mdn-num">{t["games_behind"]}</td>'
            f'<td class="mdn-num">{t["strength"]:.3f}</td>'
            f'<td>{_tiebreaker_tag(t.get("tiebreaker"))}</td>'
            f"</tr>"
        )
    return (
        '<table class="mdn-led-table">'
        "<thead><tr><th>Team</th><th class=\"mdn-num\">W</th><th class=\"mdn-num\">L</th>"
        "<th class=\"mdn-num\">T</th><th class=\"mdn-num\">Pct</th><th class=\"mdn-num\">Div</th>"
        "<th class=\"mdn-num\">Conf</th><th class=\"mdn-num\">GB</th><th class=\"mdn-num\">Str</th>"
        "<th>Tiebreaker</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


# --- Standings ---------------------------------------------------------

def render_standings_content(
    conferences: dict[str, dict[str, list[dict[str, Any]]]], team_link: TeamLink, logo: LogoRenderer
) -> str:
    """Conference header + 2-column division grid, mirroring
    standings.js's buildConferenceSection/buildDivisionSection."""
    parts = []
    for conf in _CONFERENCES:
        parts.append(_conf_head(conf, logo))
        parts.append('<div class="mdn-div-grid">')
        for div in _DIVISIONS:
            teams = conferences.get(conf, {}).get(div, [])
            parts.append(
                f'<div><div class="mdn-div-lbl">{escape(div)}</div>'
                f"{_division_table(teams, team_link, logo)}</div>"
            )
        parts.append("</div>")
    return "".join(parts)


# --- Statistics ---------------------------------------------------------
# Mirrors statistics.js exactly: one Game Outcomes ledger table (bar rows +
# a plain Average Score row + two streak rows) and a separate Score Margin
# Distribution card of bar rows (a CSS grid, not a table) — see
# _renderGameOutcomesCard/_barRow/_plainRow/_streakRow/_renderMarginDistributionCard.

def _bar_row(label: str, value: int, pct: float) -> str:
    return (
        f"<tr><td>{escape(label)}</td><td class=\"mdn-num\">"
        '<div style="display:grid;grid-template-columns:100px 110px;column-gap:10px;'
        'align-items:center;justify-content:end">'
        f'<div class="mdn-bar-track" style="width:100px"><div class="mdn-bar-fill" style="width:{pct}%"></div></div>'
        f'<span><span style="font-weight:700">{value}</span> <span class="mdn-hint">({pct}%)</span></span>'
        "</div></td></tr>"
    )


def _plain_row(label: str, value: str, detail: str) -> str:
    return (
        f"<tr><td>{escape(label)}</td><td class=\"mdn-num\">"
        f'<span style="font-weight:700">{escape(value)}</span> <span class="mdn-hint">{escape(detail)}</span>'
        "</td></tr>"
    )


def _streak_row(label: str, streaks: list[dict[str, Any]], team_link: TeamLink, logo: LogoRenderer) -> str:
    if not streaks:
        return f'<tr><td>{escape(label)}</td><td class="mdn-num"><span class="mdn-hint">No data</span></td></tr>'
    chips = []
    for s in streaks:
        logo_html = logo(TEAM_LOGO_IDS.get(s["team"], ""), 18, 18)
        href = team_link(s["team"])
        name_html = (
            f'<a class="mdn-team-link" href="{escape(href)}">{escape(s["team"])}</a>'
            if href is not None
            else f'<span class="mdn-team-link">{escape(s["team"])}</span>'
        )
        detail = f'{s["streak"]} games (week {s["from_week"]}–{s["to_week"]})'
        chips.append(
            '<span style="display:inline-flex;align-items:center;gap:6px">'
            f'{logo_html}{name_html}<span class="mdn-hint">— {escape(detail)}</span></span>'
        )
    return (
        f"<tr><td>{escape(label)}</td><td class=\"mdn-num\">"
        '<div style="display:flex;flex-wrap:wrap;gap:6px 10px;justify-content:flex-end">'
        f"{''.join(chips)}</div></td></tr>"
    )


def _margin_row(m: dict[str, Any]) -> str:
    return (
        '<div style="display:grid;grid-template-columns:80px 1fr 100px;column-gap:12px;'
        'align-items:center;padding:6px 0;border-bottom:1px solid var(--mdn-divider)">'
        f'<span style="font-size:12px;font-weight:700">{escape(m["label"])}</span>'
        f'<div class="mdn-bar-track"><div class="mdn-bar-fill" style="width:{m["pct"]}%"></div></div>'
        '<span style="text-align:right;font-size:12px;font-variant-numeric:tabular-nums">'
        f'<span style="font-weight:700">{m["count"]}</span> <span class="mdn-hint">({m["pct"]}%)</span></span>'
        "</div>"
    )


def render_statistics_content(stats: dict[str, Any], team_link: TeamLink, logo: LogoRenderer) -> str:
    rows = [
        _bar_row("Home Wins", stats["home_wins"], stats["home_wins_pct"]),
        _bar_row("Away Wins", stats["away_wins"], stats["away_wins_pct"]),
        _bar_row("Ties", stats["ties"], stats["ties_pct"]),
        _bar_row("Overtime Games", stats["overtime_games"], stats["overtime_pct"]),
        _bar_row("One-Score Games (≤8 pts)", stats["one_score_games"], stats["one_score_pct"]),
        _plain_row("Average Score", f'{stats["avg_winner_score"]}:{stats["avg_loser_score"]}', "(winner:loser)"),
        _streak_row("Longest Winning Streak", stats["longest_win_streak"], team_link, logo),
        _streak_row("Longest Losing Streak", stats["longest_lose_streak"], team_link, logo),
    ]
    outcomes_card = (
        '<div class="mdn-card" style="flex:1 1 560px;min-width:480px;margin:0">'
        '<div class="mdn-card-kicker">Overview</div>'
        '<div class="mdn-card-title" style="font-size:17px;margin-bottom:14px">Game Outcomes</div>'
        '<table class="mdn-led-table" style="width:100%">'
        '<thead><tr><th>Statistic</th><th class="mdn-num" style="width:280px">Value</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )

    margin_card = (
        '<div class="mdn-card" style="flex:1 1 380px;min-width:340px;margin:0">'
        '<div class="mdn-card-kicker">Distribution</div>'
        '<div class="mdn-card-title" style="font-size:17px;margin-bottom:14px">Score Margin Distribution</div>'
        f"{''.join(_margin_row(m) for m in stats['margin_distribution'])}</div>"
    )

    return f'<div style="display:flex;flex-wrap:wrap;gap:28px;align-items:flex-start">{outcomes_card}{margin_card}</div>'


# --- Schedule grid --------------------------------------------------------

def _grid_cell(slot: dict[str, Any] | None) -> str:
    if slot is None:
        return '<span class="mdn-bye">BYE</span>'
    at_vs = "@" if not slot["home"] else "vs"
    text = f'{at_vs} {escape(slot["opponent"])}'
    if slot["status"] == "postponed":
        return f'<div>{text}</div><div class="mdn-hint" style="font-size:10px;font-style:italic">Postponed</div>'
    if slot["status"] == "cancelled":
        return f'<div>{text}</div><div class="mdn-hint" style="font-size:10px;font-style:italic">Canceled</div>'
    if slot["team_score"] is not None and slot["opponent_score"] is not None:
        if slot["status"] == "completed":
            sub_label = f'{slot["team_score"]}-{slot["opponent_score"]}'
        else:
            sub_label = f'{slot["team_score"]}-{slot["opponent_score"]} (r)'
        return f'<div>{text}</div><div class="mdn-hint" style="font-size:10px">{sub_label}</div>'
    return text


def render_schedule_grid_content(
    grid: list[dict[str, Any]], season_weeks: int, team_link: TeamLink, logo: LogoRenderer
) -> str:
    sorted_grid = sorted(grid, key=lambda entry: entry.get("abbreviation") or entry["team"])
    header = "".join(f"<th>Wk {w}</th>" for w in range(1, season_weeks + 1))
    rows = []
    for entry in sorted_grid:
        cells = "".join(f"<td>{_grid_cell(slot)}</td>" for slot in entry["weeks"])
        team_cell = _team_ref(entry["team"], team_link, logo, logo_size=22, link_class="mdn-grid-team-link")
        rows.append(f"<tr><td>{team_cell}</td>{cells}</tr>")
    return (
        '<div class="mdn-grid-wrapper"><table class="mdn-led-table mdn-grid-table">'
        f"<thead><tr><th>Team</th>{header}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


# --- Simulation -----------------------------------------------------------
# Mirrors simulation.js's _renderPlayoffProbabilityTables/_renderSeedingMatrix/
# _renderTopScenarios: two SEPARATE per-conference tables (not merged), a
# plain-color probability bar (a simple width% div, not a chart), the
# scenarios list as a native <details> disclosure (works without JS in a
# static export), and the seeding matrix's per-cell tint (_seed_tint mirrors
# simulation.js's _seedTint exactly, including the mdn-seed-hi white-text
# class at higher probabilities) so the exported heatmap matches the live one.

def _seed_tint(pct: float) -> tuple[str, bool]:
    """Background tint + whether text should render light, mirroring
    simulation.js's _seedTint bucket-for-bucket."""
    if pct <= 0:
        return "transparent", False
    if pct < 15:
        return "oklch(91% 0.045 55)", False
    if pct < 30:
        return "oklch(82% 0.09 48)", False
    if pct < 45:
        return "oklch(71% 0.14 40)", False
    if pct < 60:
        return "oklch(60% 0.18 32)", True
    if pct < 80:
        return "oklch(48% 0.16 26)", True
    return "oklch(34% 0.10 30)", True


def _playoff_probability_bar(pct: float) -> str:
    if pct >= 99.95:
        color = "var(--mdn-accent-500)"
    elif pct <= 0.05:
        color = "var(--mdn-neutral-400)"
    else:
        color = "var(--mdn-accent-300)"
    opacity = "0.5" if pct <= 0.05 else "1"
    return (
        '<div style="display:flex;align-items:center;gap:8px">'
        '<div style="flex:1;height:6px;background:var(--mdn-neutral-200);position:relative">'
        f'<div style="position:absolute;inset:0 auto 0 0;width:{pct}%;background:{color}"></div></div>'
        f'<span style="font-size:12px;width:44px;text-align:right;flex:none;opacity:{opacity}">{pct:.1f}%</span>'
        "</div>"
    )


def _format_fetch_time(raw: str) -> str:
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return raw


def _season_data_card(
    status: dict[str, Any], cutoff_week: int | None, sim_total_line: str | None = None
) -> str:
    """The "Season data" card shared by the live Standings and Simulations
    pages (standings.js's buildSeasonDataCell) — season/cutoff title, the
    four loaded/completed stat tiles, and the last-fetch timestamp.

    `sim_total_line` (export-only, Simulations section): the live app shows
    the "N games x M iterations = X game simulations" line next to the
    Iterations/Noise/Workers controls, which the export has no equivalent
    of, so it's folded into this card as a fifth stat tile instead of being
    left as an orphaned line with nothing to sit next to."""
    season_weeks = status.get("season_weeks") or "—"
    expected_total = status.get("expected_total")
    completed = status.get("completed") or 0
    pct_completed = round((completed / expected_total) * 100) if expected_total else 0
    cutoff_title = (
        f"Week {cutoff_week} cutoff"
        if cutoff_week is not None
        else f"Auto cutoff — week {status.get('auto_cutoff_week', 0)}"
    )
    expected_display = expected_total if expected_total is not None else "—"

    parts = [
        '<div class="mdn-card" style="margin-bottom:20px">',
        '<div class="mdn-card-kicker">Season data</div>',
        f'<div class="mdn-card-title">{status.get("season_year", "")} · {escape(cutoff_title)}</div>',
        '<div style="display:flex;gap:28px;margin-top:12px;flex-wrap:wrap">',
        f'<div><div class="mdn-stat-lbl">Weeks loaded</div><div class="mdn-stat-val">{status.get("weeks_fetched", 0)} / {season_weeks}</div></div>',
        f'<div><div class="mdn-stat-lbl">Weeks completed</div><div class="mdn-stat-val">{status.get("weeks_completed", 0)} / {season_weeks}</div></div>',
        f'<div><div class="mdn-stat-lbl">Games loaded</div><div class="mdn-stat-val">{status.get("total_games", 0)} / {expected_display}</div></div>',
        f'<div><div class="mdn-stat-lbl">Games completed</div><div class="mdn-stat-val">{completed} / {expected_display} ({pct_completed}%)</div></div>',
    ]
    if sim_total_line is not None:
        parts.append(
            f'<div><div class="mdn-stat-lbl">Game simulations</div><div class="mdn-stat-val">{escape(sim_total_line)}</div></div>'
        )
    parts.append("</div>")
    if status.get("last_fetch_time"):
        parts.append(f'<p class="mdn-hint">Last fetched {escape(_format_fetch_time(status["last_fetch_time"]))}</p>')
    parts.append("</div>")
    return "".join(parts)


def _sim_total_tile_line(sim_result: dict[str, Any] | None) -> str | None:
    """The "games x iterations = total" figure for the Season Data card's
    "Game simulations" tile. None if no simulation was exported, so the
    caller can omit the tile entirely rather than showing a zeroed one."""
    if sim_result is None:
        return None
    games_to_sim = sim_result.get("simulated_games") or 0
    iterations = sim_result.get("iterations_run") or 0
    suffix = " — low confidence" if sim_result.get("low_confidence") else ""
    if games_to_sim and iterations:
        total = games_to_sim * iterations
        return f"{games_to_sim:,} × {iterations:,} = {total:,}{suffix}"
    return f"No games to simulate at this cutoff{suffix}"


def _export_header(
    title: str,
    subtitle: str,
    status: dict[str, Any] | None,
    cutoff_week: int | None,
    sim_result: dict[str, Any] | None,
) -> str:
    """Page title + the Season Data card, used at the top of every export
    page (single-page export and every page in the bundle) so season/cutoff
    context is available everywhere, not just next to the Simulation
    section. The "Game simulations" tile only appears when a simulation was
    actually run and included in this export."""
    html = _page_title(title, subtitle)
    if status is not None:
        html += _season_data_card(status, cutoff_week, sim_total_line=_sim_total_tile_line(sim_result))
    return html


def render_simulation_content(
    sim_result: dict[str, Any],
    team_link: TeamLink,
    logo: LogoRenderer,
) -> str:
    parts: list[str] = []

    by_conference: dict[str, list[dict[str, Any]]] = {"AFC": [], "NFC": []}
    for t in sim_result.get("team_results", []):
        conf = t.get("conference")
        if conf in by_conference:
            by_conference[conf].append(t)

    for conf in _CONFERENCES:
        teams = sorted(by_conference[conf], key=lambda t: (-t["playoff_probability"], t["team"]))
        rows = []
        for idx, t in enumerate(teams):
            leader_cls = ' class="mdn-leader"' if idx == 6 else ""
            rows.append(
                f"<tr{leader_cls}>"
                f'<td class="mdn-num" style="opacity:0.6">{idx + 1}</td>'
                f'<td class="mdn-tm"><div class="mdn-team-cell">{_team_ref(t["team"], team_link, logo)}</div></td>'
                f'<td class="mdn-num">{escape(t.get("record", "0-0-0"))}</td>'
                f'<td>{escape(t.get("division", ""))}</td>'
                f'<td>{_playoff_probability_bar(t["playoff_probability"])}</td>'
                f'<td class="mdn-num">{t["strength_rating"]:.3f}</td>'
                "</tr>"
            )
        parts.append(_conf_head(conf, logo, title=f"{conf} Playoff Probabilities"))
        parts.append(
            '<table class="mdn-led-table" style="margin-bottom:32px;table-layout:fixed">'
            '<thead><tr><th style="width:36px" class="mdn-num">#</th><th style="width:320px">Team</th>'
            '<th style="width:180px" class="mdn-num">Record</th><th style="width:190px">Division</th>'
            '<th style="width:220px">Playoff %</th><th style="width:270px" class="mdn-num">Strength</th></tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    seed_cols = "".join(f'<th class="mdn-num">Seed {n}</th>' for n in range(1, 8))
    for conf in _CONFERENCES:
        teams = sorted(by_conference[conf], key=lambda t: (-t["playoff_probability"], t["team"]))
        rows = []
        for t in teams:
            seed_cells = []
            for n in range(1, 8):
                prob = t.get("seed_probabilities", {}).get(str(n), 0)
                tint, hi = _seed_tint(prob)
                hi_cls = " mdn-seed-hi" if hi else ""
                seed_cells.append(
                    f'<td class="mdn-num{hi_cls}" style="background:{tint};font-weight:700">{prob:.1f}%</td>'
                )
            seed_cells = "".join(seed_cells)
            rows.append(
                f'<tr><td class="mdn-tm"><div class="mdn-team-cell">{_team_ref(t["team"], team_link, logo)}</div></td>'
                f"{seed_cells}</tr>"
            )
        parts.append(_conf_head(conf, logo, title=f"{conf} Seeding Probabilities"))
        parts.append(
            '<table class="mdn-led-table" style="margin-bottom:32px;table-layout:fixed">'
            f'<thead><tr><th style="width:250px">Team</th>{seed_cols}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    scenarios = sim_result.get("top_scenarios", [])
    if not scenarios:
        parts.append(
            '<div class="mdn-card" style="margin:8px 0 28px">'
            '<div class="mdn-card-kicker">Top scenarios</div>'
            '<div class="mdn-card-title" style="font-size:16px">Top Playoff Scenarios</div>'
            '<p style="opacity:0.6;margin:8px 0 0">No scenarios available.</p></div>'
        )
    else:
        scenario_rows = []
        for rank, s in enumerate(scenarios, start=1):
            afc = ", ".join(escape(t) for t in s.get("afc_seeds", []))
            nfc = ", ".join(escape(t) for t in s.get("nfc_seeds", []))
            scenario_rows.append(
                f'<tr><td class="mdn-num" style="opacity:0.6">{rank}</td>'
                f"<td>{afc}</td><td>{nfc}</td>"
                f'<td class="mdn-num" style="font-weight:700">{s["probability"]:.2f}%</td></tr>'
            )
        parts.append(
            '<details class="mdn-card mdn-scenario-card" style="margin:8px 0 28px">'
            '<summary><span class="mdn-scenario-triangle">&#9656;</span>'
            f'<span class="mdn-card-title" style="font-size:16px;margin:0">Top {len(scenarios)} Most Likely Playoff Scenarios</span></summary>'
            '<table class="mdn-led-table" style="margin-top:16px"><thead><tr>'
            '<th style="width:48px" class="mdn-num">#</th><th>AFC Seeds (1&ndash;7)</th>'
            '<th>NFC Seeds (1&ndash;7)</th><th class="mdn-num">Probability</th></tr></thead>'
            f"<tbody>{''.join(scenario_rows)}</tbody></table></details>"
        )

    return "".join(parts)


# --- Team page (bundle only) ---------------------------------------------

def render_team_page_content(
    team_name: str,
    team_detail: dict[str, Any],
    standings_row: dict[str, Any] | None,
    sim_row: dict[str, Any] | None,
    logo: LogoRenderer,
    status: dict[str, Any] | None = None,
    cutoff_week: int | None = None,
    sim_result: dict[str, Any] | None = None,
) -> str:
    conf = get_team_conference(team_name) or ""
    division = get_team_division(team_name)
    div_label = f"{conf} {division[1]}" if division else conf

    logo_html = logo(TEAM_LOGO_IDS.get(team_name, ""), 40, 40)
    record = team_detail["record"]
    body = [
        '<a href="index.html" class="mdn-back-link">← Back to index</a>',
        f'<div class="mdn-team-hero">{logo_html}<h1>{escape(team_name)}</h1></div>',
        f'<p class="mdn-team-record">{escape(div_label)} · '
        f"{record['wins']}-{record['losses']}-{record['ties']} "
        f"({record['win_percentage']:.3f})</p>",
    ]
    if status is not None:
        body.append(_season_data_card(status, cutoff_week, sim_total_line=_sim_total_tile_line(sim_result)))

    if standings_row is not None:
        seed = standings_row.get("seed")
        seed_text = f"Seed {seed}" if seed else ("Clinched playoff spot" if standings_row.get("is_playoff_team") else "Outside playoff picture")
        tiebreaker_html = ""
        if standings_row.get("tiebreaker"):
            tiebreaker_html = f" {_tiebreaker_tag(standings_row['tiebreaker'])}"
        body.append(
            '<div class="mdn-card" style="margin-bottom:20px">'
            '<div class="mdn-card-kicker">Standings</div>'
            f"<p style=\"margin:6px 0 0\">{escape(seed_text)}{tiebreaker_html} — Division record "
            f"{escape(standings_row['division_record'])}, Conference record "
            f"{escape(standings_row['conference_record'])}, Games behind {standings_row['games_behind']}</p>"
            "</div>"
        )

    if sim_row is not None:
        seed_cells = "".join(
            f'<td class="mdn-num">{sim_row.get("seed_probabilities", {}).get(str(n), 0)}%</td>'
            for n in range(1, 8)
        )
        body.append(
            '<div class="mdn-card" style="margin-bottom:20px">'
            '<div class="mdn-card-kicker">Simulation</div>'
            f'<div class="mdn-card-title" style="font-size:16px">Playoff probability: {sim_row["playoff_probability"]}%</div>'
            '<table class="mdn-led-table" style="margin-top:14px"><thead><tr>'
            + "".join(f'<th class="mdn-num">Seed {n}</th>' for n in range(1, 8))
            + f"</tr></thead><tbody><tr>{seed_cells}</tr></tbody></table></div>"
        )

    rows = []
    for g in team_detail["games"]:
        score = ""
        if g.get("home_score") is not None and g.get("away_score") is not None:
            score = f'{g["home_score"]}–{g["away_score"]}' if g["home"] else f'{g["away_score"]}–{g["home_score"]}'
        rows.append(
            f"<tr><td class=\"mdn-num\">{g['week']}</td>"
            f"<td>{'vs' if g['home'] else '@'} {escape(g['opponent'])}</td>"
            f"<td>{escape(g.get('result', g['status']))}</td>"
            f"<td class=\"mdn-num\">{escape(score)}</td></tr>"
        )
    body.append(
        '<div class="mdn-div-lbl">Schedule</div>'
        '<table class="mdn-led-table"><thead><tr><th class="mdn-num">Week</th>'
        "<th>Opponent</th><th>Result</th><th class=\"mdn-num\">Score</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return "".join(body)


# --- Index page (bundle only) ---------------------------------------------

def render_index_page(has_simulation: bool, season_year: int, logo: LogoRenderer) -> str:
    links = [
        ("standings.html", "Standings"),
        ("schedule-grid.html", "Schedule Grid"),
        ("statistics.html", "Statistics"),
    ]
    if has_simulation:
        links.append(("simulations.html", "Simulations"))

    nav = "".join(
        f'<a href="{href}" class="mdn-btn mdn-btn-secondary" style="text-decoration:none;margin:0 10px 10px 0">{escape(label)}</a>'
        for href, label in links
    )
    body = [
        '<p class="mdn-hint" style="margin:0 0 20px">Exported season snapshot</p>',
        f'<div style="margin-bottom:24px">{nav}</div>',
    ]
    for conf in _CONFERENCES:
        body.append(_conf_head(conf, logo, title=f"{conf} Teams"))
        body.append('<div class="mdn-div-grid">')
        for div in _DIVISIONS:
            teams = [t for t in ALL_TEAMS if get_team_division(t) == (conf, div)]
            items = "".join(
                f'<li style="margin-bottom:4px">{_team_ref(team, bundle_team_link, logo, logo_size=18)}</li>'
                for team in teams
            )
            body.append(f'<div><div class="mdn-div-lbl">{escape(div)}</div><ul style="list-style:none;padding:0;margin:8px 0 0">{items}</ul></div>')
        body.append("</div>")
    return "".join(body)


# --- Page assembly ---------------------------------------------------------

def render_combined_page(
    *,
    conferences: dict[str, Any],
    stats: dict[str, Any],
    grid: list[dict[str, Any]],
    season_weeks: int,
    sim_result: dict[str, Any] | None,
    season_year: int,
    css_content: str,
    logos: dict[str, bytes],
    status: dict[str, Any] | None = None,
    cutoff_week: int | None = None,
) -> str:
    """The single all-in-one export page. Team names are plain text (no
    links, no per-team sections) by explicit user decision -- a full
    per-team breakdown here would make the page unwieldy. Team/conference
    logos ARE still shown (via inline CSS classes, see _build_logo_css) since
    that decision was specifically about per-team detail sections, not about
    visual parity with the live pages generally."""
    no_link: TeamLink = lambda _name: None  # noqa: E731
    logo = make_inline_logo_renderer()
    body = (
        _export_header(
            f"NFL MONTE CARLO PLAYOFF SIM Export — {season_year}",
            "", status, cutoff_week, sim_result,
        )
        + _section_divider("Standings")
        + render_standings_content(conferences, no_link, logo)
        + _section_divider("Statistics")
        + render_statistics_content(stats, no_link, logo)
        + _section_divider("Schedule Grid")
        + render_schedule_grid_content(grid, season_weeks, no_link, logo)
    )
    if sim_result is not None:
        body += _section_divider("Simulation") + render_simulation_content(sim_result, no_link, logo)
    return _page_shell(
        f"NFL MONTE CARLO PLAYOFF SIM Export {season_year}",
        body, inline_css=css_content, logo_css=_build_logo_css(logos),
    )


_BUNDLE_ROOT = "export"

_BACK_TO_INDEX_LINK = '<a href="index.html" class="mdn-back-link">← Back to index</a>'


def build_bundle_zip(
    *,
    conferences: dict[str, Any],
    stats: dict[str, Any],
    grid: list[dict[str, Any]],
    season_weeks: int,
    sim_result: dict[str, Any] | None,
    team_details: dict[str, dict[str, Any]],
    season_year: int,
    css_content: str,
    logos: dict[str, bytes],
    status: dict[str, Any] | None = None,
    cutoff_week: int | None = None,
) -> bytes:
    """Build the multi-file ZIP bundle: index + 4 section pages (3 if no
    simulation data was supplied) + one page per team, all linking to a
    shared styles.css, with every team name anywhere in the bundle linked
    to that team's page. Logo files are copied into img/logos/ so pages can
    reference them the same way the live frontend does. Every file lives
    under an `export/` root inside the ZIP (all links are relative within
    that folder, so nesting doesn't break anything) rather than at the
    ZIP's top level, so extracting doesn't scatter files loose."""
    sim_by_team = {t["team"]: t for t in sim_result["team_results"]} if sim_result else {}
    standings_by_team = {
        t["team"]: t
        for conf in conferences.values()
        for div_teams in conf.values()
        for t in div_teams
    }
    logo = bundle_logo

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def write(path: str, content: str | bytes) -> None:
            zf.writestr(f"{_BUNDLE_ROOT}/{path}", content)

        write("styles.css", css_content)
        for logo_id, content in logos.items():
            write(f"img/logos/{logo_id}.png", content)
        write(
            "index.html",
            _page_shell(
                f"NFL MONTE CARLO PLAYOFF SIM Export {season_year}",
                _export_header(
                    f"NFL MONTE CARLO PLAYOFF SIM Export — {season_year}",
                    "", status, cutoff_week, sim_result,
                )
                + render_index_page(sim_result is not None, season_year, logo),
                css_href="styles.css",
            ),
        )
        write(
            "standings.html",
            _page_shell(
                "Standings",
                _BACK_TO_INDEX_LINK
                + _export_header("Standings", "", status, cutoff_week, sim_result)
                + render_standings_content(conferences, bundle_team_link, logo),
                css_href="styles.css",
            ),
        )
        write(
            "statistics.html",
            _page_shell(
                "Statistics",
                _BACK_TO_INDEX_LINK
                + _export_header(
                    "Season Statistics", f"Based on {stats['total_games']} completed games",
                    status, cutoff_week, sim_result,
                )
                + render_statistics_content(stats, bundle_team_link, logo),
                css_href="styles.css",
            ),
        )
        write(
            "schedule-grid.html",
            _page_shell(
                "Schedule Grid",
                _BACK_TO_INDEX_LINK
                + _export_header(
                    "Schedule Grid", f"All 32 teams · weeks 1–{season_weeks}", status, cutoff_week, sim_result,
                )
                + render_schedule_grid_content(grid, season_weeks, bundle_team_link, logo),
                css_href="styles.css",
            ),
        )
        if sim_result is not None:
            write(
                "simulations.html",
                _page_shell(
                    "Simulations",
                    _BACK_TO_INDEX_LINK
                    + _export_header("Simulations", "", status, cutoff_week, sim_result)
                    + render_simulation_content(sim_result, bundle_team_link, logo),
                    css_href="styles.css",
                ),
            )
        for team in ALL_TEAMS:
            detail = team_details[team]
            page = render_team_page_content(
                team,
                detail,
                standings_by_team.get(team),
                sim_by_team.get(team),
                logo,
                status=status,
                cutoff_week=cutoff_week,
                sim_result=sim_result,
            )
            write(f"team-{_slug(team)}.html", _page_shell(team, page, css_href="styles.css"))

    return buf.getvalue()


def validate_simulation_payload(data: Any) -> dict[str, Any] | None:
    """Defensively validate a client-posted simulation_result payload.

    The frontend forwards window._simulationResults verbatim, which could be
    stale or hand-edited; rather than 500ing the whole export over a bad
    payload, an invalid shape simply drops the simulation section (returns
    None) like no simulation having been run at all.
    """
    if not isinstance(data, dict):
        return None
    team_results = data.get("team_results")
    top_scenarios = data.get("top_scenarios")
    if not isinstance(team_results, list) or not isinstance(top_scenarios, list):
        return None
    for t in team_results:
        if not isinstance(t, dict) or t.get("team") not in ALL_TEAMS:
            return None
        if not isinstance(t.get("seed_probabilities"), dict):
            return None
    return data
