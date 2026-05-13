import { describe, expect, it } from "vitest";
import { toAxeliaModelLabel } from "./axeliaModelLabel";

describe("toAxeliaModelLabel", () => {
  it("maps gemini 2.5 pro to Axelia Pro", () => {
    expect(toAxeliaModelLabel("gemini-2.5-pro")).toBe("Axelia Pro");
  });

  it("maps gemini flash models to Axelia Fast", () => {
    expect(toAxeliaModelLabel("gemini-2.5-flash")).toBe("Axelia Fast");
    expect(toAxeliaModelLabel("gemini-1.5-flash")).toBe("Axelia Fast");
  });

  it("falls back to generic Axelia", () => {
    expect(toAxeliaModelLabel("gemini-xyz")).toBe("Axelia");
    expect(toAxeliaModelLabel("")).toBe("");
  });
});

