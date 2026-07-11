import re
from playwright.sync_api import Playwright, sync_playwright, expect


def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(channel="chrome", headless=False)
    context = browser.new_context(locale="es-ES", viewport={"width":1920,"height":1080})
    page = context.new_page()
    page.goto("https://ai-studio99.vercel.app/")
    page.get_by_text("AI STUDIO", exact=True).click()
    page.locator("div").filter(has_text="⌘K").nth(3).click()
    page.get_by_text("$0.01").click()
    page.locator("div").filter(has_text="GPU Spend (today)$0.01Month: $").nth(5).click()
    page.get_by_role("link", name="🎨 Create Image").click()
    page.get_by_role("button", name="Voice & Music").click()
    page.get_by_role("button", name="Voice & Music").click()
    page.get_by_role("button", name="Video Generation").click()
    page.get_by_role("button", name="Image Generation").click()
    page.get_by_role("button", name="Video Generation").click()
    page.get_by_role("button", name="Voice & Music").click()
    page.get_by_role("button", name="Full Production").click()
    page.get_by_role("link", name="Open Video Editor").click()
    page.get_by_role("button", name="Quick Edit").click()
    page.get_by_role("spinbutton").first.click()
    page.get_by_role("slider").fill("2")
    page.locator("div").filter(has_text=re.compile(r"^Resolution$")).click()
    page.get_by_text("TransformsTrimStart (s)End (s").click()
    page.locator("div").filter(has_text=re.compile(r"^Text Overlay$")).click()
    page.get_by_role("combobox").nth(1).select_option("vintage")
    page.get_by_role("combobox").nth(2).select_option("Helvetica")
    page.get_by_role("textbox", name="Add text...").click()
    page.get_by_role("link", name="Quick Create").click()
    expect(page.get_by_role("heading", name="Create")).to_be_visible()
    page.get_by_role("heading", name="Create").click()
    page.get_by_text("⌘K3Quick Create").click()
    page.get_by_text("⌘K3Quick Create").click()
    page.get_by_text("Quick GenerateDescribe what").click()
    page.get_by_role("button", name="Fast Draft Instant Lightning-").click()
    expect(page.get_by_role("main")).to_be_visible()
    expect(page.locator("div").filter(has_text="Quick GenerateDescribe what").nth(3)).to_be_visible()
    page.get_by_role("link", name="Home").click()
    expect(page.get_by_role("main")).to_be_visible()
    page.get_by_role("main").click()
    expect(page.get_by_text("HomeBrainCreateCreateEditorWorkflowsTrainingManageTalentAssetsModelsOperateProdu")).to_be_visible()

    # ---------------------
    context.close()
    browser.close()


with sync_playwright() as playwright:
    run(playwright)
