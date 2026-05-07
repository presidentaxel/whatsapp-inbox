import { beforeEach, describe, expect, it } from "vitest";
import { loadAxeliaResponseDepth, saveAxeliaResponseDepth } from "./axeliaSettings";

describe("axeliaSettings", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("loads standard by default", () => {
    expect(loadAxeliaResponseDepth()).toBe("standard");
  });

  it("persists and reloads expert", () => {
    saveAxeliaResponseDepth("expert");
    expect(loadAxeliaResponseDepth()).toBe("expert");
  });

  it("normalizes invalid value to standard", () => {
    saveAxeliaResponseDepth("unknown");
    expect(loadAxeliaResponseDepth()).toBe("standard");
  });
});

