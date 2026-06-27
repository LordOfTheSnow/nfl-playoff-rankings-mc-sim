# Implementation Plan: Bootstrap Frontend Migration

## Overview

Migrate the NFL Monte Carlo Playoff Ranking Simulator frontend from a custom ~500-line CSS design system to Bootstrap 5.3.3 loaded via CDN. The migration updates `index.html` structure, reduces `styles.css` to ≤200 lines of NFL-specific overrides, and updates all JS files to emit Bootstrap class names. The implementation proceeds layer-by-layer: CDN integration → HTML structure → CSS reduction → JS module updates → testing.

## Tasks

- [x] 1. Bootstrap CDN integration and HTML structure
  - [x] 1.1 Add Bootstrap CDN links and restructure index.html
    - Add Bootstrap 5.3.3 CSS `<link>` in `<head>` before `css/styles.css`
    - Add Bootstrap 5.3.3 JS bundle `<script>` after all page content, before `</body>`
    - Replace the custom `<header class="site-header">` with a Bootstrap navbar: `navbar navbar-expand-lg navbar-dark sticky-top` with inline `background-color:#1b3a6b`
    - Add `navbar-brand` with NFL logo (32×32) and title text
    - Add `navbar-toggler` button for responsive collapse below `lg` breakpoint
    - Wrap nav links in `collapse navbar-collapse` → `navbar-nav ms-auto` → `nav-item` → `nav-link`
    - Keep disclaimer bar below navbar with `header-disclaimer` class
    - Change `<main id="content">` to include `class="container-xl py-4"`
    - Update `#notification` element to use `container-xl mt-2 d-none`
    - Update `#loading` element to use `d-none`
    - Verify no other CSS framework links are present
    - _Requirements: 1.1, 1.2, 1.4, 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 3.1, 3.4_

  - [x] 1.2 Update app.js notification and loading system to Bootstrap components
    - Modify `showError()` to render a Bootstrap `alert alert-danger alert-dismissible fade show` with `btn-close`
    - Modify `showInfo()` to render a Bootstrap `alert alert-info alert-dismissible fade show` with `btn-close`
    - Replace `.visible`/`.hidden` class toggles with `d-none` addition/removal
    - Update `hideNotification()` to add `d-none` and remove alert from DOM
    - Update `showLoading()` to show a Bootstrap `spinner-border text-primary` with `visually-hidden` label inside a fixed overlay
    - Update `hideLoading()` to add `d-none` to spinner and overlay
    - Update `updateNavActive()` to set `aria-current="page"` on active link and remove from others
    - _Requirements: 2.4, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 2. Standings and schedule JS migration
  - [x] 2.1 Update standings.js to use Bootstrap classes
    - Change `buildFilterBar()`: set `bar.className = "card card-body mb-3 d-flex flex-row align-items-center gap-3"`
    - Change filter buttons to include `btn btn-sm btn-outline-primary` / `btn btn-sm btn-primary` for active state
    - Change `buildDivisionSection()`: set `section.className = "card mb-3"`, header to `"card-header text-uppercase text-muted fw-semibold small"`
    - Change standings table: `table.className = "table table-striped table-hover standings-table mb-0"`
    - Change `buildStatusPanel()`: set `panel.className = "card card-body mb-3"`
    - Update all `controls-panel` references to `"card card-body mb-3"`
    - Keep division-leader row styling via custom CSS class
    - Update button classes in status panel to `btn btn-primary` / `btn btn-secondary`
    - Update form inputs to use `form-control` and `form-select` classes
    - Update range inputs to use `form-range` class
    - Update spinner reference to `spinner-border text-primary`
    - _Requirements: 3.2, 4.1, 4.2, 4.5, 4.8, 5.1, 5.2, 5.3, 5.4, 6.1, 6.3, 6.4_

  - [x] 2.2 Update schedule.js to use Bootstrap table classes
    - Change schedule table: `table.className = "table table-hover schedule-table"`
    - Keep game-result color classes (`game-result--win`, `game-result--loss`, `game-result--tie`) for custom styling
    - Update back-link styling if needed for Bootstrap compatibility
    - _Requirements: 4.4_

  - [x] 2.3 Update simulation.js to use Bootstrap form and card classes
    - Change controls panel wrapper to `"card card-body mb-3"`
    - Change number inputs to include `class="form-control"`
    - Change range inputs to include `class="form-range"`
    - Change select elements to include `class="form-select"`
    - Ensure `btn btn-primary` / `btn btn-secondary` on buttons
    - Change progress indicator spinner to `spinner-border text-primary` with `visually-hidden` label
    - Change overlay to use Bootstrap positioning: `position-fixed top-0 start-0 w-100 h-100`
    - Update form layout to use Bootstrap row/col grid for side-by-side fields
    - Ensure labels have `for` attributes matching input `id` values
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 7.1, 7.2, 7.3_

  - [x] 2.4 Update statistics.js and charts.js to use Bootstrap card classes
    - Change statistics panel wrapper from `controls-panel` to `"card card-body mb-3"`
    - Add Bootstrap `table table-striped table-hover` to probability table in statistics
    - In charts.js rendering context (called externally), ensure chart containers use `card card-body mb-3`
    - _Requirements: 4.3, 6.2_

