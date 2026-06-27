# Requirements Document

## Introduction

This feature replaces the custom CSS design system in the NFL Monte Carlo Playoff Ranking Simulator frontend with the Bootstrap CSS framework. The migration preserves the existing functionality and NFL-branded visual identity (colors, team logos, dark primary header) while leveraging Bootstrap's grid system, utility classes, and pre-built components for improved maintainability, responsiveness, and faster future UI development.

## Glossary

- **Frontend**: The HTML/CSS/JavaScript application served from the `frontend/` directory that provides the user interface for the simulator
- **Bootstrap**: The Bootstrap 5 CSS framework loaded from a CDN or local bundle, providing grid, components, and utility classes
- **Custom_Stylesheet**: A project-specific CSS file (`styles.css`) containing overrides and NFL-branded styles that supplement Bootstrap defaults
- **Standings_Table**: The HTML table displaying NFL team standings grouped by conference and division
- **Simulation_Controls**: The form panel allowing users to configure and run Monte Carlo simulations
- **Navigation_Bar**: The sticky header containing the site title, NFL logo, and page navigation links
- **Results_View**: The section displaying simulation probability tables and scenario lists
- **Schedule_View**: The per-team game schedule table with win/loss/tie indicators
- **Statistics_View**: The section containing charts and statistical summaries of simulation data
- **Progress_Indicator**: The modal overlay with spinner shown during long-running simulation operations

## Requirements

### Requirement 1: Bootstrap Integration

**User Story:** As a developer, I want Bootstrap loaded in the frontend, so that I can use its grid system, components, and utilities without maintaining a custom design system.

#### Acceptance Criteria

1. THE Frontend SHALL load Bootstrap 5.3.x CSS via a CDN `<link>` element in the HTML `<head>`, positioned before the Custom_Stylesheet `<link>` element so that custom rules take cascade precedence over Bootstrap defaults
2. THE Frontend SHALL load the Bootstrap 5.3.x JavaScript bundle via a `<script>` tag placed after all page content (before the closing `</body>` tag) so that interactive Bootstrap components (dropdowns, modals, tooltips, collapses) function without additional dependencies
3. THE Custom_Stylesheet SHALL contain only CSS rules that override Bootstrap defaults with NFL-branded design tokens (colors, fonts, spacing defined as CSS custom properties) and layout rules specific to the simulator views, and SHALL NOT redefine base reset, typography, or grid behavior already provided by Bootstrap
4. THE Frontend SHALL not load any other CSS framework (e.g., Tailwind, Foundation, Bulma) alongside Bootstrap, verified by the absence of additional framework `<link>` or `<style>` imports in the HTML document

### Requirement 2: Navigation Bar Migration

**User Story:** As a user, I want the navigation header to use Bootstrap's navbar component, so that it remains consistent with Bootstrap conventions and stays responsive.

#### Acceptance Criteria

1. THE Navigation_Bar SHALL use Bootstrap's `navbar`, `navbar-expand-lg`, and `navbar-dark` component classes with an inline background color of #1b3a6b
2. THE Navigation_Bar SHALL remain fixed at the top of the viewport using Bootstrap's `sticky-top` utility class
3. THE Navigation_Bar SHALL display the NFL logo image (32×32 pixels) and the text "NFL Monte Carlo Playoff Ranking Simulator" wrapped in a Bootstrap `navbar-brand` element
4. WHEN a navigation link's href matches the current hash route, THE Navigation_Bar SHALL apply Bootstrap's `active` class and `aria-current="page"` attribute to that link's `nav-link` element
5. THE Navigation_Bar SHALL contain the disclaimer text in a separate full-width bar below the navbar links, visually distinguished by a darker background color (rgba(0, 0, 0, 0.15) overlay or equivalent)
6. WHEN the viewport width is below the `lg` breakpoint (992px), THE Navigation_Bar SHALL collapse navigation links behind a Bootstrap `navbar-toggler` button that toggles visibility of the link list
7. THE Navigation_Bar SHALL include navigation links labeled "Standings", "Statistics", and "Results" rendered as Bootstrap `nav-link` elements within a `navbar-nav` list

### Requirement 3: Layout and Grid System

**User Story:** As a developer, I want the page layout to use Bootstrap's container and grid system, so that I can remove custom max-width and padding rules.

