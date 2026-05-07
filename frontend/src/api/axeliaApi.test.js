import { beforeEach, describe, expect, it, vi } from "vitest";

const mockPost = vi.fn();

vi.mock("./axiosClient", () => ({
  api: {
    defaults: { baseURL: "http://localhost:8000" },
    post: (...args) => mockPost(...args),
    get: vi.fn(),
    patch: vi.fn(),
  },
  handleSessionUnauthorized: vi.fn(),
}));

vi.mock("./supabaseClient", () => ({
  supabaseClient: {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "token-test" } },
      })),
    },
  },
}));

describe("axeliaApi", () => {
  beforeEach(() => {
    mockPost.mockReset();
    vi.restoreAllMocks();
  });

  it("forward postAxeliaChat payload including response_depth", async () => {
    const { postAxeliaChat } = await import("./axeliaApi");
    const payload = {
      account_id: "acc-1",
      conversation_id: "conv-1",
      user_message: "Bonjour",
      response_depth: "expert",
    };
    await postAxeliaChat(payload);
    expect(mockPost).toHaveBeenCalledWith("/axelia/chat", payload, {});
  });

  it("sends response_depth in streamAxeliaChat fetch body", async () => {
    const { streamAxeliaChat } = await import("./axeliaApi");
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue({
        ok: true,
        body: {
          getReader: () => ({
            read: vi.fn(async () => ({ done: true, value: undefined })),
          }),
        },
      });
    const onEvent = vi.fn();

    const payload = {
      account_id: "acc-1",
      conversation_id: "conv-1",
      user_message: "Analyse",
      response_depth: "expert",
    };
    await streamAxeliaChat(payload, { onEvent });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const fetchCall = fetchSpy.mock.calls[0];
    const opts = fetchCall[1];
    const sent = JSON.parse(opts.body);
    expect(sent.response_depth).toBe("expert");
    fetchSpy.mockRestore();
  });
});
