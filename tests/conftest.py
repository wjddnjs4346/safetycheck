import os
from pathlib import Path

import bcrypt
import psycopg
import pytest
from playwright.sync_api import Page

BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8501")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://safety:safety@127.0.0.1:5432/safety_map")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "Test-password-123!")
PHOTO_PATH = Path(__file__).parent / "assets" / "test_photo.png"

USERS = {
    "admin": ("QA 관리자", "ADMIN", True),
    "registrar": ("QA 등록자", "REGISTRAR", False),
    "inspector": ("QA 점검자", "INSPECTOR", True),
    "viewer": ("QA 조회자", "VIEWER", False),
}


def db():
    return psycopg.connect(DATABASE_URL)


def seed_database():
    password_hash = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt())
    with db() as conn:
        conn.execute("TRUNCATE attachments, defect_actions, inspection_items, inspections, assignments, audit_logs, assets, users RESTART IDENTITY CASCADE")
        ids = {}
        for employee_no, (name, role, candidate) in USERS.items():
            row = conn.execute(
                "INSERT INTO users(employee_no,name,password_hash,role,active,candidate,created_at) VALUES(%s,%s,%s,%s,TRUE,%s,NOW()::text) RETURNING id",
                (employee_no, name, password_hash, role, candidate),
            ).fetchone()
            ids[employee_no] = row[0]
        asset_id = conn.execute(
            "INSERT INTO assets(asset_code,asset_name,asset_type,area_name,location_description,x_ratio,y_ratio,note,is_deleted,created_by,created_at) VALUES('QA-HYD-001','QA 옥내소화전','FIRE_HYDRANT','QA 구역','QA 출입구',0.25,0.35,'QA fixture',FALSE,%s,NOW()::text) RETURNING id",
            (ids["admin"],),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO assignments(year,quarter,user_id,scope_type,scope_value,active,reason,assigned_by,assigned_at) VALUES(EXTRACT(YEAR FROM CURRENT_DATE)::int,EXTRACT(QUARTER FROM CURRENT_DATE)::int,%s,'ALL','',TRUE,'QA fixture',%s,NOW()::text)",
            (ids["inspector"], ids["admin"]),
        )
    return {"users": ids, "asset_id": asset_id}


@pytest.fixture(autouse=True)
def reset_database():
    seed_database()
    yield


@pytest.fixture
def login():
    def _login(page: Page, employee_no: str, password: str = TEST_PASSWORD):
        page.goto(BASE_URL)
        page.get_by_label("아이디").fill(employee_no)
        page.get_by_label("비밀번호").fill(password)
        page.get_by_role("button", name="로그인").click()
        page.get_by_text("안전설비 관리 맵", exact=True).last.wait_for()
    return _login


@pytest.fixture
def admin_page(page: Page, login):
    login(page, "admin")
    return page
