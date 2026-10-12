import time
import pytest
from playwright.sync_api import expect
from conftest import BASE_URL, TEST_PASSWORD

@pytest.mark.auth
def test_login_fields_are_blank(page):
    page.goto(BASE_URL)
    expect(page.get_by_label("아이디")).to_have_value("")
    expect(page.get_by_label("비밀번호")).to_have_value("")

@pytest.mark.auth
def test_invalid_login_message(page):
    page.goto(BASE_URL)
    page.get_by_label("아이디").fill("invalid")
    page.get_by_label("비밀번호").fill("invalid")
    page.get_by_role("button", name="로그인").click()
    expect(page.get_by_text("아이디 또는 비밀번호가 올바르지 않습니다.")).to_be_visible()

@pytest.mark.parametrize("user,visible,hidden", [
    ("admin", ["관리 맵","설비 등록","점검","미비사항","관리자"], []),
    ("registrar", ["관리 맵","설비 등록"], ["점검","미비사항","관리자"]),
    ("inspector", ["관리 맵","점검","미비사항"], ["설비 등록","관리자"]),
    ("viewer", ["관리 맵"], ["설비 등록","점검","미비사항","관리자"]),
])
@pytest.mark.rbac
def test_role_based_menu(page, login, user, visible, hidden):
    login(page, user)
    for text in visible:
        expect(page.get_by_text(text, exact=True).first).to_be_visible()
    for text in hidden:
        expect(page.get_by_text(text, exact=True)).to_have_count(0)

@pytest.mark.auth
def test_logout_returns_to_blank_login(page, login):
    login(page, "admin")
    page.get_by_role("button", name="로그아웃").click()
    expect(page.get_by_role("button", name="로그인")).to_be_visible()
    expect(page.get_by_label("아이디")).to_have_value("")

@pytest.mark.auth
def test_inactivity_timeout(page, login):
    timeout = int(__import__("os").getenv("SESSION_TIMEOUT_SECONDS", "1800"))
    if timeout > 10:
        pytest.skip("SESSION_TIMEOUT_SECONDS=2로 실행할 때 활성화되는 타임아웃 테스트")
    login(page, "admin")
    page.wait_for_timeout((timeout + 1) * 1000)
    page.reload()
    expect(page.get_by_role("button", name="로그인")).to_be_visible()
