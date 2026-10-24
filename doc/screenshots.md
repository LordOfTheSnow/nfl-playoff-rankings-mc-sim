# Screenshots

[← Back to README](../README.md)

Every page in the app, all in the flat, red-on-white "Modernist" design system. See the [README](../README.md#screenshots) for a quick look at the Seeding Probabilities matrix; the full set is below.

## Standings

### Standings page (2025 season, cutoff week 17)

![Standings page in the Modernist Ledger redesign, 2025 season, week 17 cutoff](img/screenshot-standings-new-design.png)

*Standings page in the flat, red-on-white "Modernist Ledger" design. Each team row shows a status tag — DIVISION, #1 SEED, CLINCHED, or ELIMINATED — and, when a standings tie was resolved by a tiebreaker rule, a chip (e.g. "H2H 2-0") that explains why on hover.*

### Team Detail page (2025 season)

![Team Detail page in the Modernist Ledger redesign, showing the New England Patriots' full 2025 season schedule](img/screenshot-team-new-design.png)

*Team Detail page in the same flat "Modernist Ledger" style as Standings, reusing the same ledger table component. Each completed game shows a bordered Win/Loss/Tie tag, and the bye week renders as a single italic row.*

### Schedule Grid (2025 season)

![Schedule Grid page in the Modernist Ledger redesign, showing all 32 teams x 18 weeks](img/screenshot-schedule-grid-new-design.png)

*League-wide Schedule Grid: all 32 teams as rows, weeks 1-18 as columns, with opponent abbreviation, home/away, bye weeks, and scores for completed games — a compact overview of the entire season on one page.*

## Simulations

### Playoff Probabilities and Seeding Probabilities (2026 season, cutoff week 6)

![Simulations page with the Playoff Probabilities tables and Seeding Probabilities matrix for AFC and NFC](img/screenshot-simulation-results.png)

*Playoff Probabilities tables for both conferences. Each row shows an inline probability bar, and the 7th seed — the current projected playoff cutoff — is highlighted with the same leader-row treatment used for division leaders in Standings.*

*Seeding Probabilities matrix: each cell is tinted on a warm tan-to-maroon scale proportional to that team's probability of landing exactly that seed, switching to white text once the tint gets dark enough — never gray, and never tinted at exactly 0%. The collapsed Top Scenarios accordion sits below.*

### Top Playoff Scenarios (2025 season, cutoff week 16)

![Top Playoff Scenarios table expanded in the Modernist Ledger redesign](img/screenshot-top-10-mlploff-scens-new-design.png)

*The Top Scenarios accordion expanded, ranking the most likely distinct AFC/NFC seeding combinations by probability.*

### Clinching Scenarios (Detroit Lions, 2025 season)

![Clinching Scenarios for the Detroit Lions in the Modernist Ledger redesign](img/screenshot-playoff-probabilities-team-new-design.png)

*Inline candidate-details panel (opened by clicking a team on the Simulations page) showing every game-outcome combination that guarantees or eliminates a playoff spot, grouped by remaining record. Conditions for every scenario in a group share one aligned table, with a rowspan'd `#` column tying each scenario's rows together instead of giving every scenario its own separately-sized table.*

### Solver Timing History

![Solver Timing History dialog in the Modernist style, showing the ms/eval trend sparkline and a ledger table of past solver runs](img/screenshot-solver-timing-history-new-design.png)

*Solver Timing History dialog (opened via the "Timing History" button on the Clinching Scenarios panel): a measurement-count/average stat row with an ms/eval trend sparkline, and a scrollable ledger table where the `sampling` and `enumeration` methods are distinguished by a red-outline vs. dark-outline tag.*

## Statistics

### Season Statistics (2025 season)

![Season Statistics page in the Modernist style, showing Game Outcomes and Score Margin Distribution cards](img/screenshot-statistics-new-design.png)

*Game Outcomes card (home/away/tie/overtime/one-score win rates as inline percentage bars, average score, longest winning/losing streaks with team logos) alongside a Score Margin Distribution card bucketing every completed game's final margin.*

## Wild Card

### Wild Card Round — Simulated seeding (2026 season, cutoff week 6)

![Wild Card Round page in the Modernist style, showing Simulated seeding for AFC and NFC with bye rows, 2v7/3v6/4v5 matchups, and In the Hunt panels](img/screenshot-wildcard-simulated.png)

*Wild Card Round, Simulated mode: each conference's #1 seed on a first-round bye, the three Wild Card matchups with the higher-strength team highlighted as favorite, and an "In the Hunt" panel listing every team outside the top 7 with its playoff probability. Switching the Data source segment to Actual standings shows the same layout sourced from real results through the cutoff week instead.*

## Export

### Teaser image — "Biggest movers" (2026 season, cutoff week 3)

![Biggest movers teaser card: five team tiles with logos, each showing the playoff-probability change since the saved baseline, plus the app name and version in the footer](img/screenshot-movercard.png)

*Teaser image downloaded from the Export page (1200×630 PNG, for link previews and social posts): the five teams whose playoff probability changed most since the baseline saved on an earlier week. Each tile shows the team's logo, its change (▲/▼), and before → after probabilities. The footer carries the app name and version.*

### Wild Card teaser — NFC (2026 season, cutoff week 6)

![NFC Wild Card teaser card: 9:16 Story PNG showing the #1 seed's bye, the three 2v7/3v6/4v5 matchups with the favorite highlighted, and a stylised bell-curve panel captioned with the run's total game simulations](img/screenshot-wildcard-nfc.png)

*Wild Card teaser image downloaded from the Export page (1080×1920 PNG, for Stories; AFC has its own matching download): the conference's #1 seed on a bye, the three Wild Card matchups with the higher-strength team highlighted as favorite, and the same stylised simulation bell-curve panel used on the "Biggest movers" teaser, captioned with the run's total game simulations.*

### Matchups teaser — Week 7 (2026 season, cutoff week 7)

![Matchups teaser card for week 7 of the 2026 season, with one final score and simulated win probabilities for the remaining games](img/screenshot-teaser-card-next-week-matchups.png)

*Matchups teaser image downloaded from the Export page (1080×1920 PNG, for Stories): every game of the upcoming week, grouped by Eastern Time broadcast day, each with its simulated home/away/tie win probability as a stacked bar. When the cutoff week is only partly played, the card stays on that week and shows the games already played with their final score (here Thursday's Bears–Patriots, 30–24).*

## Settings / Info

![Settings / Info page in the Modernist style, showing runtime environment, lifetime totals, SQLite cache database metadata, and recent fetch attempts](img/screenshot-settings-info-new-design.png)

*Settings / Info page: server runtime environment (CPU model/cores, Python version, platform, and the distinct worker start methods used by simulation vs. the clinching resolver), lifetime totals for games simulated and clinching resolver evaluations (with a Reset button), per-season SQLite cache completeness, and the 20 most recent ESPN fetch attempts with failures flagged.*
