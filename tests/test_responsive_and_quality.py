import pytest
from playwright.sync_api import expect

VIEWPORTS = [(1440,900),(1280,720),(1180,820),(820,1180)]

@pytest.mark.responsive
@pytest.mark.parametrize("width,height", VIEWPORTS)
def test_no_horizontal_document_overflow(page, login, width, height):
    page.set_viewport_size({"width":width,"height":height})
    login(page,"viewer")
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
    assert not overflow

@pytest.mark.responsive
def test_keyboard_login(page):
    page.goto(__import__('conftest').BASE_URL)
    page.get_by_label("아이디").focus()
    page.keyboard.type("viewer")
    page.keyboard.press("Tab")
    page.keyboard.type(__import__('conftest').TEST_PASSWORD)
    page.keyboard.press("Enter")
    expect(page.get_by_text("안전설비 관리 맵", exact=True).last).to_be_visible()

@pytest.mark.responsive
def test_no_uncaught_page_or_console_errors(page, login):
    errors=[]
    page.on("pageerror",lambda exc: errors.append(str(exc)))
    page.on("console",lambda msg: errors.append(msg.text) if msg.type=="error" else None)
    login(page,"admin")
    page.wait_for_timeout(1000)
    assert not errors
