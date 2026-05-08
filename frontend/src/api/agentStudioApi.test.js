import { beforeEach, describe, expect, it, vi } from "vitest";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPut = vi.fn();

vi.mock("./axiosClient", () => ({
  api: {
    get: (...args) => mockGet(...args),
    post: (...args) => mockPost(...args),
    put: (...args) => mockPut(...args),
  },
}));

describe("agentStudioApi", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockPut.mockReset();
  });

  it("calls list endpoint with account id", async () => {
    const { listAgentStudioConfigs } = await import("./agentStudioApi");
    await listAgentStudioConfigs("acc-1");
    expect(mockGet).toHaveBeenCalledWith("/agent-studio/configs", {
      params: { account_id: "acc-1" },
    });
  });

  it("calls create and update endpoints with payload", async () => {
    const { createAgentStudioConfig, updateAgentStudioConfig } = await import("./agentStudioApi");
    const payload = { account_id: "a1", config: { name: "x" } };
    await createAgentStudioConfig(payload);
    await updateAgentStudioConfig("cfg-1", payload);
    expect(mockPost).toHaveBeenCalledWith("/agent-studio/configs", payload);
    expect(mockPut).toHaveBeenCalledWith("/agent-studio/configs/cfg-1", payload);
  });

  it("calls canary deploy with params", async () => {
    const { deployAgentStudioCanary } = await import("./agentStudioApi");
    await deployAgentStudioCanary("cfg-1", 20);
    expect(mockPost).toHaveBeenCalledWith(
      "/agent-studio/configs/cfg-1/deploy/canary",
      null,
      { params: { canary_percent: 20 } }
    );
  });
});

