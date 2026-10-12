# Playwright 보강 결과

## 추가된 구성

- `tests/conftest.py`: PostgreSQL 테스트 데이터 초기화 및 역할별 사용자 fixture
- `test_auth_and_rbac.py`: 로그인, 로그아웃, 타임아웃, 역할별 메뉴
- `test_asset_workflow.py`: 설비 등록 접근, 수정, 사진, 삭제, 복구
- `test_admin_workflow.py`: 사용자 추가·권한 변경, 담당자 지정
- `test_inspection_workflow.py`: 점검, 미비 코멘트, 점검사진, 조치사진
- `test_responsive_and_quality.py`: 뷰포트, 키보드, Console/Page Error
- `pytest.ini`: 테스트 마커
- `scripts/run_playwright.sh`: Docker 앱 기동부터 E2E 실행까지 자동화
- `scripts/run_timeout_test.sh`: 30분 타임아웃 단축 검증 절차

## 테스트 수

파라미터 확장 기준으로 총 23개 테스트 케이스가 구성된다.

## 검증 상태

- 모든 Python 테스트 파일 문법 검사 완료
- 테스트 fixture와 PostgreSQL seed SQL 정적 검토 완료
- 테스트 이미지 fixture 생성 확인
- 실제 Chromium 실행은 현재 샌드박스의 브라우저 다운로드 차단 및 Docker 부재로 수행하지 못함
- 실제 실행 전 통과로 간주하지 않음

## 실행 권고

```bash
cp .env.example .env
# .env 비밀번호 변경
./scripts/run_playwright.sh
```

특정 영역만 실행:

```bash
./scripts/run_playwright.sh -m auth
./scripts/run_playwright.sh -m rbac
./scripts/run_playwright.sh -m assets
./scripts/run_playwright.sh -m admin
./scripts/run_playwright.sh -m inspections
./scripts/run_playwright.sh -m responsive
```
