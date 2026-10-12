#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
  echo '.env 파일이 없습니다. cp .env.example .env 후 비밀번호를 변경하세요.' >&2
  exit 1
fi

set -a
. ./.env
set +a

export APP_BASE_URL="${APP_BASE_URL:-http://127.0.0.1:8501}"
export DATABASE_URL="${DATABASE_URL:-postgresql://safety:${POSTGRES_PASSWORD}@127.0.0.1:5432/safety_map}"
export TEST_USER_PASSWORD="${TEST_USER_PASSWORD:-Test-password-123!}"

python -m pip install -r requirements-test.txt
python -m playwright install chromium

docker compose up -d --build
for i in $(seq 1 60); do
  if curl -fsS "$APP_BASE_URL/_stcore/health" >/dev/null; then
    break
  fi
  sleep 2
  if [ "$i" -eq 60 ]; then
    docker compose logs safety-map
    exit 1
  fi
done

pytest \
  --browser chromium \
  --tracing retain-on-failure \
  --screenshot only-on-failure \
  --output test-results \
  "$@"
