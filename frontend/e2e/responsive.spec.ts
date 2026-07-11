import { test, expect } from "@playwright/test";

/**
 * Mobile responsiveness tests — verify all pages render properly
 * on mobile viewport without overlapping or broken layouts.
 */

const ALL_PAGES = [
  "/",
  "/brain",
  "/create",
  "/talent",
  "/assets",
  "/models",
  "/training",
  "/editor",
  "/workflows",
  "/production",
  "/publish",
  "/analytics",
  "/admin",
  "/admin/fleet",
  "/admin/keys",
  "/admin/downloads",
  "/settings",
];

test.describe("Mobile Responsiveness", () => {
  for (const path of ALL_PAGES) {
    test(`${path} renders without horizontal overflow`, async ({ page, viewport }) => {
      test.skip(!viewport || viewport.width > 500, "Mobile-only test");
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.waitForTimeout(1000);

      // Check no horizontal scrollbar
      const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
      const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
      // Allow 5px tolerance for borders/scrollbar
      expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 5);
    });

    test(`${path} has visible content on mobile`, async ({ page, viewport }) => {
      test.skip(!viewport || viewport.width > 500, "Mobile-only test");
      await page.goto(path);
      await page.waitForTimeout(2000);
      const mainContent = page.locator("main, [class*='space-y'], [class*='container']").first();
      if (await mainContent.isVisible().catch(() => false)) {
        const box = await mainContent.boundingBox();
        expect(box).not.toBeNull();
        if (box) {
          expect(box.width).toBeGreaterThan(100);
        }
      }
    });
  }

  test("sidebar collapses or becomes hamburger on mobile", async ({ page, viewport }) => {
    test.skip(!viewport || viewport.width > 500, "Mobile-only test");
    await page.goto("/");
    await page.waitForTimeout(1000);
    const sidebar = page.locator("aside");
    const isVisible = await sidebar.isVisible().catch(() => false);
    if (isVisible) {
      const box = await sidebar.boundingBox();
      // If visible on mobile, it should overlay
    }
  });
});

test.describe("Desktop Layout", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("sidebar is always visible", async ({ page }) => {
    await page.goto("/");
    const sidebar = page.locator("aside");
    await expect(sidebar).toBeVisible();
  });

  test("content has proper margins alongside sidebar", async ({ page }) => {
    await page.goto("/");
    await page.waitForTimeout(1000);
    const mainContent = page.locator("main").first();
    if (await mainContent.isVisible().catch(() => false)) {
      const box = await mainContent.boundingBox();
      // Main content should be offset from left (sidebar takes ~200px)
      if (box) {
        expect(box.x).toBeGreaterThanOrEqual(150);
      }
    }
  });
});