#### Acceptance Criteria

1. THE Frontend SHALL wrap the main content area in a Bootstrap `container` or `container-xl` element with a custom maximum width set between 1400px and 1600px via the Custom_Stylesheet
2. THE Frontend SHALL use Bootstrap's row and column classes for layouts containing side-by-side form fields or content panels within the Simulation_Controls and filter bars
3. WHILE the viewport width is at least 1200px, THE Frontend SHALL constrain the content area to a maximum width of no more than 1600px using the Bootstrap container element and a Custom_Stylesheet override
4. THE Frontend SHALL apply Bootstrap spacing utilities (`px-3`, `px-4`, or container default padding) for horizontal padding on the main content area, resulting in between 12px and 32px of horizontal padding on each side
5. THE Custom_Stylesheet SHALL NOT define custom `max-width` or horizontal `padding` rules on the main content wrapper that duplicate the Bootstrap container behavior

### Requirement 4: Table Styling

**User Story:** As a user, I want the standings and results tables to use Bootstrap's table component, so that they have consistent styling with striped rows and hover effects.

#### Acceptance Criteria

1. THE Standings_Table SHALL use Bootstrap's `table`, `table-striped`, and `table-hover` classes for base styling
2. THE Standings_Table SHALL visually distinguish the division leader row using the Custom_Stylesheet-defined background color and a 4px left border accent on the team name cell
3. THE Results_View probability tables SHALL use Bootstrap's `table`, `table-striped`, and `table-hover` classes
4. THE Schedule_View table SHALL use Bootstrap's `table` and `table-hover` classes
5. WHILE the viewport width is at least 1024px, THE Standings_Table SHALL display all 10 columns (Team, W, L, T, Win%, Div, Conf, GB, Str, TB) without horizontal scrolling
6. THE Custom_Stylesheet SHALL define team-specific and NFL-branded color overrides for table rows that Bootstrap does not provide
7. THE Custom_Stylesheet SHALL define a right-aligned, tabular-numeral style for numeric table cells in the Standings_Table and Results_View probability tables
8. THE Standings_Table SHALL use fixed column widths so that columns align consistently across all division tables within the same conference section

### Requirement 5: Button and Form Controls

**User Story:** As a user, I want buttons and form inputs to use Bootstrap's component styles, so that they have consistent sizing, focus states, and accessibility defaults.

#### Acceptance Criteria

1. THE Simulation_Controls panel buttons SHALL use Bootstrap's `btn` and `btn-primary` or `btn-secondary` classes
2. THE Simulation_Controls form inputs SHALL use Bootstrap's `form-control` class for text and number inputs and Bootstrap's `form-range` class for range slider inputs
3. THE Simulation_Controls select elements SHALL use Bootstrap's `form-select` class
4. THE Simulation_Controls form layout SHALL use Bootstrap's grid or flex utilities to arrange control fields in a single row on viewports at least 1024px wide and stack them vertically below that width
5. WHEN a button or form input is disabled, THE Frontend SHALL apply the HTML `disabled` attribute so that Bootstrap's disabled state styling and pointer-event suppression take effect
6. THE Simulation_Controls form labels SHALL be associated with their corresponding input elements using the `for` attribute matching the input's `id`, providing accessible name mapping for assistive technologies

### Requirement 6: Cards and Panels

**User Story:** As a user, I want content sections like simulation controls and chart containers to use Bootstrap's card component, so that they have consistent borders, padding, and shadows.

#### Acceptance Criteria

1. THE Simulation_Controls panel SHALL use Bootstrap's `card` component with `card-body` for internal padding
2. THE Statistics_View chart containers SHALL use Bootstrap's `card` component to frame each chart
3. THE division sections in standings SHALL use Bootstrap's `card` component for grouped presentation
4. THE conference headers SHALL use Bootstrap utility classes for font size, weight, and left border accent styling

### Requirement 7: Progress and Error Feedback

**User Story:** As a user, I want loading indicators and error messages to use Bootstrap's spinner and alert components, so that feedback is visually consistent.

#### Acceptance Criteria

