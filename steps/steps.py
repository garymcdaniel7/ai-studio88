from behave import given, then
from playwright.sync_api import expect
from page_objects import AIStudioSelectors

@given('the user opens the AI Studio website')
def step_impl(context):
    context.page.goto("https://ai-studio99.vercel.app/")

@then('there should be exactly {count:d} element that matches "{element_name}" with identifier "{identifier}"')
def step_impl(context, count, element_name, identifier):
    # We use the identifier provided in the Gherkin step
    # or resolve it via page_objects if needed
    selector = AIStudioSelectors.get_selector(element_name) or identifier
    elements = context.page.locator(selector)
    expect(elements).to_have_count(count)