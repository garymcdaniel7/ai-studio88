/**
 * Red Team Interactive Audit — Headed Playwright browser for live page inspection.
 *
 * This script opens a VISIBLE browser window, navigates to every page,
 * captures screenshots, clicks interactive elements, and reports findings.
 *
 * Usage:
 *   HEADED MODE (watch it happen):
 *     cd frontend && npx playwright test ../scripts/redteam-interactive-audit.ts --headed --project=desktop --workers=1
 *
 *   HEADLESS MODE (just capture):
 *     cd frontend && npx playwright test ../scripts/redteam-interactive-audit.ts --project=desktop --workers=1
 *
 *   SLOW MOTION (watch step by step, 500ms delay between actions):
 *     cd frontend && SLOW_MO=500 npx playwright test ../scripts/redteam-interactive-audit.ts --headed --project=desktop --workers=1
 *
 * Output:
 *   - frontend/redteam-audit/*.png — Full page screenshots
 *   - frontend/redteam-audit/interactions/*.png — Screenshots after button clicks
 *   - frontend/redteam-audit/REDUNDANCY_REPORT.md — Auto-generated findings
 *
 * Prerequisites:
 *   - Frontend running on localhost:3000 (npm run dev)
 *   - Backend running on localhost:8000 (uvicorn)
 */

import { test, expect, Page } from "@playwright/test";
import { mkdirSync, writeFileSync, existsSync } from "fs";
import { join } from "path";

// --- Configuration ---

const OUTPUT_DIR = "redteam-audit";
const INTERACTIONS_DIR = join(OUTPUT_DIR, "interactions");
const SLOW_MO = parseInt(process.env.SLOW_MO || "0", 10);

// All 22 routes in the application
const ALL_PAGES = [
  { path: "/", name: "home", category: "main" },
  { path: "/brain", name: "brain", category: "main" },
  { path: "/create", name: "create", category: "main" },
  { path: "/talent", name: "talent", category: "main" },
  { path: "/assets", name: "assets", category: "main" },
  { path: "/models", name: "models", category: "main" },
  { path: "/training", name: "training", category: "main" },
  { path: "/projects", name: "projects", category: "main" },
  { path: "/publish", name: "publish", category: "main" },
  { path: "/analytics", name: "analytics", category: "main" },
  { path: "/editor", name: "editor", category: "main" },
  { path: "/workflows", name: "workflows", category: "main" },
  { path: "/production", name: "production", category: "main" },
  { path: "/settings", name: "settings", category: "main" },
  { path: "/login", name: "login", category: "auth" },
  { path: "/admin", name: "admin-dashboard", category: "admin" },
  { path: "/admin/fleet", name: "admin-fleet", category: "admin" },
  { path: "/admin/downloads", name: "admin-downloads", category: "admin" },
  { path: "/admin/health", name: "admin-health", category: "admin" },
  { path: "/admin/ise", name: "admin-ise", category: "admin" },
  { path: "/admin/keys", name: "admin-keys", category: "admin" },
  { path: "/admin/knowledge", name: "admin-knowledge", category: "admin" },
];

// --- Redundancy Detection Data ---

interface PageAuditData {
  name: string;
  path: string;
  category: string;
  h1Text: string;
  buttons: string[];
  links: string[];
  tabs: string[];
  forms: string[];
  apiCalls: string[];
  hasGenerateButton: boolean;
  hasLaunchWorkerButton: boolean;
  hasCostDisplay: boolean;
  hasModelSelector: boolean;
  hasServiceStatus: boolean;
  hasJobQueue: boolean;
}

const auditResults: PageAuditData[] = [];
const findings: string[] = [];

// --- Helper Functions ---

async function delay(ms: number) {
  if (SLOW_MO > 0) {
    await new Promise((r) => setTimeout(r, ms));
  }
}

async function navigateSafely(page: Page, path: string): Promise<boolean> {
  try {
    // Set auth cookie to bypass login redirect
    await page.context().addCookies([
      { name: "ai_studio_auth", value: "redteam_audit", domain: "localhost", path: "/" },
    ]);

    await page.goto(path, { waitUntil: "domcontentloaded", timeout: 15000 });
    await page.waitForTimeout(2000); // Let React hydrate
    return true;
  } catch (e) {
    console.log(`  ⚠ Failed to navigate to ${path}: ${(e as Error).message}`);
    return false;
  }
}

