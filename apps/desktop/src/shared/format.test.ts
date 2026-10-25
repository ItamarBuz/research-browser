import { describe, expect, it } from "vitest";

import { formatBytes, formatPercent, isolate } from "./format";

describe("formatBytes", () => {
  it("uses MB below a gigabyte and GB above", () => {
    expect(formatBytes(129 * 1024 ** 2, "en")).toBe(isolate("129 MB"));
    expect(formatBytes(2.34 * 1024 ** 3, "en")).toBe(isolate("2.3 GB"));
  });

  it("isolates values so they keep their direction inside Hebrew text", () => {
    const value = formatBytes(63.7 * 1024 ** 3, "he");
    expect(value.startsWith("⁨")).toBe(true);
    expect(value.endsWith("⁩")).toBe(true);
    expect(value).toContain("63.7");
  });
});

describe("formatPercent", () => {
  it("rounds to whole percent", () => {
    expect(formatPercent(0.704, "en")).toBe(isolate("70%"));
  });
});
