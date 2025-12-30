@echo off
REM 로컬에서 뉴스 수집 스크립트 실행 (API 키 사용)
REM Windows 배치 파일

echo 🔍 로컬 뉴스 수집 시작 (교차검증 모드)
echo ==================================

REM .env 파일 확인
if not exist .env (
    echo ⚠️  .env 파일이 없습니다!
    echo 프로젝트 루트에 .env 파일을 생성하고 API 키를 추가하세요.
    echo.
    echo 예시:
    echo CROSS_VALIDATE=true
    echo NEWS_API_TYPE=openai
    echo OPENAI_API_KEY=sk-your-key
    echo CLAUDE_API_KEY=sk-ant-your-key
    exit /b 1
)

REM Python 스크립트 실행
python scripts/fetch_news.py
set exit_code=%ERRORLEVEL%

if %exit_code% equ 0 (
    echo.
    echo ✅ 뉴스 수집 완료!
    echo 변경사항을 확인하고 GitHub에 푸시하세요:
    echo   git add data/news.csv
    echo   git commit -m "Update news data"
    echo   git push
) else (
    echo.
    echo ❌ 뉴스 수집 실패 (코드: %exit_code%)
)

exit /b %exit_code%

