import { describe, expect, it } from "vitest";
import { toAxeliaDepthLabel } from "./axeliaDepthLabel";

describe("toAxeliaDepthLabel", () => {
  it("maps known depth modes", () => {
    expect(toAxeliaDepthLabel("brief")).toBe("Mode Bref");
    expect(toAxeliaDepthLabel("standard")).toBe("Mode Standard");
    expect(toAxeliaDepthLabel("expert")).toBe("Mode Expert");
  });

  it("falls back to Mode Standard", () => {
    expect(toAxeliaDepthLabel("unknown")).toBe("Mode Standard");
    expect(toAxeliaDepthLabel("")).toBe("Mode Standard");
  });
});

