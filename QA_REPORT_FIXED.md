# 수정본 QA 보고서

## 판정
**코드 및 구성 검증 통과, 실제 PostgreSQL 통합 테스트는 배포 환경에서 추가 필요**

## 완료한 검증
- `app.py` Python 문법 검사 통과
- Playwright 테스트 파일 문법 검사 통과
- SQLite import와 SQL `?` placeholder 제거 확인
- 로그인 기본값 제거 확인
- 사용자 관리, 설비 수정, 사진첨부, 30분 타임아웃 코드 존재 확인
- PostgreSQL 연결 실패 시 사용자에게 설정 오류를 표시하고 앱이 무작정 중단되지 않는 흐름 확인
- PostgreSQL/관리자 비밀번호 필수 환경변수 Docker Compose 구성

## 환경 제약
현재 실행 컨테이너에는 Docker/PostgreSQL 서버가 없어 실제 DB 통합 흐름은 실행하지 못했다. `AppTest`로 PostgreSQL 미기동 시 오류화면이 예외 없이 렌더링되는 것을 확인했다.

## 배포 후 실행할 검증

```bash
cp .env.example .env
# 강력한 비밀번호로 변경
docker compose up -d --build
pip install -r requirements-test.txt
playwright install chromium
INITIAL_ADMIN_PASSWORD='<.env와 동일한 값>' pytest tests/test_streamlit_playwright.py
```

## 운영 참고
사진을 BYTEA로 저장하므로 초기 운영은 간단하지만 사진 데이터가 커지면 DB 백업 파일도 빠르게 증가한다. 운영 규모가 커지면 오브젝트 스토리지로 이전하는 것이 좋다.
