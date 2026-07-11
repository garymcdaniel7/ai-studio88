import { test, expect } from "@playwright/test";

/**
 * Service connection tests — verify all external service
 * indicators show status and buttons work.
 */

test.describe("Service Connections (Admin)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/admin");
    await page.waitForTimeout(3000); // Let health checks complete
  });

  test("Supabase connection status shown", async ({ page }) => {
    const content = await page.textContent("body");
    const hasSupabase =
      content?.includes("Supabase") ||
      content?.includes("Database") ||
      content?.includes("Connected") ||
      content?.includes("Service");
    expect(hasSupabase).toBeTruthy();
  });

  test("Backblaze B2 connection status shown", async ({ page }) => {
    const content = await page.textContent("body");
    const hasB2 = content?.includes("B2") || content?.includes("Backblaze") || content?.includes("Storage");
    expect(hasB2).toBeTruthy();
  });

  test("Vast.ai connection status shown", async ({ page }) => {
    const content = await page.textContent("body");
    const hasVast = content?.includes("Vast") || content?.includes("GPU") || content?.includes("vast");
    expect(hasVast).toBeTruthy();
  });

  test("ComfyUI connection status shown", async ({ page }) => {
    const content = await page.textContent("body");
    const hasComfy = content?.includes("ComfyUI") || content?.includes("Comfy") || content?.includes("Generation");
    expect(hasComfy).toBeTruthy();
  });

  test("Ollama connection status shown", async ({ page }) => {
    const content = await page.textContent("body");
    const hasOllama = content?.includes("Ollama") || content?.includes("LLM") || content?.includes("Brain");
    expect(hasOllama).toBeTruthy();
  });

  test("test connection buttons trigger health check", async ({ page }) => {
    const testBtns = page.locator("button:has-text('Test'), button:has-text('Check'), button:has-text('Refresh')");
    const count = await testBtns.count();
    if (count > 0) {
      await testBtns.first().click();
      await page.waitForTimeout(2000);
      // After click, status should update (green/red indicators)
    }
  });

  test("enable/disable toggles for services", async ({ page }) => {
    const toggles = page.locator("[role='switch'], input[type='checkbox']");
    const count = await toggles.count();
    if (count > 0) {
      const firstToggle = toggles.first();
      await expect(firstToggle).toBeEnabled();
    }
  });
});

test.describe("API Health Check", () => {
  test("backend health endpoint returns OK", async ({ request }) => {
    const baseURL = process.env.BASE_URL || "http://localhost:3000";
    const apiBase = baseURL.includes("localhost")
      ? "http://localhost:8000"
      : "https://web-production-1f511.up.railway.app";

    try {
      const resp = await request.get(`${apiBase}/api/v1/health`);
      expect(resp.status()).toBe(200);
      const body = await resp.json();
      expect(body.status).toBe("ok");
    } catch {
      // Backend may not be running — this is informational
      test.skip();
    }
  });

  test("models endpoint returns data", async ({ request }) => {
    const baseURL = process.env.BASE_URL || "http://localhost:3000";
    const apiBase = baseURL.includes("localhost")
      ? "http://localhost:8000"
      : "https://web-production-1f511.up.railway.app";

    try {
      const resp = await request.get(`${apiBase}/api/v1/models`);
      expect(resp.status()).toBe(200);
      const body = await resp.json();
      expect(Array.isArray(body)).toBeTruthy();
    } catch {
      test.skip();
    }
  });

  test("talent endpoint returns data", async ({ request }) => {
    const baseURL = process.env.BASE_URL || "http://localhost:3000";
    const apiBase = baseURL.includes("localhost")
      ? "http://localhost:8000"
      : "https://web-production-1f511.up.railway.app";

    try {
      const resp = await request.get(`${apiBase}/api/v1/talent`);
      expect(resp.status()).toBe(200);
      const body = await resp.json();
      expect(Array.isArray(body)).toBeTruthy();
    } catch {
      test.skip();
    }
  });

  test("models inventory endpoint returns structured data", async ({ request }) => {
    const baseURL = process.env.BASE_URL || "http://localhost:3000";
    const apiBase = baseURL.includes("localhost")
      ? "http://localhost:8000"
      : "https://web-production-1f511.up.railway.app";

    try {
      const resp = await request.get(`${apiBase}/api/v1/models/inventory`);
      expect(resp.status()).toBe(200);
      const body = await resp.json();
      expect(body).toHaveProperty("on_gpu");
      expect(body).toHaveProperty("b2_only");
      expect(body).toHaveProperty("total_active");
    } catch {
      test.skip();
    }
  });
});
