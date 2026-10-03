/**
 * AI Studio Page Objects for Playwright UAT.
 *
 * Every page in the app gets a class with:
 *  - `goto()` — navigate to the page
 *  - `expectReady()` — assert the page rendered (heading visible, no crash)
 *  - Convenience locators / actions for critical UI elements
 *
 * Auth-optional helpers live in `AuthPage` (login, trackRequests).
 */

import { expect, Locator, Page, test } from "@playwright/test";

/* ───────── helpers ───────── */

/** Attach error/failure listeners to a page. Call in beforeEach or the test body. */
export function trackErrors(page: Page) {
  (page as any).__consoleErrors ??= [];
  (page as any).__failedRequests ??= [];
  page.on("console", (m) => {
    if (m.type() === "error") (page as any).__consoleErrors.push(m.text());
  });
  page.on("requestfailed", (r) => {
    const err = r.failure()?.errorText || "";
    if (err.includes("ERR_ABORTED")) return; // benign RSC prefetch abort
    (page as any).__failedRequests.push(`${r.method()} ${r.url()} :: ${err}`);
  });
}

export function getErrors(page: Page): string[] {
  return (page as any).__consoleErrors ?? [];
}
export function getFailedRequests(page: Page): string[] {
  return (page as any).__failedRequests ?? [];
}

/** Return a function that filters out analytics/fonts/favicon noise. */
export function relevantFailures(page: Page): string[] {
  return getFailedRequests(page).filter(
    (r) => !/analytics|fonts|gtm|favicon/.test(r)
  );
}

/* ───────── Auth Page ───────── */

export class AuthPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/login");
  }

  async expectReady() {
    await expect(this.page.locator("body")).toContainText(
      /Welcome back|Sign in|Continue with Google|you@example.com/i
    );
  }

  async login(email: string, password: string) {
    await this.goto();
    await this.page.getByPlaceholder("you@example.com").fill(email);
    await this.page.getByPlaceholder("At least 6 characters").fill(password);
    await this.page.getByRole("button", { name: /sign in/i }).click();
    await this.page.waitForURL(
      (u) => !u.pathname.startsWith("/login"),
      { timeout: 25000 }
    );
  }

  async logout() {
    const btn = this.page.getByRole("button", {
      name: /log out|sign out|logout/i,
    }).first();
    if (await btn.isVisible().catch(() => false)) {
      await btn.click();
      await this.page.waitForURL(
        (u) => u.pathname.includes("login"),
        { timeout: 15000 }
      );
    }
  }
}

/* ───────── Home (Landing) ───────── */

export class HomePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/");
  }

  async expectReady() {
    await expect(this.page.locator("body")).toContainText(
      /Your AITalent Agency|AI Studio|Get Started/i,
      { timeout: 15000 }
    );
  }
}

/* ───────── Create / Studio ───────── */

export class CreatePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/create");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  /** Fill the prompt textarea/input. */
  async fillPrompt(text: string) {
    const input = this.page
      .locator("textarea, input[placeholder*='prompt'], input[placeholder*='Describe']")
      .first();
    await input.fill(text);
  }

  /** Return the Generate button locator. */
  generateButton(): Locator {
    return this.page
      .locator("button:has-text('Generate'), button:has-text('GPU Offline')")
      .first();
  }

  /** Select a model from the model dropdown if visible. */
  async selectModel(modelLabel: string) {
    const select = this.page.locator("select, [role='combobox']").first();
    if (await select.isVisible().catch(() => false)) {
      await select.selectOption({ label: modelLabel });
    }
  }

  /** Switch tab (Image / Video / Audio / Voice / Production). */
  async switchTab(tabName: string) {
    const tab = this.page
      .locator(`button:has-text('${tabName}')`)
      .first();
    if (await tab.isVisible().catch(() => false)) {
      await tab.click();
      await this.page.waitForTimeout(300);
    }
  }

  async expectNoCrash() {
    const body = await this.page.textContent("body");
    expect(body?.length).toBeGreaterThan(50);
  }
}

/* ───────── Talent ───────── */

export class TalentPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/talent");
  }

  async expectReady() {
    await expect(this.page.locator("h1", { hasText: "Talent" })).toBeVisible({
      timeout: 15000,
    });
  }

  async clickNewTalent() {
    await this.page.locator("button:has-text('New Talent')").click();
  }

  /** Return visible talent cards. */
  talentCards() {
    return this.page.locator("[class*='rounded-xl'], [class*='card'], article");
  }

  async clickFirstTalent() {
    const card = this.talentCards().first();
    if (await card.isVisible()) {
      await card.click();
    }
  }

  async clickTrainLora() {
    const btn = this.page.locator("button:has-text('Train LoRA')");
    if (await btn.isVisible()) {
      await btn.click();
      await this.page.waitForURL("**/training**", { timeout: 8000 });
    }
  }
}

/* ───────── Publish / Schedule ───────── */

export class PublishPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/publish");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  socialConnections() {
    return this.page.locator("button:has-text('Connect'), button:has-text('Link')");
  }

  publishButton() {
    return this.page
      .locator(
        "button:has-text('Publish'), button:has-text('Schedule'), button:has-text('Post')"
      )
      .first();
  }
}

