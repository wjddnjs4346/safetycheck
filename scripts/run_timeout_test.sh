#!/usr/bin/env bash
set -euo pipefail
# 타임아웃만 빠르게 검증하려면 safety-map 서비스의 환경변수에
# SESSION_TIMEOUT_SECONDS=2를 설정한 뒤 재기동합니다.
export SESSION_TIMEOUT_SECONDS=2
./scripts/run_playwright.sh -m auth -k inactivity_timeout
