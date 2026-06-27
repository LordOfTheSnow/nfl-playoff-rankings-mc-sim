/**
 * Property-based test: Navigation active state synchronization
 *
 * **Validates: Requirements 2.4**
 *
 * Property 1: For any valid hash route that matches a navigation link's href,
 * the corresponding nav-link element SHALL have the `active` class and
 * `aria-current="page"` attribute, and all other nav-link elements SHALL NOT
 * have the `active` class or `aria-current` attribute.
 */

import { describe, it, expect, beforeAll } from "vitest";
import fc from "fast-check";

describe("Property 1: Navigation active state synchronization", () => {
  /** @type {NodeListOf<HTMLAnchorElement>} */
  let navLinks;

  /** Valid views that correspond to nav link hrefs */
  const navLinkViews = ["standings", "statistics", "results"];

  beforeAll(() => {
    // Trigger DOMContentLoaded to ensure App.init() resolves DOM references
    document.dispatchEvent(new Event("DOMContentLoaded"));
    navLinks = document.querySelectorAll(".navbar-nav .nav-link");
  });

  it("active class and aria-current are set on the correct nav-link only (100+ iterations)", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...navLinkViews),
        (activeView) => {
          // Act: set hash and trigger routing
          window.location.hash = `#${activeView}`;
          App.route();

          // Re-query nav links to get current state
          const links = document.querySelectorAll(".navbar-nav .nav-link");

          for (const link of links) {
            const href = link.getAttribute("href") || "";
            const linkView = href.replace(/^#/, "");

            if (linkView === activeView) {
              // The matching link SHALL have active class and aria-current="page"
              expect(link.classList.contains("active")).toBe(true);
              expect(link.getAttribute("aria-current")).toBe("page");
            } else {
              // All other links SHALL NOT have active class or aria-current
              expect(link.classList.contains("active")).toBe(false);
              expect(link.hasAttribute("aria-current")).toBe(false);
            }
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("exactly one nav-link is active after routing to any valid view (100+ iterations)", () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...navLinkViews),
        (activeView) => {
          // Act
          window.location.hash = `#${activeView}`;
          App.route();

          // Assert: exactly one link has active class
          const links = document.querySelectorAll(".navbar-nav .nav-link");
          const activeLinks = Array.from(links).filter((l) =>
            l.classList.contains("active")
          );
          expect(activeLinks).toHaveLength(1);

          // Assert: exactly one link has aria-current
          const ariaCurrentLinks = Array.from(links).filter((l) =>
            l.hasAttribute("aria-current")
          );
          expect(ariaCurrentLinks).toHaveLength(1);

          // Both should be the same element
          expect(activeLinks[0]).toBe(ariaCurrentLinks[0]);
        }
      ),
      { numRuns: 100 }
    );
  });

  it("routes not matching any nav link result in no active nav-link (100+ iterations)", () => {
    // Views that exist in the router but have no nav-link (e.g., "simulate", "team/xxx")
    const nonNavRoutes = ["simulate", "team/Buffalo Bills", "team/Kansas City Chiefs"];

    fc.assert(
      fc.property(
        fc.constantFrom(...nonNavRoutes),
        (route) => {
          // Act
          window.location.hash = `#${route}`;
          App.route();

          // Assert: no nav-link should have active class
          const links = document.querySelectorAll(".navbar-nav .nav-link");
          for (const link of links) {
            expect(link.classList.contains("active")).toBe(false);
            expect(link.hasAttribute("aria-current")).toBe(false);
          }
        }
      ),
      { numRuns: 100 }
    );
  });
});
