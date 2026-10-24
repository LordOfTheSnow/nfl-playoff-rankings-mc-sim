/**
 * Kickoff display tests: Team Detail's formatKickoff (viewer-local time,
 * Eastern date for not-yet-scheduled games) and the Matchups card's
 * _matchupDayLabel (Eastern Time broadcast day).
 */

import { describe, it, expect } from "vitest";
import fc from "fast-check";

const WEEKDAYS = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"];

/** Collapse the narrow no-break space some ICU versions put before AM/PM. */
const norm = (s) => s.replace(/\s/g, " ");

/** Arbitrary UTC kickoff instant within [hourMin, hourMax] UTC, 2020-2030 seasons. */
function utcKickoff(hourMin, hourMax) {
  return fc
    .record({
      day: fc.date({ min: new Date("2020-09-01T00:00:00Z"), max: new Date("2030-02-01T00:00:00Z") }),
      hour: fc.integer({ min: hourMin, max: hourMax }),
      minute: fc.integer({ min: 0, max: 59 }),
    })
    .map(({ day, hour, minute }) =>
      new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth(), day.getUTCDate(), hour, minute)),
    );
}

describe("_matchupDayLabel", () => {
  it("names prime-time games by their Eastern broadcast day", () => {
    // 2026 week 7: TNF, SNF, MNF all kick off after midnight UTC.
    expect(_matchupDayLabel({ kickoff: "2026-10-23T00:15:00+00:00", date: "2026-10-23" })).toBe("THURSDAY");
    expect(_matchupDayLabel({ kickoff: "2026-10-26T00:20:00+00:00", date: "2026-10-26" })).toBe("SUNDAY");
    expect(_matchupDayLabel({ kickoff: "2026-10-27T00:15:00+00:00", date: "2026-10-27" })).toBe("MONDAY");
    // International morning game, and MNF after the November DST change (EST).
    expect(_matchupDayLabel({ kickoff: "2026-10-25T13:30:00+00:00", date: "2026-10-25" })).toBe("SUNDAY");
    expect(_matchupDayLabel({ kickoff: "2026-11-03T01:15:00+00:00", date: "2026-11-03" })).toBe("MONDAY");
  });

  it("puts 00:00-03:59 UTC kickoffs on the previous day (evening in ET, EDT or EST)", () => {
    fc.assert(
      fc.property(utcKickoff(0, 3), (kickoff) => {
        const expected = WEEKDAYS[(kickoff.getUTCDay() + 6) % 7];
        expect(_matchupDayLabel({ kickoff: kickoff.toISOString(), date: "1970-01-01" })).toBe(expected);
      }),
      { numRuns: 100 },
    );
  });

  it("keeps 10:00-23:59 UTC kickoffs on the same day", () => {
    fc.assert(
      fc.property(utcKickoff(10, 23), (kickoff) => {
        expect(_matchupDayLabel({ kickoff: kickoff.toISOString(), date: "1970-01-01" })).toBe(
          WEEKDAYS[kickoff.getUTCDay()],
        );
      }),
      { numRuns: 100 },
    );
  });

  it("falls back to the UTC date when there's no kickoff", () => {
    expect(_matchupDayLabel({ date: "2026-10-23" })).toBe("FRIDAY");
    expect(_matchupDayLabel({ kickoff: null, date: "2026-10-25" })).toBe("SUNDAY");
  });
});

describe("formatKickoff", () => {
  const tnf = { kickoff: "2026-10-23T00:15:00+00:00", kickoff_time_valid: true, date: "2026-10-23" };

  it("shows date and time in the viewer's timezone", () => {
    expect(norm(formatKickoff(tnf, "America/New_York"))).toBe("Thu, Oct 22 · 8:15 PM");
    expect(norm(formatKickoff(tnf, "America/Los_Angeles"))).toBe("Thu, Oct 22 · 5:15 PM");
    expect(norm(formatKickoff(tnf, "Europe/Berlin"))).toBe("Fri, Oct 23 · 2:15 AM");
  });

  it("shows the Eastern date plus TBD for unscheduled times, in any viewer timezone", () => {
    // ESPN's placeholder for an unscheduled time is midnight ET (05:00Z in EST).
    const tz = fc.constantFrom("America/Los_Angeles", "America/New_York", "Europe/Berlin", "Asia/Tokyo", "UTC");
    fc.assert(
      fc.property(utcKickoff(5, 5), tz, (placeholder, viewerTz) => {
        placeholder.setUTCMinutes(0);
        const game = { kickoff: placeholder.toISOString(), kickoff_time_valid: false };
        const expectedDay = placeholder.toLocaleDateString("en-US", {
          weekday: "short", month: "short", day: "numeric", timeZone: "America/New_York",
        });
        expect(formatKickoff(game, viewerTz)).toBe(`${expectedDay} · TBD`);
      }),
      { numRuns: 100 },
    );
    expect(formatKickoff({ kickoff: "2027-01-10T05:00:00+00:00", kickoff_time_valid: false }, "America/Los_Angeles"))
      .toBe("Sun, Jan 10 · TBD");
  });

  it("falls back to the date-only field without a kickoff", () => {
    expect(formatKickoff({ date: "2026-10-23" })).toBe("Oct 23, 2026");
    expect(formatKickoff({})).toBe("TBD");
  });
});
