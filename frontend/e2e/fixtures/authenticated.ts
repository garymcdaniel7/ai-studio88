/* eslint-disable react-hooks/rules-of-hooks */
import { mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { test as base, expect, type BrowserContext, type Page, type Route } from "@playwright/test";
import { PLAYWRIGHT_AUTH_COOKIE } from "../../src/lib/auth-utils";

export interface TestTenant {
  orgId: string;
  userId: string;
}

type AuthTestFixtures = {
  authenticatedContext: BrowserContext;
  authenticatedPage: Page;
  testTenant: TestTenant;
};

type AuthWorkerFixtures = {
  authenticatedState: { path: string; reason?: undefined } | { path?: undefined; reason: string };
};

const MOCK_UNIVERSE = { id: "universe-1", name: "Continuity House" };
const MOCK_EPISODE = {
  id: "episode-1",
  universe_id: MOCK_UNIVERSE.id,
  title: "Episode 01",
  episode_number: 1,
  status: "draft",
};
const MOCK_SCENE = {
  id: "scene-1",
  episode_id: MOCK_EPISODE.id,
  scene_number: 1,
  location: "Rooftop",
  time_of_day: "night",
  characters: ["character-1"],
};
const MOCK_SHOT = {
  id: "shot-1",
  scene_id: MOCK_SCENE.id,
  shot_number: 1,
  shot_type: "medium",
  description: "### Subject\nA person on a rooftop\n\n### Action\nLooks over the city\n\n### Camera\nSlow dolly in\n\n### Lighting\nBlue hour\n\n### Sound\nWind\n\n### Style\nCinematic",
  status: "planned",
  generation_params: { model_id: "h3-preview", frame_grid: 226, seed: 42 },
};

function isLoopbackUrl(value: string | undefined): boolean {
  if (!value) return false;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname);
  } catch {
    return false;
  }
}

function statePath(testInfo: { project: { outputDir: string; name: string }; workerIndex: number }): string {
  return path.join(testInfo.project.outputDir, ".auth", `${testInfo.project.name}-${testInfo.workerIndex}.json`);
}

function unavailable(reason: string): AuthWorkerFixtures["authenticatedState"] {
  return { reason };
}

async function mockApiResponse(route: Route, body: unknown): Promise<void> {
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
}

/**
 * Provide deterministic, loopback-only API data for mock-auth browser tests.
 * This route belongs to the Playwright context and is never part of runtime code.
 */
async function mockDataProvider(route: Route): Promise<void> {
  const request = route.request();
  const url = new URL(request.url());
  if (!url.pathname.startsWith("/api/v1/")) {
    await route.continue();
    return;
  }

  const method = request.method();
  const pathname = url.pathname;
  if (method === "GET" && pathname === "/api/v1/universes") return mockApiResponse(route, [MOCK_UNIVERSE]);
  if (method === "GET" && pathname === `/api/v1/universes/${MOCK_UNIVERSE.id}/episodes`) return mockApiResponse(route, [MOCK_EPISODE]);
  if (method === "GET" && pathname === `/api/v1/episodes/${MOCK_EPISODE.id}/scenes`) return mockApiResponse(route, [MOCK_SCENE]);
  if (method === "GET" && pathname === `/api/v1/scenes/${MOCK_SCENE.id}/shots`) return mockApiResponse(route, [MOCK_SHOT]);
  if (pathname === `/api/v1/shots/${MOCK_SHOT.id}` && method === "GET") return mockApiResponse(route, MOCK_SHOT);
  if (pathname === `/api/v1/shots/${MOCK_SHOT.id}` && method === "PUT") {
    let patch: Record<string, unknown> = {};
    try {
      const body = request.postDataJSON();
      if (body && typeof body === "object" && !Array.isArray(body)) patch = body as Record<string, unknown>;
    } catch {
      patch = {};
    }
    return mockApiResponse(route, { ...MOCK_SHOT, ...patch });
  }
  if (pathname === `/api/v1/shots/${MOCK_SHOT.id}/generate` && method === "POST") {
    return mockApiResponse(route, {
      shot_id: MOCK_SHOT.id,
      job_id: "job-preview-1",
      status: "queued",
      workflow_id: "workflow-preview",
      model_id: "h3-preview",
      seed: 9876,
    });
  }

  if (pathname === "/api/v1/generate/available-models") return mockApiResponse(route, { models: [] });
  if (pathname === "/api/v1/infrastructure/status") return mockApiResponse(route, { worker: {} });
  if (pathname.endsWith("/voices/elevenlabs") || pathname.endsWith("/voices/moss")) return mockApiResponse(route, { voices: [] });
  if (pathname === "/api/v1/projects") return mockApiResponse(route, { projects: [] });
  if (pathname === "/api/v1/models" || pathname === "/api/v1/presets" || pathname === "/api/v1/talent" || pathname === "/api/v1/jobs") return mockApiResponse(route, []);
  if (pathname.startsWith("/api/v1/generate/batch/")) return mockApiResponse(route, { batch_id: "mock-batch-1", state: "completed", variations: [] });

  // Keep mock mode hermetic: no unlisted API request reaches a backend.
  return mockApiResponse(route, {});
}

