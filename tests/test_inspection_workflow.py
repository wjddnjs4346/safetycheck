import pytest
from playwright.sync_api import expect
from conftest import PHOTO_PATH

@pytest.mark.inspections
def test_inspector_submits_defect_with_photo(page, login):
    login(page, "inspector")
    page.get_by_text("점검", exact=True).click()
    expect(page.get_by_text("QA 옥내소화전 점검", exact=True)).to_be_visible()
    radios = page.get_by_text("미비", exact=True)
    radios.first.click()
    page.get_by_label("미비 코멘트").first.fill("호스 상태 보완 필요")
    page.get_by_label("점검 증빙사진").set_input_files(PHOTO_PATH)
    page.get_by_role("button", name="최종 제출").click()
    expect(page.get_by_text("점검이 제출되었습니다.")).to_be_visible()

@pytest.mark.inspections
def test_defect_requires_comment(page, login):
    login(page, "inspector")
    page.get_by_text("점검", exact=True).click()
    page.get_by_text("미비", exact=True).first.click()
    page.get_by_role("button", name="최종 제출").click()
    expect(page.get_by_text("미비항목에는 코멘트를 입력하세요.")).to_be_visible()

@pytest.mark.inspections
def test_defect_action_before_and_after_photos(page, login):
    login(page, "inspector")
    page.get_by_text("점검", exact=True).click()
    page.get_by_text("미비", exact=True).first.click()
    page.get_by_label("미비 코멘트").first.fill("조치 사진 검증")
    page.get_by_role("button", name="최종 제출").click()
    page.get_by_text("미비사항", exact=True).click()
    page.get_by_text("QA 옥내소화전", exact=False).click()
    page.get_by_label("조치내용").fill("조치 완료")
    page.get_by_label("조치 전 사진").set_input_files(PHOTO_PATH)
    page.get_by_label("조치 후 사진").set_input_files(PHOTO_PATH)
    page.get_by_role("button", name="조치완료").click()
    expect(page.get_by_text("현재 상태:", exact=False)).to_be_visible()
