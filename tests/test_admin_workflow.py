import uuid
import pytest
from playwright.sync_api import expect

@pytest.mark.admin
def test_admin_creates_user_and_changes_role(admin_page):
    page = admin_page
    page.get_by_text("관리자", exact=True).click()
    page.get_by_role("tab", name="사용자 관리").click()
    employee_no = f"qa-{uuid.uuid4().hex[:8]}"
    page.get_by_label("사번/아이디*").fill(employee_no)
    page.get_by_label("이름*").fill("자동화 사용자")
    page.get_by_label("초기 비밀번호*").fill("Automation-123!")
    page.get_by_role("button", name="사용자 추가").click()
    expect(page.get_by_text("사용자를 추가했습니다.")).to_be_visible()
    page.get_by_label("사용자").select_option(label=f"자동화 사용자 ({employee_no})")
    page.get_by_label("역할").last.select_option("INSPECTOR")
    page.get_by_label("분기 담당자 후보").last.check()
    page.get_by_label("변경 사유*").fill("자동화 권한 변경")
    page.get_by_role("button", name="사용자 변경 저장").click()
    expect(page.get_by_text("사용자를 변경했습니다.")).to_be_visible()

@pytest.mark.admin
def test_admin_assigns_quarter_owner(admin_page):
    page = admin_page
    page.get_by_text("관리자", exact=True).click()
    page.get_by_role("tab", name="분기 담당자").click()
    page.get_by_label("담당자").select_option(label="QA 점검자 (점검자)")
    page.get_by_label("지정 사유*").fill("Playwright 분기 배정")
    page.get_by_role("button", name="담당자 지정").click()
    expect(page.get_by_text("담당자를 지정했습니다.")).to_be_visible()