/* ───────── Settings ───────── */

export class SettingsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/settings");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async switchTab(tabName: string) {
    const tab = this.page
      .getByRole("button", { name: new RegExp(tabName, "i") })
      .first();
    if (await tab.isVisible().catch(() => false)) {
      await tab.click();
      await this.page.waitForTimeout(1000);
    }
  }

  /** Check the page shows selector/primitives (migrated selects). */
  async expectSelectsRendered() {
    const text = await this.page.locator("body").innerText();
    const hasRecipe = /recipe|auto \(ai picks best\)|preferred recipe/i.test(
      text
    );
    const hasFormat = /format|square \(1024x1024\)|landscape|portrait/i.test(
      text
    );
    return hasRecipe || hasFormat;
  }
}

/* ───────── Editor ───────── */

export class EditorPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/editor");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

/* ───────── Assets ───────── */

export class AssetsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/assets");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectNoError() {
    const text = await this.page.locator("body").innerText();
    expect(/error|something went wrong/i.test(text)).toBe(false);
  }
}

/* ───────── Models / Registry ───────── */

export class ModelsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/models");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

/* ───────── Projects ───────── */

export class ProjectsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/projects");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

/* ───────── Training ───────── */

export class TrainingPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/training");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

/* ───────── Workflows ───────── */

export class WorkflowsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/workflows");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

/* ───────── Story ───────── */

export class StoryPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/story");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

/* ───────── Brain Chat ───────── */

export class BrainPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/brain");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  /** Type a message into the chat input. */
  async typeMessage(text: string) {
    const input = this.page
      .locator(
        "textarea, input[placeholder*='message'], input[placeholder*='Ask']"
      )
      .first();
    if (await input.isVisible()) {
      await input.fill(text);
    }
  }

  sendButton() {
    return this.page
      .locator("button:has-text('Send'), button[type='submit']")
      .first();
  }
}

/* ───────── Analytics ───────── */

export class AnalyticsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/analytics");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectHasData() {
    const text = await this.page.locator("body").innerText();
    const hasAnalytics =
      /Total|Cost|Jobs|Analytics|Usage|Generation/i.test(text);
    expect(hasAnalytics).toBeTruthy();
  }
}

/* ───────── Production ───────── */

export class ProductionPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/production");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectShowsStatus() {
    const text = await this.page.locator("body").innerText();
    const hasStatus =
      /Worker|Production|Status|Queue|Job|Running/i.test(text);
    expect(hasStatus).toBeTruthy();
  }
}

/* ───────── Admin Pages ───────── */

export class AdminPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectShowsServices() {
    const text = await this.page.locator("body").innerText();
    const hasServices =
      /Vast|Backblaze|Supabase|ComfyUI|Ollama|ElevenLabs|Service|Connection/i.test(
        text
      );
    expect(hasServices).toBeTruthy();
  }
}

export class AdminFleetPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/fleet");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectShowsFleet() {
    const text = await this.page.locator("body").innerText();
    const hasFleet =
      /Worker|GPU|Instance|Fleet|No workers|Launch/i.test(text);
    expect(hasFleet).toBeTruthy();
  }
}

export class AdminFleetPlannerPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/fleet-planner");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

export class AdminKeysPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/keys");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectHasKeySection() {
    const text = await this.page.locator("body").innerText();
    const hasKeys = /API|Key|Secret|Token/i.test(text);
    expect(hasKeys).toBeTruthy();
  }
}

export class AdminConnectionsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/connections");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectNoError() {
    const text = await this.page.locator("body").innerText();
    expect(/error|something went wrong/i.test(text)).toBe(false);
  }
}

export class AdminHealthPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/health");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

export class AdminKnowledgePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/knowledge");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

export class AdminObjectsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/objects");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

export class AdminIsePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/ise");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}

export class AdminDownloadsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/admin/downloads");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }

  async expectHasDownloads() {
    const text = await this.page.locator("body").innerText();
    const hasDownloads = /Download|Model|Cache|Available/i.test(text);
    expect(hasDownloads).toBeTruthy();
  }
}

/* ───────── Public pages ───────── */

export class PricingPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/pricing");
  }

  async expectReady() {
    await expect(this.page.locator("body")).toContainText(/Pricing/i, {
      timeout: 15000,
    });
  }
}

export class PrivacyPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/privacy");
  }

  async expectReady() {
    await expect(this.page.locator("body")).toContainText(/Privacy Policy/i, {
      timeout: 15000,
    });
  }
}

export class TermsPage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/terms");
  }

  async expectReady() {
    await expect(this.page.locator("body")).toContainText(
      /Terms of Service/i,
      { timeout: 15000 }
    );
  }
}

/* ───────── Title Sequence ───────── */

export class TitleSequencePage {
  constructor(private page: Page) {}

  async goto() {
    await this.page.goto("/title-sequence");
  }

  async expectReady() {
    await expect(this.page.locator("h1").first()).toBeVisible({
      timeout: 15000,
    });
  }
}