async function installMockDataProvider(context: BrowserContext): Promise<void> {
  await context.route("**/api/v1/**", mockDataProvider);
}

/**
 * Authenticated browser fixtures for local/test-only WRITE and MAKE checks.
 *
 * Only explicit local-password or mock mode is supported. The worker creates one
 * reusable storage state; each test gets a fresh context from that state.
 * Mock mode requires the loopback Playwright proxy seam and a test-only cookie.
 * Dotenv files, external BASE_URL values, credentials, cookies, and tokens are
 * never read, printed, or copied into reports.
 */
export const test = base.extend<AuthTestFixtures, AuthWorkerFixtures>({
  testTenant: async ({}, use) => {
    await use({
      orgId: process.env.PLAYWRIGHT_TEST_ORG_ID || "playwright-local-org",
      userId: process.env.PLAYWRIGHT_TEST_USER_ID || "playwright-local-user",
    });
  },

  authenticatedState: [async ({ browser }, use, workerInfo) => {
    const configuredBaseURL = workerInfo.project.use.baseURL;
    const baseURL = typeof configuredBaseURL === "string" ? configuredBaseURL : "";
    if (!isLoopbackUrl(baseURL)) {
      await use(unavailable("Authenticated fixture requires a loopback BASE_URL"));
      return;
    }
    const authMode = process.env.PLAYWRIGHT_AUTH_MODE;
    if (authMode !== "local-password" && authMode !== "mock") {
      await use(unavailable("Set PLAYWRIGHT_AUTH_MODE=mock or local-password for authenticated checks"));
      return;
    }
    if (authMode === "local-password" && !isLoopbackUrl(process.env.NEXT_PUBLIC_SUPABASE_URL)) {
      await use(unavailable("Local auth emulator required: NEXT_PUBLIC_SUPABASE_URL must be loopback"));
      return;
    }

    const email = process.env.PLAYWRIGHT_TEST_EMAIL ?? "";
    const password = process.env.PLAYWRIGHT_TEST_PASSWORD ?? "";
    if (authMode === "local-password" && (!email || !password)) {
      await use(unavailable("Local auth emulator credentials are unavailable; authenticated WRITE/MAKE checks are skipped"));
      return;
    }

    const storageFile = statePath(workerInfo);
    await mkdir(path.dirname(storageFile), { recursive: true });
    let hasStorageState = false;
    try {
      await stat(storageFile);
      hasStorageState = true;
    } catch {
      hasStorageState = false;
    }

    const context = await browser.newContext(hasStorageState ? { storageState: storageFile } : {});
    if (authMode === "mock") await installMockDataProvider(context);
    if (authMode === "mock" && !hasStorageState) {
      await context.addCookies([{
        name: PLAYWRIGHT_AUTH_COOKIE,
        value: "authenticated",
        domain: new URL(baseURL).hostname,
        path: "/",
        httpOnly: false,
        sameSite: "Lax",
      }]);
    }
    const page = await context.newPage();
    try {
      const entryPath = hasStorageState || authMode === "mock" ? "/write" : "/login?redirect=%2Fwrite";
      await page.goto(entryPath, { waitUntil: "domcontentloaded" });
      if (authMode === "local-password" && await page.getByText("Supabase is not configured", { exact: false }).count()) {
        await use(unavailable("The local frontend has no configured auth emulator"));
        return;
      }
      if (authMode === "local-password" && page.url().includes("/login")) {
        await page.getByLabel("Email").fill(email);
        await page.getByLabel("Password").fill(password);
        await page.getByRole("button", { name: "Sign In" }).click();
        await page.waitForURL((url) => url.pathname !== "/login", { timeout: 15000 });
      }
      await context.storageState({ path: storageFile });
      await use({ path: storageFile });
    } catch {
      const reason = authMode === "mock"
        ? "Mock authenticated bootstrap failed while creating the per-worker storage state"
        : "Local auth emulator login did not complete; authenticated checks are skipped";
      await use(unavailable(reason));
    } finally {
      await page.close();
      await context.close();
    }
  }, { scope: "worker" }],

  authenticatedContext: async ({ browser, authenticatedState }, use, testInfo) => {
    if (!authenticatedState.path) {
      testInfo.skip(true, authenticatedState.reason);
      return;
    }
    const context = await browser.newContext({ storageState: authenticatedState.path });
    if (process.env.PLAYWRIGHT_AUTH_MODE === "mock") await installMockDataProvider(context);
    await use(context);
    await context.close();
  },

  authenticatedPage: async ({ authenticatedContext }, use) => {
    const page = await authenticatedContext.newPage();
    await use(page);
    await page.close();
  },
});

export { expect };
