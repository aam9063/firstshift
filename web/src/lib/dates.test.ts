import { describe, expect, it } from "vitest";
import { formatDateTime } from "./dates";

describe("formatDateTime", () => {
  it("renders dd/mm/yyyy HH:mm in local time", () => {
    const local = new Date(2026, 9, 23, 7, 40);
    expect(formatDateTime(local.toISOString())).toBe("23/10/2026 07:40");
  });

  it("pads single-digit day, month, hour and minute", () => {
    const local = new Date(2027, 0, 5, 3, 7);
    expect(formatDateTime(local.toISOString())).toBe("05/01/2027 03:07");
  });

  it("returns an empty string for an empty value", () => {
    expect(formatDateTime("")).toBe("");
    expect(formatDateTime(null)).toBe("");
  });

  it("passes an unparseable value through instead of inventing a date", () => {
    expect(formatDateTime("not a date")).toBe("not a date");
  });
});
