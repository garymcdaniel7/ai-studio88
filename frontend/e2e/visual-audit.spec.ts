/**
 * Visual Audit — Captures screenshots of every page for Red Team review.
 *
 * Run: cd frontend && npx playwright test scripts/visual-audit.ts --project=desktop
 *
 * Output: frontend/visual-audit/ (one PNG per page)
 *
 * Then feed the screenshots to @redteam for visual UX analysis:
 * "Review these screenshots. What looks broken, misaligned, or confusing?"
 */

import { test } from "@playwright/test";
import { mkdirSync } from "fs";

const OUTPUT_DIR = "visual-audit";

const PAGES = [
  { path: "/", name: "home" },
  { path: "/brain", name: "brain" },
  { path: "/create", name: "create" },
  { path: "/talent", name: "talent" },
  { path: "/assets", name: "assets" },
  { path: "/models", name: "models" },
  { path: "/training", name: "training" },
  { path: "/projects", name: "projects" },
  { path: "/publish", name: "publish" },
  { path: "/admin", name: "admin-dashboard" },
  { path: "/admin/fleet", name: "admin-fleet" },
  { path: "/settings", name: "settings" },
  { path: "/login", name: "login" },
];

test.describe("Visual Audit — Screenshot All Pages", () => {
  test.beforeAll(() => {
    mkdirSync(OUTPUT_DIR, { recursive: true });
  });

  for (const page of PAGES) {
    test(`screenshot ${page.name} (${page.path})`, async ({ page: p }) => {
      // Set a cookie to bypass auth middleware
      await p.context().addCookies([
        { name: "ai_studio_auth", value: "visual_audit", domain: "localhost", path: "/" },
      ]);

      await p.goto(page.path, { waitUntil: "networkidle", timeout: 15000 }).catch(() => {
        // Fall back to domcontentloaded if networkidle times out
        return p.goto(page.path, { waitUntil: "domcontentloaded", timeout: 10000 });
      });

      // Wait for content to render
      await p.waitForTimeout(2000);

      // Full page screenshot
      await p.screenshot({
        path: `${OUTPUT_DIR}/${page.name}.png`,
        fullPage: true,
      });
    });
  }
});
