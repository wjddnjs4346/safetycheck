import pytest
from playwright.sync_api import expect
from conftest import PHOTO_PATH

@pytest.mark.assets
def test_registrar_can_open_registration(page, login):
    login(page, "registrar")
    page.get_by_text("설비 등록", exact=True).click()
    expect(page.get_by_text("설비 위치 등록", exact=True)).to_be_visible()
    expect(page.get_by_label("관리번호*")).to_be_visible()

@pytest.mark.assets
def test_admin_edits_asset_and_uploads_photo(admin_page):
    page = admin_page
    page.get_by_label("설비 상세").select_option(label="QA-HYD-001 · QA 옥내소화전 · 미점검")
    page.get_by_role("button", name="설비 수정").click()
    expect(page.get_by_text("설비 정보 및 위치 수정", exact=True)).to_be_visible()
    page.get_by_label("세부 위치").fill("수정된 QA 위치")
    page.get_by_label("설비 사진").set_input_files(PHOTO_PATH)
    page.get_by_label("수정 사유*").fill("Playwright 수정 검증")
    page.get_by_role("button", name="수정 저장").click()
    expect(page.get_by_text("설비를 수정했습니다.")).to_be_visible()

@pytest.mark.assets
def test_admin_delete_and_restore_asset(admin_page):
    page = admin_page
    page.get_by_role("button", name="설비 삭제").click()
    page.get_by_label("삭제 사유").fill("Playwright 삭제 검증")
    page.get_by_role("button", name="삭제 확정").click()
    page.get_by_text("관리자", exact=True).click()
    page.get_by_role("tab", name="삭제 설비").click()
    expect(page.get_by_text("QA-HYD-001", exact=False)).to_be_visible()
    page.get_by_role("button", name="복구").click()
    expect(page.get_by_text("QA-HYD-001", exact=False)).to_have_count(0)

@pytest.mark.assets
def test_viewer_has_no_mutating_asset_actions(page, login):
    login(page, "viewer")
    expect(page.get_by_role("button", name="설비 수정")).to_have_count(0)
    expect(page.get_by_role("button", name="설비 삭제")).to_have_count(0)
