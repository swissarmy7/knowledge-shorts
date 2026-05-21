#!/bin/bash

# 프로젝트 디렉토리 설정
PROJECT_DIR="/var/www/html/my_shorts"
cd $PROJECT_DIR

# 1. 컨테이너 실행 여부 확인
CONTAINER_STATUS=$(docker ps -q -f name=shorts-generator)

# 2. API 응답 확인 (localhost:8000/api/auth-check)
# auth-check는 401을 반환하더라도 서버가 살아있음을 의미하므로 유효한 응답으로 간주
API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/auth-check)

if [ -z "$CONTAINER_STATUS" ] || [ "$API_STATUS" -eq 000 ] || [ "$API_STATUS" -ge 500 ]; then
    echo "$(date): Health check failed (Status: $API_STATUS). Restarting shorts-generator..." >> $PROJECT_DIR/health_check.log
    
    # 컨테이너 재시작
    docker compose up -d
    
    # Nginx 설정 재로드 (필요한 경우)
    docker exec scenespot-nginx nginx -s reload >> /dev/null 2>&1
else
    # 정상 작동 시 로그 (필요 시 주석 해제)
    # echo "$(date): Health check passed." >> $PROJECT_DIR/health_check.log
    exit 0
fi
