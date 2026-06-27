/**
 * Property-based test: Error alert display and auto-dismiss
 *
 * **Validates: Requirements 7.4, 7.6**
 *
 * Property 8: For any error message displayed by the application, it SHALL be
 * rendered in a Bootstrap `alert alert-danger` component, and if not manually
 * dismissed, it SHALL be automatically hidden after 8 seconds (±500ms tolerance).
 */

import { describe, it, expect, beforeAll, beforeEach, afterEach } from "vitest";
import fc from "fast-check";

/**
 * Generator for error messages that won't be mangled by innerHTML parsing.
 * The app uses innerHTML to render messages, so HTML-special characters like
 * < and > would be interpreted as tags. We use printable ASCII without angle brackets.
 */
const errorMessageArb = fc
  .stringOf(
    fc.char().filter((c) => {
      const code = c.charCodeAt(0);
      // Printable ASCII excluding < > & which get interpreted as HTML
      return code >= 32 && code <= 126 && c !== "<" && c !== ">" && c !== "&";
    }),
    { minLength: 1, maxLength: 200 }
  )
  .filter((s) => s.trim().length > 0);

describe("Property 8: Error alert display and auto-dismiss", () => {
  beforeAll(() => {
    // Trigger DOMContentLoaded to ensure App.init() resolves DOM references
    document.dispatchEvent(new Event("DOMContentLoaded"));
  });

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    // Clean up notification state
    App.hideNotification();
  });

  it("error message renders in a Bootstrap alert-danger component with correct structure (100+ iterations)", () => {
    fc.assert(
      fc.property(
        errorMessageArb,
        (message) => {
          // Act: show error
          App.showError(message);

          // Assert: notification container is visible (no d-none)
          const notificationEl = document.getElementById("notification");
          expect(notificationEl.classList.contains("d-none")).toBe(false);

          // Assert: contains an alert-danger div with correct Bootstrap classes
          const alertDiv = notificationEl.querySelector(".alert");
          expect(alertDiv).not.toBeNull();
          expect(alertDiv.classList.contains("alert-danger")).toBe(true);
          expect(alertDiv.classList.contains("alert-dismissible")).toBe(true);
          expect(alertDiv.classList.contains("fade")).toBe(true);
          expect(alertDiv.classList.contains("show")).toBe(true);

          // Assert: message text is present in the alert
          expect(alertDiv.textContent).toContain(message);

          // Assert: btn-close button exists inside the alert
          const closeBtn = alertDiv.querySelector(".btn-close");
          expect(closeBtn).not.toBeNull();
          expect(closeBtn.getAttribute("data-bs-dismiss")).toBe("alert");
          expect(closeBtn.getAttribute("aria-label")).toBe("Close");

          // Clean up for next iteration
          App.hideNotification();
        }
      ),
      { numRuns: 100 }
    );
  });

  it("error alert is still visible at 7999ms and hidden at 8000ms (100+ iterations)", () => {
    fc.assert(
      fc.property(
        errorMessageArb,
        (message) => {
          // Act: show error
          App.showError(message);

          const notificationEl = document.getElementById("notification");

          // Assert: visible immediately
          expect(notificationEl.classList.contains("d-none")).toBe(false);

          // Advance to just before auto-dismiss (7999ms)
          vi.advanceTimersByTime(7999);
          expect(notificationEl.classList.contains("d-none")).toBe(false);
          expect(notificationEl.innerHTML).not.toBe("");

          // Advance to 8000ms — auto-dismiss should trigger
          vi.advanceTimersByTime(1);
          expect(notificationEl.classList.contains("d-none")).toBe(true);
          expect(notificationEl.innerHTML).toBe("");
        }
      ),
      { numRuns: 100 }
    );
  });

  it("auto-dismiss timeout resets when a new error is shown (100+ iterations)", () => {
    fc.assert(
      fc.property(
        errorMessageArb,
        errorMessageArb,
        (message1, message2) => {
          const notificationEl = document.getElementById("notification");

          // Show first error
          App.showError(message1);
          expect(notificationEl.classList.contains("d-none")).toBe(false);

          // Advance 5 seconds (less than 8s timeout)
          vi.advanceTimersByTime(5000);
          expect(notificationEl.classList.contains("d-none")).toBe(false);

          // Show second error — should reset the timeout
          App.showError(message2);
          expect(notificationEl.classList.contains("d-none")).toBe(false);

          // Advance another 7999ms from the second showError call
          vi.advanceTimersByTime(7999);
          expect(notificationEl.classList.contains("d-none")).toBe(false);
          expect(notificationEl.textContent).toContain(message2);

          // Advance 1 more ms — now 8000ms since second showError, should dismiss
          vi.advanceTimersByTime(1);
          expect(notificationEl.classList.contains("d-none")).toBe(true);
          expect(notificationEl.innerHTML).toBe("");
        }
      ),
      { numRuns: 100 }
    );
  });
});
