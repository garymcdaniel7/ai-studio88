import { expect, test } from "./fixtures/authenticated";

test.describe("authenticated browser context", () => {
  test("replays the worker state across refresh and canonical deep links", async ({ authenticatedPage }) => {
    await authenticatedPage.goto("/make");
    await expect(authenticatedPage).toHaveURL(/\/make$/);
    await authenticatedPage.reload();
    await expect(authenticatedPage).not.toHaveURL(/\/login/);

    await authenticatedPage.goto("/write");
    await expect(authenticatedPage).toHaveURL(/\/write$/);
    await authenticatedPage.reload();
    await expect(authenticatedPage).not.toHaveURL(/\/login/);
  });

  test("mock mode exposes only the loopback test session cookie", async ({ authenticatedContext }) => {
    test.skip(process.env.PLAYWRIGHT_AUTH_MODE !== "mock", "Mock-only assertion; local-password mode uses the local auth emulator");
    const cookies = await authenticatedContext.cookies();
    const session = cookies.find((cookie) => cookie.name === "ai_studio_playwright_session");
    expect(session?.value).toBe("authenticated");
    expect(session?.secure).toBe(false);
  });
});
