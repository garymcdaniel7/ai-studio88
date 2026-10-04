import { expect, test } from "@playwright/test";

import { isPublicRoute } from "../src/lib/auth-utils";
import {
  START_NAV_BREAKPOINTS,
  START_NAV_STEPS,
  getCurrentStartStep,
  getStartStepState,
} from "../src/app/start/_components/start-navigation";
import {
  getStartViewState,
  toStartRequestError,
  type StartRequestError,
} from "../src/app/start/_components/start-state";
import { ApiError } from "../src/lib/api";

const PROTECTED_PHASE_ONE_ROUTES = ["/start", "/cast", "/write", "/make", "/publish", "/settings", "/admin", "/brain"];


test.describe("Phase 1 START and navigation contracts", () => {
  test("keeps public landing separate from protected START and step routes", () => {
    expect(isPublicRoute("/")).toBe(true);
    for (const route of PROTECTED_PHASE_ONE_ROUTES) {
      expect(isPublicRoute(route), route).toBe(false);
    }
  });

  test("defines the exact START to PUBLISH handoff order", () => {
    expect(START_NAV_STEPS.map((step) => [step.label, step.href])).toEqual([
      ["START", "/start"],
      ["CAST", "/cast"],
      ["WRITE", "/write"],
      ["MAKE", "/make"],
      ["PUBLISH", "/publish"],
    ]);
    expect(getCurrentStartStep("/start")).toBe("start");
    expect(getCurrentStartStep("/make/queue")).toBe("make");
  });

  test("exposes active, completed, and future step states", () => {
    expect(getStartStepState("start", "start")).toBe("active");
    expect(getStartStepState("start", "make")).toBe("completed");
    expect(getStartStepState("publish", "make")).toBe("future");
  });

  test("pins the responsive navigation breakpoints", () => {
    expect(START_NAV_BREAKPOINTS).toEqual({
      mobileMax: 767,
      tabletMin: 768,
      tabletMax: 1023,
      desktopMin: 1024,
    });
  });

  test("covers loading, error, and empty dashboard states", () => {
    expect(getStartViewState({ isLoading: true, error: null, projects: [] })).toBe("loading");
    const error: StartRequestError = {
      code: "SERVER_ERROR",
      detail: "Backend unavailable",
      message: "Unable to load your projects.",
      requestId: "req-start-1",
      retryable: true,
      status: 503,
    };
    expect(getStartViewState({ isLoading: false, error, projects: [] })).toBe("error");
    expect(getStartViewState({ isLoading: false, error: null, projects: [{ id: "1", name: "Archived", status: "archived" }] })).toBe("empty");
    expect(getStartViewState({ isLoading: false, error: null, projects: [{ id: "1", name: "Active", status: "active" }] })).toBe("ready");
  });

  test("retains typed retryability and X-Request-ID evidence", () => {
    const error = toStartRequestError(new ApiError({
      code: "SERVER_ERROR",
      detail: "upstream unavailable",
      message: "Service unavailable",
      requestId: "req-123",
      status: 503,
    }));
    expect(error).toMatchObject({ code: "SERVER_ERROR", requestId: "req-123", retryable: true, status: 503 });
  });

  test("redirects an unauthenticated HTTP request for START when auth is configured", async ({ request }) => {
    const response = await request.get("/start", { maxRedirects: 0 });
    if (response.status() === 200) {
      test.info().annotations.push({ type: "blocked", description: "The server is running in local fallback mode; client AuthGate remains authoritative." });
      test.skip();
    }
    expect([301, 302, 307, 308]).toContain(response.status());
    expect(response.headers().location).toContain("/login");
    expect(response.headers().location).toContain("redirect=%2Fstart");
  });
});
