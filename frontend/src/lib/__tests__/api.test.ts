import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getAccessToken: vi.fn<() => Promise<string | null>>(),
  refreshSession: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("@/lib/supabase", () => ({
  getAccessToken: mocks.getAccessToken,
  supabase: {
    auth: {
      refreshSession: mocks.refreshSession,
      signOut: mocks.signOut,
    },
  },
}));

import { api, authFetch } from "../api";

function installLocation(pathname = "/start") {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      location: {
        pathname,
        assign: vi.fn(),
      },
    },
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("canonical frontend API transport", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mocks.getAccessToken.mockResolvedValue("valid-token");
    mocks.refreshSession.mockResolvedValue({
      data: { session: { access_token: "refreshed-token" } },
      error: null,
    });
    mocks.signOut.mockResolvedValue({ error: null });
    installLocation();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ ok: true })));
  });

  it("sources and attaches a valid Supabase bearer token and request ID", async () => {
    await api.get<{ ok: boolean }>("/api/v1/projects");

    const [, init] = vi.mocked(fetch).mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer valid-token");
    expect(headers.get("X-Request-ID")).toBeTruthy();
    expect(mocks.getAccessToken).toHaveBeenCalledTimes(1);
  });

  it("fails closed and redirects when no session token can be refreshed", async () => {
    mocks.getAccessToken.mockResolvedValue(null);
    mocks.refreshSession.mockResolvedValue({ data: { session: null }, error: null });
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: "missing token" }, 401));

    await expect(api.get("/api/v1/projects")).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
    });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
    expect(mocks.signOut).toHaveBeenCalledTimes(1);
    expect(window.location.assign).toHaveBeenCalledWith("/login");
  });

  it("sends no bearer for an explicitly unauthenticated health probe", async () => {
    await api.get<{ status: string }>("/", { noAuth: true });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
    expect(mocks.refreshSession).not.toHaveBeenCalled();
  });

  it("refreshes once after a 401 and replays with the refreshed token", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));

    await api.post("/api/v1/jobs", { name: "test" });

    expect(mocks.refreshSession).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetch)).toHaveBeenCalledTimes(2);
    const [, replayInit] = vi.mocked(fetch).mock.calls[1];
    expect(new Headers(replayInit?.headers).get("Authorization")).toBe("Bearer refreshed-token");
    expect(mocks.signOut).not.toHaveBeenCalled();
  });

  it("clears the session and redirects after refresh failure", async () => {
    mocks.refreshSession.mockResolvedValue({ data: { session: null }, error: new Error("expired") });
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401));

    await expect(api.get("/api/v1/projects")).rejects.toMatchObject({
      status: 401,
      code: "UNAUTHORIZED",
    });

    expect(mocks.refreshSession).toHaveBeenCalledTimes(1);
    expect(mocks.signOut).toHaveBeenCalledTimes(1);
    expect(window.location.assign).toHaveBeenCalledWith("/login");
  });

  it("does not create a redirect loop when already on /login", async () => {
    installLocation("/login");
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: "expired" }, 401));

    await expect(api.get("/api/v1/projects")).rejects.toMatchObject({ status: 401 });

    expect(mocks.signOut).toHaveBeenCalledTimes(1);
    expect(window.location.assign).not.toHaveBeenCalled();
  });

  it.each(["org_id", "orgId", "org-id", "organization_id"]) (
    "rejects %s query selectors before network access",
    async (selector) => {
      await expect(api.get(`/api/v1/projects?${selector}=foreign-org`)).rejects.toMatchObject({
        status: 422,
        code: "VALIDATION",
      });
      expect(vi.mocked(fetch)).not.toHaveBeenCalled();
    }
  );

  it("routes authFetch through canonical auth and preserves Response compatibility", async () => {
    const response = jsonResponse({ items: [] });
    vi.mocked(fetch).mockResolvedValueOnce(response);

    const result = await authFetch("http://localhost:8000/api/v1/assets");

    expect(result).toBe(response);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer valid-token");
    expect(new Headers(init?.headers).get("X-Request-ID")).toBeTruthy();
  });
});