async function auditPage(page: Page, pageInfo: typeof ALL_PAGES[0]): Promise<PageAuditData> {
  // Gather page data
  const h1Text = await page.locator("h1").first().textContent().catch(() => "(no h1)") || "(no h1)";

  // All visible buttons
  const buttons = await page.locator("button:visible").allTextContents();
  const uniqueButtons = [...new Set(buttons.map((b) => b.trim()).filter(Boolean))];

  // All navigation links
  const links = await page.locator("a[href]:visible").evaluateAll((els) =>
    els.map((el) => ({ text: el.textContent?.trim() || "", href: el.getAttribute("href") || "" }))
      .filter((l) => l.href.startsWith("/") && l.text.length > 0)
      .map((l) => `${l.text} → ${l.href}`)
  );

  // Tabs (common pattern: role=tab or data-tab or tab-like buttons)
  const tabs = await page.locator('[role="tab"], [data-tab], button[class*="tab"]').allTextContents();

  // Forms
  const forms = await page.locator("form, input, textarea, select").evaluateAll((els) =>
    els.map((el) => el.tagName.toLowerCase() + (el.getAttribute("placeholder") ? `[${el.getAttribute("placeholder")}]` : ""))
  );

  // Detect key patterns
  const pageContent = await page.content();
  const hasGenerateButton = uniqueButtons.some((b) => /generate|create image/i.test(b));
  const hasLaunchWorkerButton = uniqueButtons.some((b) => /launch|start worker/i.test(b));
  const hasCostDisplay = pageContent.includes("$/hr") || pageContent.includes("cost") || pageContent.includes("spend");
  const hasModelSelector = pageContent.includes("model") && (pageContent.includes("select") || pageContent.includes("selector"));
  const hasServiceStatus = pageContent.includes("healthy") || pageContent.includes("status") || pageContent.includes("online");
  const hasJobQueue = pageContent.includes("queue") || pageContent.includes("running") || pageContent.includes("completed");

  // Collect API calls from page source
  const apiCalls = await page.evaluate(() => {
    const scripts = document.querySelectorAll("script");
    const apiPatterns: string[] = [];
    scripts.forEach((s) => {
      const matches = s.textContent?.match(/fetch\(["`']([^"`']+)["`']/g) || [];
      apiPatterns.push(...matches.map((m) => m.replace(/fetch\(["`']|["`']/g, "")));
    });
    return apiPatterns;
  });

  return {
    name: pageInfo.name,
    path: pageInfo.path,
    category: pageInfo.category,
    h1Text: h1Text.trim(),
    buttons: uniqueButtons,
    links: links.slice(0, 20),
    tabs: tabs.map((t) => t.trim()).filter(Boolean),
    forms: forms.slice(0, 10),
    apiCalls,
    hasGenerateButton,
    hasLaunchWorkerButton,
    hasCostDisplay,
    hasModelSelector,
    hasServiceStatus,
    hasJobQueue,
  };
}

async function clickAllButtons(page: Page, pageName: string) {
  // Find all clickable buttons that don't navigate away or submit forms
  const safeButtons = await page.locator(
    'button:visible:not([type="submit"]):not([data-destructive])'
  ).all();

  let clickCount = 0;
  for (const button of safeButtons.slice(0, 8)) {
    // Max 8 buttons per page
    try {
      const text = await button.textContent();
      const trimmed = (text || "").trim().slice(0, 30);

      // Skip dangerous buttons
      if (/delete|remove|destroy|stop|cancel|logout|sign out/i.test(trimmed)) continue;
      // Skip already-active tabs
      if (await button.getAttribute("aria-selected") === "true") continue;

      await delay(SLOW_MO);
      await button.click({ timeout: 3000 });
      await page.waitForTimeout(800);

      // Screenshot after click
      clickCount++;
      await page.screenshot({
        path: join(INTERACTIONS_DIR, `${pageName}-click${clickCount}-${trimmed.replace(/[^a-zA-Z0-9]/g, "_")}.png`),
        fullPage: true,
      });
    } catch {
      // Button might be disabled or cause navigation — skip
    }
  }
  return clickCount;
}

function detectRedundancies(data: PageAuditData[]) {
  // Pattern 1: Multiple pages with "Launch Worker" button
  const launchWorkerPages = data.filter((d) => d.hasLaunchWorkerButton);
  if (launchWorkerPages.length > 1) {
    findings.push(
      `### P1 — "Launch Worker" button appears on ${launchWorkerPages.length} pages\n` +
      `**Pages:** ${launchWorkerPages.map((p) => p.path).join(", ")}\n` +
      `**Issue:** Users don't know which page is the "right" place to launch a GPU worker.\n` +
      `**Recommendation:** Keep only on /admin/fleet (or unified Super Admin). Other pages link to it.\n`
    );
  }

  // Pattern 2: Multiple pages showing service status
  const statusPages = data.filter((d) => d.hasServiceStatus);
  if (statusPages.length > 2) {
    findings.push(
      `### P2 — Service health status shown on ${statusPages.length} pages\n` +
      `**Pages:** ${statusPages.map((p) => p.path).join(", ")}\n` +
      `**Issue:** Status information scattered — no single source of truth.\n` +
      `**Recommendation:** Show detailed status only on /admin/health. Other pages show a compact indicator.\n`
    );
  }

  // Pattern 3: Multiple pages with cost display
  const costPages = data.filter((d) => d.hasCostDisplay);
  if (costPages.length > 2) {
    findings.push(
      `### P2 — Cost/spend data shown on ${costPages.length} pages\n` +
      `**Pages:** ${costPages.map((p) => p.path).join(", ")}\n` +
      `**Issue:** "Where do I find my GPU costs?" has too many answers.\n` +
      `**Recommendation:** /analytics is the authoritative cost page. Others show a single compact metric.\n`
    );
  }

  // Pattern 4: Job queue on multiple pages
  const jobPages = data.filter((d) => d.hasJobQueue);
  if (jobPages.length > 1) {
    findings.push(
      `### P2 — Job queue data on ${jobPages.length} pages\n` +
      `**Pages:** ${jobPages.map((p) => p.path).join(", ")}\n` +
      `**Issue:** Active jobs shown redundantly. User checks multiple places for same info.\n` +
      `**Recommendation:** /production (or /jobs) is the canonical job view. Home shows top 3 only.\n`
    );
  }

  // Pattern 5: Duplicate h1 text (identity confusion)
  const h1Map = new Map<string, PageAuditData[]>();
  for (const d of data) {
    if (d.h1Text === "(no h1)") continue;
    const existing = h1Map.get(d.h1Text) || [];
    existing.push(d);
    h1Map.set(d.h1Text, existing);
  }
  for (const [h1, pages] of h1Map) {
    if (pages.length > 1) {
      findings.push(
        `### P1 — Duplicate h1 "${h1}" on ${pages.length} pages\n` +
        `**Pages:** ${pages.map((p) => p.path).join(", ")}\n` +
        `**Issue:** Two pages with the same heading creates identity confusion.\n` +
        `**Recommendation:** Rename one or merge the pages.\n`
      );
    }
  }

  // Pattern 6: Admin sub-pages that are nearly identical
  const adminPages = data.filter((d) => d.category === "admin");
  const healthLike = adminPages.filter((d) => d.hasServiceStatus);
  if (healthLike.length > 1) {
    findings.push(
      `### P1 — ${healthLike.length} admin pages show service health\n` +
      `**Pages:** ${healthLike.map((p) => p.path).join(", ")}\n` +
      `**Issue:** Admin section has redundant health views.\n` +
      `**Recommendation:** Consolidate into single /admin health tab.\n`
    );
  }
}

function generateReport(data: PageAuditData[]) {
  let report = `# Red Team Interactive Audit Report\n\n`;
  report += `**Generated:** ${new Date().toISOString()}\n`;
  report += `**Pages audited:** ${data.length}\n`;
  report += `**Interactions captured:** See ${INTERACTIONS_DIR}/\n\n`;
  report += `---\n\n`;

  report += `## Page Inventory\n\n`;
  report += `| Page | h1 | Buttons | Tabs | Generate? | Workers? | Costs? | Status? |\n`;
  report += `|------|-----|---------|------|-----------|----------|--------|--------|\n`;
  for (const d of data) {
    report += `| ${d.path} | ${d.h1Text.slice(0, 25)} | ${d.buttons.length} | ${d.tabs.length} | ${d.hasGenerateButton ? "YES" : "-"} | ${d.hasLaunchWorkerButton ? "YES" : "-"} | ${d.hasCostDisplay ? "YES" : "-"} | ${d.hasServiceStatus ? "YES" : "-"} |\n`;
  }
  report += `\n`;

  report += `## Redundancy Findings\n\n`;
  if (findings.length === 0) {
    report += `No automated redundancies detected.\n\n`;
  } else {
    for (const f of findings) {
      report += f + `\n`;
    }
  }

  report += `## Button Inventory (per page)\n\n`;
  for (const d of data) {
    if (d.buttons.length > 0) {
      report += `### ${d.path}\n`;
      report += d.buttons.map((b) => `- ${b}`).join("\n") + "\n\n";
    }
  }

  report += `## Tab Inventory (per page)\n\n`;
  for (const d of data) {
    if (d.tabs.length > 0) {
      report += `### ${d.path}\n`;
      report += d.tabs.map((t) => `- ${t}`).join("\n") + "\n\n";
    }
  }

  return report;
}

// --- Test Suite ---

test.describe("Red Team Interactive Audit", () => {
  test.beforeAll(() => {
    mkdirSync(OUTPUT_DIR, { recursive: true });
    mkdirSync(INTERACTIONS_DIR, { recursive: true });
  });

  // Phase 1: Screenshot every page
  test("Phase 1 — Capture all pages", async ({ page }) => {
    test.setTimeout(300000); // 5 min for all pages

    for (const pageInfo of ALL_PAGES) {
      console.log(`\n📸 Capturing: ${pageInfo.name} (${pageInfo.path})`);

      const success = await navigateSafely(page, pageInfo.path);
      if (!success) continue;

      await delay(SLOW_MO);

      // Full page screenshot
      await page.screenshot({
        path: join(OUTPUT_DIR, `${pageInfo.name}.png`),
        fullPage: true,
      });

      // Audit the page structure
      const data = await auditPage(page, pageInfo);
      auditResults.push(data);

      console.log(`  ✓ ${data.h1Text} | ${data.buttons.length} buttons | ${data.tabs.length} tabs`);
    }
  });

  // Phase 2: Click interactions on key pages
  test("Phase 2 — Button interactions", async ({ page }) => {
    test.setTimeout(300000);

    const interactivePages = ALL_PAGES.filter((p) =>
      ["/create", "/admin", "/admin/fleet", "/brain", "/talent", "/training", "/production", "/settings"].includes(p.path)
    );

    for (const pageInfo of interactivePages) {
      console.log(`\n🖱 Interacting: ${pageInfo.name} (${pageInfo.path})`);

      const success = await navigateSafely(page, pageInfo.path);
      if (!success) continue;

      await delay(SLOW_MO);
      const clicks = await clickAllButtons(page, pageInfo.name);
      console.log(`  ✓ ${clicks} buttons clicked`);
    }
  });

  // Phase 3: Redundancy analysis + report
  test("Phase 3 — Redundancy analysis", async () => {
    // Run detection
    detectRedundancies(auditResults);

    // Generate markdown report
    const report = generateReport(auditResults);
    writeFileSync(join(OUTPUT_DIR, "REDUNDANCY_REPORT.md"), report);

    console.log(`\n═══════════════════════════════════════════════`);
    console.log(`  Red Team Audit Complete`);
    console.log(`  Screenshots: ${OUTPUT_DIR}/`);
    console.log(`  Interactions: ${INTERACTIONS_DIR}/`);
    console.log(`  Report: ${OUTPUT_DIR}/REDUNDANCY_REPORT.md`);
    console.log(`  Findings: ${findings.length} redundancies detected`);
    console.log(`═══════════════════════════════════════════════\n`);
  });
});
