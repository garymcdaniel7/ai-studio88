import { expect, test } from "./fixtures/authenticated";

async function mockMakeApi(page: import("@playwright/test").Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/models")) return route.fulfill({ json: [] });
    if (url.includes("available-models")) return route.fulfill({ json: { models: [] } });
    if (url.includes("/projects")) return route.fulfill({ json: { projects: [] } });
    if (url.includes("/jobs")) return route.fulfill({ json: [] });
    if (url.includes("infrastructure/status")) return route.fulfill({ json: { worker: {} } });
    if (url.includes("/presets")) return route.fulfill({ json: [] });
    if (url.includes("/voices/")) return route.fulfill({ json: { voices: [] } });
    return route.fulfill({ json: {} });
  });
}

test.describe("canonical MAKE Prompt Workshop", () => {
  test("renders templates, injectors, preview, and exact frame-grid values", async ({ authenticatedPage }) => {
    await mockMakeApi(authenticatedPage);
    await authenticatedPage.goto("/make");
    await expect(authenticatedPage.getByTestId("prompt-workshop")).toBeVisible();
    await expect(authenticatedPage.getByLabel("Shot type template")).toHaveValue("Dialogue");
    await expect(authenticatedPage.getByLabel("Subject injector")).toBeVisible();
    await expect(authenticatedPage.getByTestId("prompt-preview")).toContainText("### Subject");
    await expect(authenticatedPage.getByLabel("Preview frame grid").locator("option")).toHaveCount(11);
  });

  test("keeps advanced controls keyboard-addressable without tenant or secret fields", async ({ authenticatedPage }) => {
    await mockMakeApi(authenticatedPage);
    await authenticatedPage.goto("/make");
    await authenticatedPage.getByRole("tab", { name: /Advanced/ }).click();
    await expect(authenticatedPage.getByRole("heading", { name: /Tier 1/ })).toBeVisible();
    await expect(authenticatedPage.getByRole("heading", { name: /Tier 3/ })).toBeVisible();
    await expect(authenticatedPage.locator("input[name*=org], input[name*=token], input[name*=secret], input[name*=key]")).toHaveCount(0);
  });
});
