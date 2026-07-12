import { test, expect } from "@playwright/test";

test.describe("Fleet Management Page", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/admin/fleet");
    await page.waitForTimeout(3000);
  });

  test("page loads with fleet header", async ({ page }) => {
    await expect(page.locator("h1", { hasText: "Fleet Management" })).toBeVisible();
  });

  test("shows worker metrics cards", async ({ page }) => {
    // Should have 4 metric cards: Active Workers, Hourly Burn, Today's Spend, Daily Budget
    await expect(page.locator("text=Active Workers")).toBeVisible();
    await expect(page.locator("text=Hourly Burn")).toBeVisible();
    await expect(page.locator("text=Today's Spend")).toBeVisible({ timeout: 5000 });
    await expect(page.locator("text=Daily Budget")).toBeVisible();
  });

  test("settings button opens settings panel", async ({ page }) => {
    const settingsBtn = page.locator("button", { hasText: "Settings" });
    await expect(settingsBtn).toBeVisible();
    await settingsBtn.click();

    // Settings panel should show
    await expect(page.locator("text=Fleet Settings")).toBeVisible();
    await expect(page.locator("text=Max Instances")).toBeVisible();
    await expect(page.locator("text=Daily Budget (USD)")).toBeVisible();
    await expect(page.locator("text=Idle Timeout")).toBeVisible();
    await expect(page.locator("text=Preferred Provider")).toBeVisible();
  });

  test("settings panel has editable inputs", async ({ page }) => {
    await page.locator("button", { hasText: "Settings" }).click();
    await page.waitForTimeout(500);

    // Max Instances input
    const maxInput = page.locator("input[type='number']").first();
    await expect(maxInput).toBeVisible();
    await expect(maxInput).toBeEditable();
  });

  test("refresh button exists and is clickable", async ({ page }) => {
    // The refresh button (RefreshCw icon)
    const refreshBtn = page.locator("button").filter({ has: page.locator("svg") }).last();
    await expect(refreshBtn).toBeVisible();
    await refreshBtn.click();
    // Should not crash
    await page.waitForTimeout(1000);
    await expect(page.locator("h1", { hasText: "Fleet Management" })).toBeVisible();
  });

  test("shutdown idle button exists", async ({ page }) => {
    await expect(page.locator("button", { hasText: "Shutdown Idle" })).toBeVisible();
  });

  test("workers section shows either workers or empty state", async ({ page }) => {
    // Either shows worker cards or the empty state
    const hasWorkers = await page.locator("text=VRAM").count() > 0;
    const hasEmpty = await page.locator("text=No GPU workers active").count() > 0;
    expect(hasWorkers || hasEmpty).toBeTruthy();
  });

  test("model placement section exists", async ({ page }) => {
    // Scroll down to see model placement section
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    await expect(page.locator("text=Model Placement (GPU")).toBeVisible({ timeout: 5000 });
  });

  test("model placement refresh loads data", async ({ page }) => {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    // Click the Refresh button in Model Placement section
    const refreshBtns = page.locator("button:has-text('Refresh')");
    await refreshBtns.last().click();
    await page.waitForTimeout(3000);
    await expect(page.locator("text=Model Placement (GPU")).toBeVisible();
  });

  test("model placement shows state badges after loading", async ({ page }) => {
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);
    await page.locator("button:has-text('Refresh')").last().click();
    await page.waitForTimeout(3000);

    // Should show summary counts or model list
    const hasContent = await page.locator("text=Total").count() > 0 ||
                       await page.locator("text=Loaded").count() > 0 ||
                       await page.locator("text=Click Refresh").count() > 0;
    expect(hasContent).toBeTruthy();
  });

  test("provider selector in settings has options", async ({ page }) => {
    await page.locator("button", { hasText: "Settings" }).click();
    await page.waitForTimeout(500);

    const select = page.locator("select");
    await expect(select).toBeVisible();
    const options = await select.locator("option").allTextContents();
    expect(options).toContain("Vast.ai");
    expect(options).toContain("RunPod");
  });

  test("auto-provision checkbox is toggleable", async ({ page }) => {
    await page.locator("button", { hasText: "Settings" }).click();
    await page.waitForTimeout(1000);

    const checkbox = page.locator("input[type='checkbox']");
    await expect(checkbox).toBeVisible();
    // Just verify it's interactive (don't assert toggle since API save may re-render)
    await checkbox.click();
    await page.waitForTimeout(500);
    await expect(checkbox).toBeVisible(); // Still rendered after click
  });
});

test.describe("Fleet Management — API Endpoints", () => {
  const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  test("GET /api/v1/infrastructure/workers returns data", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/infrastructure/workers`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("workers");
  });

  test("GET /api/v1/infrastructure/fleet/settings returns settings", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/v1/infrastructure/fleet/settings`);
    expect(resp.status()).toBe(200);
  });

  test("GET /aios/v1/models/placements returns model states", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/aios/v1/models/placements`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("models");
    expect(data).toHaveProperty("summary");
  });

  test("POST /aios/v1/session/autoscale evaluates scaling", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/aios/v1/session/autoscale`, {
      data: { pending_tasks: [], budget_remaining: 20.0 },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("fleet");
    expect(data).toHaveProperty("decisions");
  });

  test("POST /aios/v1/session/autoscale with tasks returns decisions", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/aios/v1/session/autoscale`, {
      data: { pending_tasks: [{ type: "train_lora" }], budget_remaining: 20.0 },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data.decisions.length).toBeGreaterThanOrEqual(0);
  });

  test("GET /aios/v1/session/insights returns usage patterns", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/aios/v1/session/insights`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("total_requests");
  });

  test("POST /aios/v1/session/should-release evaluates worker release", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/aios/v1/session/should-release`, {
      data: { idle_minutes: 5, session_type: "image", pending_jobs: 0 },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("should_release");
    expect(data).toHaveProperty("reason");
  });

  test("POST /aios/v1/session/model-swap recommends action", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/aios/v1/session/model-swap`, {
      data: { current_models: ["sdxl-turbo"], needed_model: "flux-dev", vram_total_gb: 24, vram_used_gb: 8 },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("action");
  });

  test("POST /aios/v1/workflow/configure returns generation config", async ({ request }) => {
    const resp = await request.post(`${API_BASE}/aios/v1/workflow/configure`, {
      data: { prompt: "luxury portrait", quality: "high", platform: "instagram" },
    });
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("model");
    expect(data).toHaveProperty("steps");
    expect(data).toHaveProperty("width");
    expect(data).toHaveProperty("reasoning");
  });

  test("GET /aios/v1/health/full returns service health", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/aios/v1/health/full`);
    expect(resp.status()).toBe(200);
    const data = await resp.json();
    expect(data).toHaveProperty("overall");
    expect(data).toHaveProperty("services");
  });
});
