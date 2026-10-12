# 중형압연공장 안전설비 관리 맵 - Streamlit/PostgreSQL

## 반영 기능

- 로그인 기본 아이디·비밀번호 제거
- 관리자 사용자 추가, 역할·활성상태·담당자 후보 변경, 비밀번호 초기화
- 관리자 및 지정 등록자의 기존 설비 정보·좌표 수정
- 설비 사진, 점검 증빙사진, 조치 전·후 사진 첨부
- 30분 무활동 자동 로그아웃
- PostgreSQL 데이터베이스 전환
- 관리자만 설비 삭제·복구
- 분기 담당자 지정 및 감사로그

## 가장 간단한 Docker 실행

```bash
cp .env.example .env
```

`.env`에서 두 비밀번호를 강력한 값으로 변경합니다.

```bash
docker compose up -d --build
```

접속 주소는 `http://localhost:8501`입니다. 최초 관리자 아이디는 `admin`, 비밀번호는 `.env`의 `INITIAL_ADMIN_PASSWORD`입니다. 로그인 화면에는 계정 정보가 자동 입력되거나 노출되지 않습니다.

## 로컬 Python 실행

PostgreSQL을 먼저 준비하고 환경변수를 설정합니다.

```bash
export DATABASE_URL='postgresql://safety:password@localhost:5432/safety_map'
export INITIAL_ADMIN_PASSWORD='10자-이상의-초기-관리자-비밀번호'
pip install -r requirements.txt
streamlit run app.py
```

Windows PowerShell:

```powershell
$env:DATABASE_URL='postgresql://safety:password@localhost:5432/safety_map'
$env:INITIAL_ADMIN_PASSWORD='10자-이상의-초기-관리자-비밀번호'
pip install -r requirements.txt
streamlit run app.py
```

`INITIAL_ADMIN_PASSWORD`는 사용자 테이블이 비어 있는 최초 실행에서만 사용됩니다.

## 사진 저장

사진은 PostgreSQL의 `attachments.file_data` BYTEA에 저장됩니다. 허용 형식은 JPG, PNG, WEBP이며 파일당 최대 10MB입니다. 운영 규모가 커지면 파일은 오브젝트 스토리지에 저장하고 DB에는 URL만 저장하는 방식을 권장합니다.

## 자동 로그아웃

로그인 후 Streamlit이 다시 실행될 때마다 활동시각을 갱신합니다. 마지막 활동 이후 30분을 초과하면 세션을 지우고 로그인 화면으로 이동합니다.

## 백업

```bash
docker compose exec postgres pg_dump -U safety -d safety_map -Fc -f /tmp/safety_map.dump
docker compose cp postgres:/tmp/safety_map.dump ./safety_map.dump
```

## Playwright 검토

```bash
pip install -r requirements-test.txt
playwright install chromium
streamlit run app.py --server.port 8501
pytest tests/test_streamlit_playwright.py --tracing=retain-on-failure --screenshot=only-on-failure
```

## 운영 전 확인

- 최초 관리자 비밀번호 변경
- HTTPS 및 사내망 접근 제한
- PostgreSQL 정기 백업과 복구 리허설
- 사진 저장 용량 모니터링
- 실제 Chromium Playwright 회귀 테스트

## 보강된 Playwright 전체 실행

Docker와 Chromium을 사용할 수 있는 환경에서 다음 명령만 실행하면 PostgreSQL, 앱 기동, 테스트 데이터 초기화, Playwright 테스트가 순서대로 수행됩니다.

```bash
cp .env.example .env
# .env 비밀번호 변경
./scripts/run_playwright.sh
```

세부 테스트 범위는 `PLAYWRIGHT_TEST_PLAN.md`, 결과 요약은 `PLAYWRIGHT_QA_ENHANCED.md`를 확인하세요.
