from __future__ import annotations

import io
import os
import secrets
import time

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import bcrypt
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw
try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except (ImportError, AttributeError):
    streamlit_image_coordinates = None

APP_DIR = Path(__file__).parent
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://safety:safety@localhost:5432/safety_map")
POOL = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False)
SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT_SECONDS", "1800"))
LAYOUT_PATH = APP_DIR / "assets" / "layout.png"
UPLOAD_DIR = APP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ROLES = {"ADMIN": "관리자", "REGISTRAR": "지정 등록자", "INSPECTOR": "점검자", "VIEWER": "조회자"}
ASSET_TYPES = {"FIRE_HYDRANT": "소화전", "FIRE_EXTINGUISHER": "소화기", "GAS_MANIFOLD": "가스 매니폴더"}
STATUSES = {"NOT_INSPECTED": "미점검", "INCOMPLETE": "미완료", "COMPLETED": "완료"}
STATUS_COLORS = {"NOT_INSPECTED": "#9E9E9E", "INCOMPLETE": "#D32F2F", "COMPLETED": "#2E7D32"}
CHECKLISTS = {
    "FIRE_HYDRANT": [
        "호스(2ea), 관창, 레버(옥외) 비치 여부",
        "호스 보관 상태(고착, 지그재그)",
        "호스와 앵글밸브 체결 여부(옥내 소화전)",
        "옥외소화전 개방 실시 및 고착 여부",
        "소화전 함 상태",
    ],
    "FIRE_EXTINGUISHER": [
        "용기 변형/훼손",
        "손잡이 변형/훼손",
        "호스, 노즐 변형/훼손",
        "지시압력 확인",
        "안전핀 탈락/변형",
    ],
    "GAS_MANIFOLD": [
        "MSDS, 점검표 비치",
        "가스 누설 유무",
        "버블 체크 비치 여부",
        "사용 전 점검표 및 정기점검표 작성 유무",
        "밸브 잠금 상태",
        "게이지 상태(상·하한 표시)",
        "정리정돈 상태",
    ],
}

