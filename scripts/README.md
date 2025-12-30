# 뉴스 수집 스크립트

이 디렉토리에는 뉴스를 자동으로 수집하는 스크립트가 포함되어 있습니다.

## 파일 구조

- `fetch_news.py`: 메인 뉴스 수집 스크립트
- `keywords.json`: 검색 키워드 설정 파일

## 로컬 테스트 방법

1. 가상 환경 생성 (선택사항):
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. 의존성 설치:
```bash
pip install -r requirements.txt
```

3. 스크립트 실행:
```bash
python scripts/fetch_news.py
```

## 환경 변수

로컬 개발 시 `.env` 파일을 프로젝트 루트에 생성:
```
# .env 파일 (Git에 커밋하지 않음)
NEWS_API_KEY=your_api_key_here  # 추후 유료 API 사용 시
```

GitHub Actions에서는 리포지토리 Secrets를 사용합니다.

## 키워드 설정

`keywords.json` 파일을 수정하여 검색 키워드를 변경할 수 있습니다.