- [x] 3. CSS stylesheet reduction
  - [x] 3.1 Rewrite styles.css to NFL-only overrides (≤200 lines)
    - Remove universal reset rules (`*` selector with box-sizing/margin/padding)
    - Remove base typography rules (html font-size, body font-family that Bootstrap Reboot provides)
    - Remove custom `.btn`, form input, select, and table base styles that Bootstrap provides
    - Remove custom grid/layout (`.main-content` max-width and padding rules that duplicate container)
    - Remove custom `.nav-link` base styles (Bootstrap navbar handles this)
    - Retain `:root` CSS custom properties for NFL brand colors, fonts, radii, shadows
    - Retain `.header-disclaimer` styling
    - Retain `.conference-header--afc` and `.conference-header--nfc` border colors
    - Retain `.division-leader` row background + left border
    - Retain `.team-link` hover/focus styles
    - Retain `.standings-table` fixed column widths (nth-child rules)
    - Retain `.numeric` / `td.numeric` right-aligned, tabular-nums styling
    - Retain `.game-result--win`, `.game-result--loss`, `.game-result--tie` colors
    - Retain spinner overlay (`position-fixed` backdrop with custom opacity)
    - Retain team logo contextual sizing if not handled inline
    - Retain `container-xl` max-width override (1400px–1600px range)
    - Ensure total non-comment lines ≤ 200
    - _Requirements: 1.3, 3.3, 3.5, 8.1, 8.2, 8.3, 8.5, 8.6, 9.1, 9.2, 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 4. Checkpoint - Verify visual consistency
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Property-based and unit tests
  - [x] 5.1 Set up testing framework (fast-check + JSDOM or Playwright)
    - Install fast-check and test runner (vitest or jest with jsdom)
    - Create test directory structure for frontend property tests
    - Configure test environment to load Bootstrap and app JS files
    - _Requirements: Design testing strategy_

  - [x] 5.2 Write property test for navigation active state synchronization
    - **Property 1: Navigation active state synchronization**
    - Generate random valid hash routes; verify active class and aria-current on correct nav-link only
    - **Validates: Requirements 2.4**

  - [x] 5.3 Write property test for table Bootstrap class assignment
    - **Property 2: Table Bootstrap class assignment**
    - Generate random standings/results/schedule data; verify table elements contain correct Bootstrap classes
    - **Validates: Requirements 4.1, 4.3, 4.4**

  - [x] 5.4 Write property test for division leader visual distinction
    - **Property 3: Division leader visual distinction**
    - Generate random division teams; verify first row has leader styling and others do not
    - **Validates: Requirements 4.2**

  - [x] 5.5 Write property test for form element Bootstrap classes
    - **Property 4: Form element Bootstrap class assignment**
    - Render simulation controls; verify all inputs, selects, ranges, and buttons have correct Bootstrap classes
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x] 5.6 Write property test for label-input association
    - **Property 5: Label-input association**
    - Render simulation controls; verify all labels with `for` attribute match an input `id`
    - **Validates: Requirements 5.6**

  - [x] 5.7 Write property test for error alert display and auto-dismiss
    - **Property 8: Error alert display and auto-dismiss**
    - Generate random error messages; verify Bootstrap alert-danger rendering and 8-second auto-dismiss
    - **Validates: Requirements 7.4, 7.6**

  - [x] 5.8 Write property test for conference header border colors
    - **Property 9: Conference header border colors**
    - Generate AFC/NFC data; verify left border colors #d32f2f and #1565c0 respectively
    - **Validates: Requirements 8.3**

  - [x] 5.9 Write property test for team logo sizing
    - **Property 10: Team logo sizing by context**
    - Generate logos in different DOM contexts; verify width/height attributes: 20×20 (table), 28×28 (conference header), 32×32 (navbar)
    - **Validates: Requirements 8.4**

  - [x] 5.10 Write property test for game result color indicators
    - **Property 11: Game result color indicators**
    - Generate random win/loss/tie results; verify text colors #16a34a, #e63946, #d97706
    - **Validates: Requirements 8.5**

- [x] 6. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is vanilla JavaScript (HTML/CSS/JS) matching the existing codebase
- Bootstrap 5.3.3 is loaded via CDN — no build tools or npm dependencies required for the frontend itself
- The testing framework (fast-check) would require a Node.js dev dependency if property tests are implemented

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "3.1"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9", "5.10"] }
  ]
}
```