st.set_page_config(page_title="안전설비 관리 맵", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def db():
    if POOL.closed:
        POOL.open(wait=True, timeout=15)
    with POOL.connection() as conn:
        with conn.transaction():
            yield conn


def q(sql: str, params: tuple = (), one: bool = False):
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    data = [dict(x) for x in rows]
    return (data[0] if data else None) if one else data


def execute(sql: str, params: tuple = ()) -> int:
    with db() as conn:
        statement = sql.strip()
        if statement.upper().startswith("INSERT") and "RETURNING" not in statement.upper():
            statement += " RETURNING id"
            row = conn.execute(statement, params).fetchone()
            return int(row["id"])
        conn.execute(statement, params)
        return 0


def audit(action: str, entity: str, entity_id: Any, reason: str = "", before: str = "", after: str = ""):
    user = st.session_state.get("user") or {}
    execute(
        "INSERT INTO audit_logs(user_id,action_type,entity_type,entity_id,reason,before_value,after_value,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (user.get("id"), action, entity, str(entity_id), reason, before, after, now()),
    )


def store_attachment(entity_type: str, entity_id: int, purpose: str, uploaded_file, user_id: int):
    if not uploaded_file:
        return
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if uploaded_file.type not in allowed:
        raise ValueError("JPG, PNG, WEBP 이미지만 첨부할 수 있습니다.")
    data = uploaded_file.getvalue()
    if len(data) > 10 * 1024 * 1024:
        raise ValueError("사진은 파일당 10MB 이하여야 합니다.")
    execute(
        "INSERT INTO attachments(entity_type,entity_id,purpose,file_name,mime_type,file_data,uploaded_by,uploaded_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (entity_type, entity_id, purpose, uploaded_file.name, uploaded_file.type, psycopg.Binary(data), user_id, now()),
    )


def show_attachments(entity_type: str, entity_id: int, purpose: str | None = None):
    sql = "SELECT id,purpose,file_name,mime_type,file_data FROM attachments WHERE entity_type=%s AND entity_id=%s"
    params = [entity_type, entity_id]
    if purpose:
        sql += " AND purpose=%s"
        params.append(purpose)
    rows = q(sql + " ORDER BY id", tuple(params))
    if rows:
        cols = st.columns(min(3, len(rows)))
        for idx, row in enumerate(rows):
            cols[idx % len(cols)].image(bytes(row["file_data"]), caption=f"{row['purpose']} · {row['file_name']}", use_container_width=True)

def init_db():
    initial_password = os.getenv("INITIAL_ADMIN_PASSWORD")
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users(
              id BIGSERIAL PRIMARY KEY, employee_no TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
              password_hash BYTEA NOT NULL, role TEXT NOT NULL CHECK(role IN ('ADMIN','REGISTRAR','INSPECTOR','VIEWER')),
              active BOOLEAN NOT NULL DEFAULT TRUE, candidate BOOLEAN NOT NULL DEFAULT FALSE, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS assets(
              id BIGSERIAL PRIMARY KEY, asset_code TEXT UNIQUE NOT NULL, asset_name TEXT NOT NULL,
              asset_type TEXT NOT NULL, area_name TEXT NOT NULL, location_description TEXT DEFAULT '',
              x_ratio DOUBLE PRECISION NOT NULL CHECK(x_ratio BETWEEN 0 AND 1), y_ratio DOUBLE PRECISION NOT NULL CHECK(y_ratio BETWEEN 0 AND 1),
              note TEXT DEFAULT '', is_deleted BOOLEAN NOT NULL DEFAULT FALSE, created_by BIGINT, created_at TEXT NOT NULL,
              updated_at TEXT, deleted_at TEXT, deletion_reason TEXT);
            CREATE TABLE IF NOT EXISTS assignments(
              id BIGSERIAL PRIMARY KEY, year INTEGER NOT NULL, quarter INTEGER NOT NULL CHECK(quarter BETWEEN 1 AND 4),
              user_id BIGINT NOT NULL, scope_type TEXT NOT NULL, scope_value TEXT DEFAULT '', active BOOLEAN NOT NULL DEFAULT TRUE,
              reason TEXT NOT NULL, assigned_by BIGINT, assigned_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inspections(
              id BIGSERIAL PRIMARY KEY, asset_id BIGINT NOT NULL, year INTEGER NOT NULL, quarter INTEGER NOT NULL,
              inspector_id BIGINT NOT NULL, version INTEGER NOT NULL DEFAULT 1, submitted_at TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inspection_items(
              id BIGSERIAL PRIMARY KEY, inspection_id BIGINT NOT NULL, item_no INTEGER NOT NULL,
              item_name TEXT NOT NULL, result TEXT NOT NULL, comment TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS defect_actions(
              id BIGSERIAL PRIMARY KEY, item_id BIGINT NOT NULL, status TEXT NOT NULL,
              action_comment TEXT DEFAULT '', completed_by BIGINT, completed_at TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attachments(
              id BIGSERIAL PRIMARY KEY, entity_type TEXT NOT NULL, entity_id BIGINT NOT NULL, purpose TEXT NOT NULL,
              file_name TEXT NOT NULL, mime_type TEXT NOT NULL, file_data BYTEA NOT NULL,
              uploaded_by BIGINT, uploaded_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit_logs(
              id BIGSERIAL PRIMARY KEY, user_id BIGINT, action_type TEXT NOT NULL, entity_type TEXT NOT NULL,
              entity_id TEXT, reason TEXT, before_value TEXT, after_value TEXT, created_at TEXT NOT NULL);
        """)
        count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if count == 0:
            if not initial_password or len(initial_password) < 10:
                raise RuntimeError("최초 실행 시 INITIAL_ADMIN_PASSWORD 환경변수에 10자 이상의 관리자 비밀번호를 설정하세요.")
            admin_password = bcrypt.hashpw(initial_password.encode(), bcrypt.gensalt())
            admin = conn.execute(
                "INSERT INTO users(employee_no,name,password_hash,role,active,candidate,created_at) VALUES(%s,%s,%s,'ADMIN',TRUE,TRUE,%s) RETURNING id",
                ("admin", "안전 관리자", admin_password, now()),
            ).fetchone()["id"]
            samples = [
                ("HYD-001", "1호 옥내소화전", "FIRE_HYDRANT", "가열로 구역", "가열로 출입구 우측", .22, .34),
                ("EXT-001", "압연기 소화기", "FIRE_EXTINGUISHER", "압연기 구역", "운전실 전면", .52, .51),
                ("GAS-001", "산소 매니폴더", "GAS_MANIFOLD", "정정 구역", "가스 저장소", .78, .67),
            ]
            for row in samples:
                conn.execute(
                    "INSERT INTO assets(asset_code,asset_name,asset_type,area_name,location_description,x_ratio,y_ratio,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (*row, admin, now()),
                )

def asset_status(asset_id: int, year: int, quarter: int) -> str:
    inspection = q(
        "SELECT * FROM inspections WHERE asset_id= %s AND year= %s AND quarter= %s ORDER BY version DESC,id DESC LIMIT 1",
        (asset_id, year, quarter), one=True,
    )
    if not inspection:
        return "NOT_INSPECTED"
    items = q("SELECT * FROM inspection_items WHERE inspection_id= %s", (inspection["id"],))
    for item in items:
        if item["result"] == "DEFECT":
            action = q("SELECT * FROM defect_actions WHERE item_id= %s ORDER BY id DESC LIMIT 1", (item["id"],), one=True)
            if not action or action["status"] != "CLOSED":
                return "INCOMPLETE"
    return "COMPLETED"


def can_inspect(user: dict, asset: dict, year: int, quarter: int) -> bool:
    if user["role"] == "ADMIN":
        return True
    if user["role"] != "INSPECTOR":
        return False
    rows = q("SELECT * FROM assignments WHERE active=1 AND user_id= %s AND year= %s AND quarter= %s", (user["id"], year, quarter))
    return any(
        r["scope_type"] == "ALL"
        or (r["scope_type"] == "AREA" and r["scope_value"] == asset["area_name"])
        or (r["scope_type"] == "ASSET" and r["scope_value"] == str(asset["id"]))
        for r in rows
    )


def draw_map(assets: list[dict], year: int, quarter: int, selected_id: int | None = None) -> Image.Image:
    img = Image.open(LAYOUT_PATH).convert("RGB")
    draw = ImageDraw.Draw(img)
    radius = max(10, img.width // 110)
    for a in assets:
        x, y = int(a["x_ratio"] * img.width), int(a["y_ratio"] * img.height)
        s = asset_status(a["id"], year, quarter)
        color = STATUS_COLORS[s]
        outline = "#146FE8" if a["id"] == selected_id else "white"
        width = 7 if a["id"] == selected_id else 4
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=color, outline=outline, width=width)
        symbol = {"FIRE_HYDRANT": "H", "FIRE_EXTINGUISHER": "E", "GAS_MANIFOLD": "G"}[a["asset_type"]]
        draw.text((x, y), symbol, fill="white", anchor="mm")
    return img


def login_page():
    st.markdown("<div style='height:8vh'></div>", unsafe_allow_html=True)
    left, center, right = st.columns([1, 1.2, 1])
    with center:
        st.title("🛡️ 안전설비 관리 맵")
        st.caption("중형압연공장 소방·가스 안전설비")
        with st.form("login"):
            emp = st.text_input("아이디", value="")
            pw = st.text_input("비밀번호", type="password", value="")
            if st.form_submit_button("로그인", use_container_width=True, type="primary"):
                user = q("SELECT * FROM users WHERE employee_no= %s AND active=1", (emp,), one=True)
                if user and bcrypt.checkpw(pw.encode(), user["password_hash"]):
                    user.pop("password_hash", None)
                    st.session_state.user = user
                    st.session_state.last_activity = time.time()
                    st.rerun()
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


def filters(assets: list[dict], year: int, quarter: int):
    st.sidebar.header("필터")
    keyword = st.sidebar.text_input("설비명 또는 관리번호")
    type_options = ["전체"] + list(ASSET_TYPES.values())
    asset_type = st.sidebar.selectbox("설비 종류", type_options)
    status = st.sidebar.selectbox("점검 상태", ["전체"] + list(STATUSES.values()))
    areas = ["전체"] + sorted({a["area_name"] for a in assets})
    area = st.sidebar.selectbox("구역", areas)
    out = assets
    if keyword:
        out = [a for a in out if keyword.lower() in f'{a["asset_name"]} {a["asset_code"]}'.lower()]
    if asset_type != "전체": out = [a for a in out if ASSET_TYPES[a["asset_type"]] == asset_type]
    if status != "전체": out = [a for a in out if STATUSES[asset_status(a["id"], year, quarter)] == status]
    if area != "전체": out = [a for a in out if a["area_name"] == area]
    return out


def register_asset(user: dict):
    st.subheader("설비 위치 등록")
    st.caption("도면을 클릭해 위치를 지정한 후 설비정보를 입력하세요.")
    base = Image.open(LAYOUT_PATH)
    if streamlit_image_coordinates is not None:
        clicked = streamlit_image_coordinates(base, key="register_coordinate", width=min(1100, base.width))
        if clicked:
            st.session_state.new_x = clicked["x"] / clicked["width"]
            st.session_state.new_y = clicked["y"] / clicked["height"]
        x = st.session_state.get("new_x")
        y = st.session_state.get("new_y")
        st.write("선택 좌표:", "도면을 클릭하세요" if x is None else f"x={x:.4f}, y={y:.4f}")
    else:
        st.warning("현재 Streamlit 버전에서는 도면 클릭 컴포넌트를 사용할 수 없어 좌표 슬라이더로 대체합니다.")
        st.image(base, use_container_width=True)
        x = st.slider("가로 위치", 0.0, 1.0, float(st.session_state.get("new_x", 0.5)), 0.001)
        y = st.slider("세로 위치", 0.0, 1.0, float(st.session_state.get("new_y", 0.5)), 0.001)
        st.session_state.new_x, st.session_state.new_y = x, y
    with st.form("asset_register"):
        c1, c2 = st.columns(2)
        code = c1.text_input("관리번호*")
        name = c2.text_input("설비명*")
        asset_type = c1.selectbox("설비 종류*", list(ASSET_TYPES), format_func=lambda z: ASSET_TYPES[z])
        area = c2.text_input("설치구역*")
        loc = st.text_input("세부 위치")
        note = st.text_area("비고")
        if st.form_submit_button("설비 등록", type="primary"):
            if x is None or y is None or not all([code, name, area]):
                st.error("도면 위치와 필수항목을 모두 입력하세요.")
            else:
                try:
                    asset_id = execute(
                        "INSERT INTO assets(asset_code,asset_name,asset_type,area_name,location_description,x_ratio,y_ratio,note,created_by,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (code, name, asset_type, area, loc, x, y, note, user["id"], now()),
                    )
                    audit("CREATE", "ASSET", asset_id, after=f"{code} {name}")
                    st.session_state.pop("new_x", None); st.session_state.pop("new_y", None)
                    st.success("설비가 등록되었습니다.")
                    st.rerun()
                except psycopg.errors.UniqueViolation:
                    st.error("이미 사용 중인 관리번호입니다.")


def inspection_form(user: dict, asset: dict, year: int, quarter: int):
    st.subheader(f"{asset['asset_name']} 점검")
    if not can_inspect(user, asset, year, quarter):
        st.warning("이 설비의 현재 분기 점검 권한이 없습니다.")
        return
    items = CHECKLISTS[asset["asset_type"]]
    results = []
    with st.form(f"inspection_{asset['id']}"):
        for idx, name in enumerate(items, 1):
            st.markdown(f"**{idx}. {name}**")
            result = st.radio("판정", ["PASS", "DEFECT", "NA"], format_func=lambda z: {"PASS":"적합","DEFECT":"미비","NA":"해당없음"}[z], horizontal=True, key=f"r_{asset['id']}_{idx}")
            comment = st.text_input("미비 코멘트", key=f"c_{asset['id']}_{idx}", disabled=result != "DEFECT")
            results.append((idx, name, result, comment))
            st.divider()
        inspection_photo = st.file_uploader("점검 증빙사진", type=["jpg", "jpeg", "png", "webp"], key=f"inspection_photo_{asset['id']}")
        if st.form_submit_button("최종 제출", type="primary"):
            if any(r == "DEFECT" and not c.strip() for _, _, r, c in results):
                st.error("미비항목에는 코멘트를 입력하세요.")
            else:
                old = q("SELECT MAX(version) v FROM inspections WHERE asset_id= %s AND year= %s AND quarter= %s", (asset["id"], year, quarter), one=True)
                version = int(old["v"] or 0) + 1
                inspection_id = execute(
                    "INSERT INTO inspections(asset_id,year,quarter,inspector_id,version,submitted_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (asset["id"], year, quarter, user["id"], version, now(), now()),
                )
                for no, name, result, comment in results:
                    item_id = execute("INSERT INTO inspection_items(inspection_id,item_no,item_name,result,comment) VALUES(%s,%s,%s,%s,%s)", (inspection_id, no, name, result, comment))
                    if result == "DEFECT":
                        execute("INSERT INTO defect_actions(item_id,status,created_at) VALUES(%s,'OPEN',%s)", (item_id, now()))
                store_attachment("INSPECTION", inspection_id, "점검 증빙", inspection_photo, user["id"])
                audit("SUBMIT", "INSPECTION", inspection_id, after=f"asset={asset['id']}, {year}Q{quarter}, v{version}")
                st.success("점검이 제출되었습니다.")
                st.rerun()


def defects_page(user: dict):
    st.header("미비사항 조치")
    rows = q("""
      SELECT ii.id item_id, a.id asset_id,a.asset_name,i.year,i.quarter,ii.item_name,ii.comment,
      (SELECT da.status FROM defect_actions da WHERE da.item_id=ii.id ORDER BY da.id DESC LIMIT 1) action_status
      FROM inspection_items ii JOIN inspections i ON i.id=ii.inspection_id JOIN assets a ON a.id=i.asset_id
      WHERE ii.result='DEFECT' ORDER BY i.submitted_at DESC
    """)
    if not rows: st.info("등록된 미비사항이 없습니다."); return
    for r in rows:
        asset = q("SELECT * FROM assets WHERE id= %s", (r["asset_id"],), one=True)
        with st.expander(f"{asset['asset_name']} · {r['year']}년 {r['quarter']}분기 · {r['item_name']}"):
            st.write("점검 코멘트:", r["comment"] or "-")
            st.write("현재 상태:", {"OPEN":"미조치","IN_PROGRESS":"조치중","CLOSED":"조치완료"}.get(r["action_status"], "미조치"))
            if user["role"] == "ADMIN" or can_inspect(user, asset, r["year"], r["quarter"]):
                show_attachments("DEFECT", r["item_id"])
                comment = st.text_area("조치내용", key=f"action_{r['item_id']}")
                before_photo = st.file_uploader("조치 전 사진", type=["jpg","jpeg","png","webp"], key=f"before_{r['item_id']}")
                after_photo = st.file_uploader("조치 후 사진", type=["jpg","jpeg","png","webp"], key=f"after_{r['item_id']}")
                c1, c2 = st.columns(2)
                if c1.button("조치중", key=f"progress_{r['item_id']}"):
                    execute("INSERT INTO defect_actions(item_id,status,action_comment,created_at) VALUES(%s,'IN_PROGRESS',%s,%s)", (r["item_id"], comment, now()))
                    store_attachment("DEFECT", r["item_id"], "조치 전", before_photo, user["id"])
                    audit("ACTION", "DEFECT", r["item_id"], after="IN_PROGRESS")
                    st.rerun()
                if c2.button("조치완료", type="primary", key=f"close_{r['item_id']}"):
                    execute("INSERT INTO defect_actions(item_id,status,action_comment,completed_by,completed_at,created_at) VALUES(%s,'CLOSED',%s,%s,%s,%s)", (r["item_id"], comment, user["id"], now(), now()))
                    store_attachment("DEFECT", r["item_id"], "조치 전", before_photo, user["id"])
                    store_attachment("DEFECT", r["item_id"], "조치 후", after_photo, user["id"])
                    audit("COMPLETE", "DEFECT", r["item_id"], after="CLOSED")
                    st.rerun()


def admin_page(user: dict, year: int, quarter: int):
    st.header("관리자")
    tab1, tab2, tab3, tab4 = st.tabs(["분기 담당자", "사용자 관리", "삭제 설비", "감사로그"])
    with tab1:
        candidates = q("SELECT id,name,role FROM users WHERE active=TRUE AND candidate=TRUE ORDER BY name")
        if not candidates:
            st.warning("활성 담당자 후보가 없습니다. 사용자 관리에서 후보를 지정하세요.")
        else:
            with st.form("assign"):
                assignee = st.selectbox("담당자", candidates, format_func=lambda u: f"{u['name']} ({ROLES[u['role']]})")
                scope = st.selectbox("담당 범위", ["ALL", "AREA", "ASSET"], format_func=lambda z: {"ALL":"전체 공장","AREA":"구역","ASSET":"개별 설비"}[z])
                scope_value = st.text_input("구역명 또는 설비 ID", disabled=scope == "ALL")
                reason = st.text_input("지정 사유*")
                if st.form_submit_button("담당자 지정", type="primary"):
                    if not reason: st.error("지정 사유를 입력하세요.")
                    else:
                        assignment_id = execute("INSERT INTO assignments(year,quarter,user_id,scope_type,scope_value,active,reason,assigned_by,assigned_at) VALUES(%s,%s,%s,%s,%s,TRUE,%s,%s,%s)", (year, quarter, assignee["id"], scope, scope_value, reason, user["id"], now()))
                        audit("ASSIGN", "ASSIGNMENT", assignment_id, reason=reason); st.success("담당자를 지정했습니다."); st.rerun()
        st.dataframe(pd.DataFrame(q("SELECT a.id,a.year,a.quarter,u.name AS 담당자,a.scope_type AS 범위,a.scope_value AS 대상,a.reason AS 사유 FROM assignments a JOIN users u ON u.id=a.user_id WHERE a.active=TRUE ORDER BY a.id DESC")), use_container_width=True, hide_index=True)
    with tab2:
        st.subheader("사용자 추가")
        with st.form("create_user", clear_on_submit=True):
            c1,c2=st.columns(2)
            employee_no=c1.text_input("사번/아이디*")
            name=c2.text_input("이름*")
            password=c1.text_input("초기 비밀번호*", type="password", help="10자 이상")
            role=c2.selectbox("역할", list(ROLES), format_func=lambda x:ROLES[x])
            candidate=st.checkbox("분기 담당자 후보", value=role in ("ADMIN","INSPECTOR"))
            if st.form_submit_button("사용자 추가", type="primary"):
                if not employee_no or not name or len(password)<10: st.error("아이디·이름과 10자 이상의 초기 비밀번호를 입력하세요.")
                else:
                    try:
                        uid=execute("INSERT INTO users(employee_no,name,password_hash,role,active,candidate,created_at) VALUES(%s,%s,%s,%s,TRUE,%s,%s)",(employee_no,name,bcrypt.hashpw(password.encode(),bcrypt.gensalt()),role,candidate,now()))
                        audit("CREATE","USER",uid,after=f"{employee_no}/{role}");st.success("사용자를 추가했습니다.");st.rerun()
                    except psycopg.errors.UniqueViolation: st.error("이미 사용 중인 아이디입니다.")
        users=q("SELECT id,employee_no,name,role,active,candidate,created_at FROM users ORDER BY id")
        st.subheader("사용자 권한 변경")
        selected=st.selectbox("사용자",users,format_func=lambda u:f"{u['name']} ({u['employee_no']})")
        with st.form("edit_user"):
            new_role=st.selectbox("역할",list(ROLES),index=list(ROLES).index(selected["role"]),format_func=lambda x:ROLES[x])
            active=st.checkbox("활성 사용자",value=bool(selected["active"]))
            cand=st.checkbox("분기 담당자 후보",value=bool(selected["candidate"]))
            reset_password=st.text_input("새 비밀번호(변경 시에만 입력)",type="password")
            reason=st.text_input("변경 사유*")
            if st.form_submit_button("사용자 변경 저장",type="primary"):
                if not reason: st.error("변경 사유를 입력하세요.")
                elif selected["id"]==user["id"] and not active: st.error("현재 로그인한 관리자 본인을 비활성화할 수 없습니다.")
                elif reset_password and len(reset_password)<10: st.error("새 비밀번호는 10자 이상이어야 합니다.")
                else:
                    execute("UPDATE users SET role=%s,active=%s,candidate=%s WHERE id=%s",(new_role,active,cand,selected["id"]))
                    if reset_password: execute("UPDATE users SET password_hash=%s WHERE id=%s",(bcrypt.hashpw(reset_password.encode(),bcrypt.gensalt()),selected["id"]))
                    audit("UPDATE","USER",selected["id"],reason=reason,after=f"role={new_role},active={active},candidate={cand}");st.success("사용자를 변경했습니다.");st.rerun()
        st.dataframe(pd.DataFrame(users),use_container_width=True,hide_index=True)
    with tab3:
        deleted=q("SELECT * FROM assets WHERE is_deleted=TRUE")
        for a in deleted:
            c1,c2=st.columns([4,1]);c1.write(f"{a['asset_code']} · {a['asset_name']} · {a['deletion_reason']}")
            if c2.button("복구",key=f"restore_{a['id']}"):
                execute("UPDATE assets SET is_deleted=FALSE,deleted_at=NULL,deletion_reason=NULL WHERE id=%s",(a["id"],));audit("RESTORE","ASSET",a["id"]);st.rerun()
    with tab4:
        logs=q("SELECT l.*,u.name AS user_name FROM audit_logs l LEFT JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 500")
        st.dataframe(pd.DataFrame(logs),use_container_width=True,hide_index=True)

def edit_asset_form(user: dict, asset: dict):
    st.subheader("설비 정보 및 위치 수정")
    with st.form(f"edit_asset_{asset['id']}"):
        c1,c2=st.columns(2)
        code=c1.text_input("관리번호",value=asset["asset_code"])
        name=c2.text_input("설비명",value=asset["asset_name"])
        atype=c1.selectbox("설비 종류",list(ASSET_TYPES),index=list(ASSET_TYPES).index(asset["asset_type"]),format_func=lambda x:ASSET_TYPES[x])
        area=c2.text_input("설치구역",value=asset["area_name"])
        loc=st.text_input("세부 위치",value=asset["location_description"] or "")
        note=st.text_area("비고",value=asset["note"] or "")
        x=st.slider("가로 위치",0.0,1.0,float(asset["x_ratio"]),0.001)
        y=st.slider("세로 위치",0.0,1.0,float(asset["y_ratio"]),0.001)
        photo=st.file_uploader("설비 사진",type=["jpg","jpeg","png","webp"])
        reason=st.text_input("수정 사유*")
        if st.form_submit_button("수정 저장",type="primary"):
            if not reason: st.error("수정 사유를 입력하세요.")
            else:
                execute("UPDATE assets SET asset_code=%s,asset_name=%s,asset_type=%s,area_name=%s,location_description=%s,note=%s,x_ratio=%s,y_ratio=%s,updated_at=%s WHERE id=%s",(code,name,atype,area,loc,note,x,y,now(),asset["id"]))
                store_attachment("ASSET",asset["id"],"설비 사진",photo,user["id"])
                audit("UPDATE","ASSET",asset["id"],reason=reason);st.success("설비를 수정했습니다.");st.rerun()
    show_attachments("ASSET",asset["id"])

def map_page(user: dict, year: int, quarter: int):
    all_assets = q("SELECT * FROM assets WHERE is_deleted=0 ORDER BY asset_code")
    assets = filters(all_assets, year, quarter)
    counts = {k: sum(asset_status(a["id"], year, quarter) == k for a in all_assets) for k in STATUSES}
    c1,c2,c3,c4,c5=st.columns(5)
    c1.metric("전체",len(all_assets));c2.metric("완료",counts["COMPLETED"]);c3.metric("미완료",counts["INCOMPLETE"]);c4.metric("미점검",counts["NOT_INSPECTED"]);c5.metric("완료율",f"{round(counts['COMPLETED']/len(all_assets)*100) if all_assets else 0}%")
    selected_id = st.session_state.get("selected_asset_id")
    st.image(draw_map(assets, year, quarter, selected_id), use_container_width=True)
    options = {f"{a['asset_code']} · {a['asset_name']} · {STATUSES[asset_status(a['id'],year,quarter)]}":a["id"] for a in assets}
    if options:
        selected_label = st.selectbox("설비 상세", options, index=list(options.values()).index(selected_id) if selected_id in options.values() else 0)
        selected_id = options[selected_label];st.session_state.selected_asset_id=selected_id
        asset = next(a for a in assets if a["id"]==selected_id)
        left,right=st.columns([2,1])
        with left:
            st.subheader(asset["asset_name"]);st.caption(asset["asset_code"])
            st.write(f"**종류:** {ASSET_TYPES[asset['asset_type']]}  |  **상태:** {STATUSES[asset_status(asset['id'],year,quarter)]}")
            st.write(f"**구역:** {asset['area_name']}  |  **위치:** {asset['location_description'] or '-'}")
        with right:
            if user["role"] in ("ADMIN","INSPECTOR") and st.button("이 설비 점검",use_container_width=True,type="primary"):
                st.session_state.page="점검";st.rerun()
            if user["role"] in ("ADMIN","REGISTRAR") and st.button("설비 수정",use_container_width=True):
                st.session_state.edit_asset_id=asset["id"]
            if user["role"]=="ADMIN" and st.button("설비 삭제",use_container_width=True):
                st.session_state.confirm_delete=asset["id"]
        show_attachments("ASSET", asset["id"])
        if st.session_state.get("edit_asset_id")==asset["id"]:
            edit_asset_form(user,asset)
        if st.session_state.get("confirm_delete")==asset["id"]:
            reason=st.text_input("삭제 사유")
            if st.button("삭제 확정",type="primary") and reason:
                execute("UPDATE assets SET is_deleted=1,deleted_at= %s,deletion_reason= %s WHERE id= %s",(now(),reason,asset["id"]));audit("DELETE","ASSET",asset["id"],reason=reason);st.session_state.pop("confirm_delete",None);st.rerun()
    csv = pd.DataFrame([{**a,"status":STATUSES[asset_status(a["id"],year,quarter)]} for a in all_assets]).to_csv(index=False).encode("utf-8-sig")
    st.download_button("설비 현황 CSV 다운로드",csv,f"safety_assets_{year}Q{quarter}.csv","text/csv")


def app():
    try:
        init_db()
    except Exception as exc:
        st.error(f"데이터베이스 연결 또는 초기화 실패: {exc}")
        st.info("DATABASE_URL과 최초 실행용 INITIAL_ADMIN_PASSWORD 환경변수를 확인하세요.")
        st.stop()
    current_time=time.time()
    if "user" in st.session_state:
        last_activity=st.session_state.get("last_activity",current_time)
        if current_time-last_activity>SESSION_TIMEOUT_SECONDS:
            st.session_state.clear();st.warning("30분 동안 활동이 없어 자동 로그아웃되었습니다.");st.rerun()
        st.session_state.last_activity=current_time
    if "user" not in st.session_state:
        login_page(); return
    user=st.session_state.user
    st.sidebar.title("🛡️ 안전설비")
    st.sidebar.caption(f"{user['name']} · {ROLES[user['role']]}")
    year=st.sidebar.selectbox("연도",list(range(datetime.now().year-1,datetime.now().year+3)),index=1)
    quarter=st.sidebar.selectbox("분기",[1,2,3,4],index=((datetime.now().month-1)//3))
    pages=["관리 맵"]
    if user["role"] in ("ADMIN","REGISTRAR"): pages.append("설비 등록")
    if user["role"] in ("ADMIN","INSPECTOR"): pages.extend(["점검","미비사항"])
    if user["role"]=="ADMIN": pages.append("관리자")
    default=st.session_state.get("page","관리 맵")
    page=st.sidebar.radio("메뉴",pages,index=pages.index(default) if default in pages else 0)
    st.session_state.page=page
    if st.sidebar.button("로그아웃",use_container_width=True):
        st.session_state.clear();st.rerun()
    st.title("안전설비 관리 맵")
    assignments=q("SELECT u.name FROM assignments a JOIN users u ON u.id=a.user_id WHERE a.active=1 AND a.year= %s AND a.quarter= %s",(year,quarter))
    st.caption(f"{year}년 {quarter}분기 · 담당자: {', '.join(x['name'] for x in assignments) or '미지정'}")
    if page=="관리 맵": map_page(user,year,quarter)
    elif page=="설비 등록": register_asset(user)
    elif page=="점검":
        assets=q("SELECT * FROM assets WHERE is_deleted=0 ORDER BY asset_code")
        if not assets: st.info("등록된 설비가 없습니다.")
        else:
            default_id=st.session_state.get("selected_asset_id")
            idx=next((i for i,a in enumerate(assets) if a["id"]==default_id),0)
            asset=st.selectbox("점검 설비",assets,index=idx,format_func=lambda a:f"{a['asset_code']} · {a['asset_name']}")
            inspection_form(user,asset,year,quarter)
    elif page=="미비사항": defects_page(user)
    elif page=="관리자": admin_page(user,year,quarter)


if __name__ == "__main__":
    app()
