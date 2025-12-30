#!/bin/bash
# 로컬에서 뉴스 수집 스크립트 실행 (API 키 사용)
# Windows에서는 run_local.bat 사용

echo "🔍 로컬 뉴스 수집 시작 (교차검증 모드)"
echo "=================================="

# .env 파일 확인
if [ ! -f .env ]; then
    echo "⚠️  .env 파일이 없습니다!"
    echo "프로젝트 루트에 .env 파일을 생성하고 API 키를 추가하세요."
    echo ""
    echo "예시:"
    echo "CROSS_VALIDATE=true"
    echo "NEWS_API_TYPE=openai"
    echo "OPENAI_API_KEY=sk-your-key"
    echo "CLAUDE_API_KEY=sk-ant-your-key"
    exit 1
fi

# Python 스크립트 실행
python scripts/fetch_news.py
exit_code=$?

if [ $exit_code -eq 0 ]; then
    echo ""
    echo "✅ 뉴스 수집 완료!"
    echo "변경사항을 확인하고 GitHub에 푸시하세요:"
    echo "  git add data/news.csv"
    echo "  git commit -m 'Update news data'"
    echo "  git push"
else
    echo ""
    echo "❌ 뉴스 수집 실패 (코드: $exit_code)"
fi

exit $exit_code