1. THE Progress_Indicator SHALL use Bootstrap's `spinner-border` component for the loading animation and include a visually hidden text label for screen readers
2. THE Progress_Indicator SHALL be centered on a backdrop overlay with an opacity between 0.4 and 0.6, using Bootstrap positioning utilities to cover the full viewport
3. WHEN a long-running operation begins, THE Frontend SHALL display the Progress_Indicator, and WHEN the operation completes or fails, THE Frontend SHALL hide the Progress_Indicator
4. WHEN an error occurs during an API call or view rendering, THE Frontend SHALL display the error message in a Bootstrap `alert alert-danger` component positioned below the Navigation_Bar
5. THE error alert SHALL support Bootstrap's dismiss functionality via the `alert-dismissible` and `fade show` classes and include a close button using Bootstrap's `btn-close` component
6. IF the user does not manually dismiss the error alert, THEN THE Frontend SHALL automatically hide the alert after 8 seconds

### Requirement 8: NFL Brand Preservation

**User Story:** As a product owner, I want the NFL branding (colors, logos, conference styling) to be preserved after the Bootstrap migration, so that the application retains its visual identity.

#### Acceptance Criteria

1. THE Custom_Stylesheet SHALL define CSS custom properties for NFL brand colors including primary (#1b3a6b), accent (#e63946), AFC red (#d32f2f), and NFC blue (#1565c0)
2. THE Navigation_Bar background color SHALL remain the NFL primary brand color (#1b3a6b)
3. THE conference headers SHALL retain a 4px left border colored #d32f2f for AFC and #1565c0 for NFC
4. THE team logos SHALL display at 20×20 pixels in standings rows, 28×28 pixels in conference headers, and 32×32 pixels in the site header
5. THE game result indicators SHALL display wins in #16a34a, losses in #e63946, and ties in #d97706
6. THE Custom_Stylesheet SHALL load after the Bootstrap stylesheet so that NFL brand custom properties and component styles take precedence over Bootstrap defaults

### Requirement 9: Responsive Behavior

**User Story:** As a user, I want the application to remain usable on screens from 1024px to 1920px wide, so that it works on common desktop and laptop displays.

#### Acceptance Criteria

1. WHILE the viewport width is between 1024px and 1200px, THE Navigation_Bar SHALL reduce link padding to no more than 0.75rem horizontal and reduce the site title font size to no more than 1.1rem, using Bootstrap responsive spacing utilities
2. WHILE the viewport width is at least 1600px, THE Frontend SHALL use an expanded container width up to 1600px
3. THE Frontend SHALL set a minimum viewport width of 1024px so that no horizontal scrollbar appears and no content is clipped at viewports of 1024px or wider
4. THE Frontend SHALL use Bootstrap's responsive utility classes instead of custom media queries for spacing, visibility, and display changes that have a direct Bootstrap utility equivalent
5. WHILE the viewport width is between 1024px and 1920px, THE Frontend SHALL display all interactive elements and text content without overlapping, truncation, or requiring horizontal scrolling

### Requirement 10: Removal of Redundant Custom CSS

**User Story:** As a developer, I want custom CSS rules that duplicate Bootstrap functionality to be removed, so that the stylesheet is minimal and maintainable.

#### Acceptance Criteria

1. THE Custom_Stylesheet SHALL not define universal reset rules (wildcard selector `*` with margin, padding, or box-sizing declarations) that Bootstrap's Reboot already provides
2. THE Custom_Stylesheet SHALL not define unqualified element-level styles for `button`, `input`, `select`, or `table` elements, nor re-declare base `.btn`, `.form-control`, `.form-select`, or `.table` class styles that Bootstrap provides
3. THE Custom_Stylesheet SHALL retain only the following categories of rules: CSS custom property definitions for NFL brand colors, conference-specific border colors, division leader row highlighting, game result color indicators (win, loss, tie), team logo sizing, custom component states not provided by Bootstrap (progress overlay animation, error notification slide animation, team-link focus styles), and layout overrides for NFL-specific fixed column widths
4. THE Custom_Stylesheet SHALL contain no more than 200 non-comment lines after migration, where a non-comment line is any line that is not blank and not exclusively a CSS comment
5. IF a CSS rule in the Custom_Stylesheet targets a selector or property combination that produces identical computed styles to a Bootstrap class applied in the HTML, THEN THE Custom_Stylesheet SHALL not include that rule
