import { test, expect } from "./fixtures/authenticated";

const universe = { id: "universe-1", name: "Continuity House" };
const episode = { id: "episode-1", universe_id: universe.id, title: "Episode 01", episode_number: 1, status: "draft" };
const scene = { id: "scene-1", episode_id: episode.id, scene_number: 1, location: "Rooftop", time_of_day: "night", characters: ["character-1"] };
const shot = {
  id: "shot-1", scene_id: scene.id, shot_number: 1, shot_type: "medium",
  description: "### Subject\nA person on a rooftop\n\n### Action\nLooks over the city\n\n### Camera\nSlow dolly in\n\n### Lighting\nBlue hour\n\n### Sound\nWind\n\n### Style\nCinematic",
  status: "planned", generation_params: { model_id: "h3-preview", frame_grid: 226, seed: 42 },
};

async function mockStoryApi(page: import("@playwright/test").Page): Promise<void> {
  await page.route("**/api/v1/universes", async (route) => {
    if (route.request().method() === "GET") await route.fulfill({ json: [universe] });
    else await route.continue();
  });
  await page.route(`**/api/v1/universes/${universe.id}/episodes`, (route) => route.fulfill({ json: [episode] }));
  await page.route(`**/api/v1/episodes/${episode.id}/scenes`, (route) => route.fulfill({ json: [scene] }));
  await page.route(`**/api/v1/scenes/${scene.id}/shots`, (route) => route.fulfill({ json: [shot] }));
  await page.route(`**/api/v1/shots/${shot.id}`, (route) => route.fulfill({ json: shot }));
  await page.route(`**/api/v1/shots/${shot.id}/generate`, (route) => route.fulfill({ json: { shot_id: shot.id, job_id: "job-preview-1", status: "queued", workflow_id: "workflow-preview", model_id: "h3-preview", seed: 9876 } }));
}

async function openWrite(page: import("@playwright/test").Page): Promise<void> {
  await page.goto("/write");
  await page.waitForLoadState("domcontentloaded");
  await expect(page.getByText("Story and storyboard")).toBeVisible();
}

test.describe("WRITE story editor", () => {
  test("redirects unauthenticated visitors to login", async ({ page }) => {
    await page.goto("/write");
    await page.waitForURL((url) => url.pathname === "/login" || url.pathname === "/write", { timeout: 10000 });
    if (page.url().includes("/login")) expect(page.url()).toContain("redirect=%2Fwrite");
  });

  test("renders episodes, storyboard, six-section prompt editor, and exact frame grid", async ({ authenticatedPage }) => {
    await mockStoryApi(authenticatedPage);
    await openWrite(authenticatedPage);
    await expect(authenticatedPage.getByRole("button", { name: /Episode 01/ })).toBeVisible();
    await expect(authenticatedPage.getByTestId("shot-card-shot-1")).toBeVisible();
    await authenticatedPage.getByTestId("edit-prompt").click();
    await expect(authenticatedPage.getByTestId("prompt-editor")).toBeVisible();
    await expect(authenticatedPage.getByRole("tab", { name: "### Subject" })).toBeVisible();
    await expect(authenticatedPage.getByRole("tab", { name: "### Style" })).toBeVisible();
    const frameGrid = authenticatedPage.getByLabel("Preview frame grid");
    await expect(frameGrid.locator("option")).toHaveCount(11);
    await expect(frameGrid.locator("option").first()).toHaveAttribute("value", "124");
    await expect(frameGrid.locator("option").last()).toHaveAttribute("value", "600");
  });

  test("rejects unsupported reference MIME types without uploading", async ({ authenticatedPage }) => {
    await mockStoryApi(authenticatedPage);
    await openWrite(authenticatedPage);
    await authenticatedPage.getByTestId("edit-prompt").click();
    await authenticatedPage.locator('input[type="file"]').setInputFiles({ name: "not-an-image.txt", mimeType: "text/plain", buffer: Buffer.from("no") });
    await expect(authenticatedPage.getByText("Use a JPEG, PNG, WebP, or GIF reference image.")).toBeVisible();
  });

  test("saves prompt context and queues a preview with a new seed", async ({ authenticatedPage }) => {
    await mockStoryApi(authenticatedPage);
    await openWrite(authenticatedPage);
    await authenticatedPage.getByTestId("edit-prompt").click();
    await authenticatedPage.getByRole("tab", { name: "### Action" }).click();
    await authenticatedPage.locator("#prompt-Action").fill("Walks toward the skyline");
    const saveRequest = authenticatedPage.waitForRequest((request) => request.url().endsWith(`/api/v1/shots/${shot.id}`) && request.method() === "PUT");
    await authenticatedPage.getByRole("button", { name: "Save prompt" }).click();
    await saveRequest;
    await expect(authenticatedPage.getByRole("button", { name: "Regenerate preview" })).toBeVisible();
    const generationRequest = authenticatedPage.waitForRequest((request) => request.url().endsWith(`/api/v1/shots/${shot.id}/generate`) && request.method() === "POST");
    await authenticatedPage.getByRole("button", { name: "Regenerate preview" }).click();
    const body = (await generationRequest).postDataJSON();
    expect(body.quality).toBe("preview");
    expect(body.steps).toBe(4);
    expect(body.height).toBe(480);
    expect([124, 141, 209, 226, 243, 260, 277, 294, 362, 480, 600]).toContain(body.frame_grid);
    expect(body.seed).not.toBe(42);
  });
});
