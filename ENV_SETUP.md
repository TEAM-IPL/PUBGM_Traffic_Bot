# 환경 변수 설정 가이드

## ⚠️ 중요: API 키는 로컬에서만 사용

**GitHub Secrets에 API 키를 저장하지 않습니다!**
- 로컬에서만 `.env` 파일로 API 키 사용
- GitHub Actions는 RSS만 사용 (API 키 불필요)
- 수집된 뉴스 데이터만 GitHub에 커밋

## .env 파일 사용 방법

### 1. 로컬 개발 환경

프로젝트 루트(`PUBGM_TRAFFIC-master/`)에 `.env` 파일을 생성하세요:

```bash
# .env 파일 내용

# 교차검증 활성화 (OpenAI + Claude 둘 다 사용)
CROSS_VALIDATE=true

# 사용할 API 타입 선택 (교차검증 시 어느 것을 기본으로 할지)
# openai: OpenAI를 기본으로 사용
# claude: Claude를 기본으로 사용
NEWS_API_TYPE=openai

# OpenAI API 키
OPENAI_API_KEY=sk-proj-your-openai-api-key-here

# Claude API 키
CLAUDE_API_KEY=sk-ant-api03-your-claude-api-key-here

# NAVER_API_KEY
NAVER_CLIENT_ID=your-naver-client-id
NAVER_CLIENT_SECRET=your-naver-client-secret
```

### 2. 로컬에서 실행

#### 방법 A: 직접 실행
```bash
python scripts/fetch_news.py
```

#### 방법 B: 배치 파일 사용 (Windows)
```bash
# 더블클릭 또는
scripts\run_local.bat
```

#### 방법 C: 쉘 스크립트 사용 (Mac/Linux)
```bash
chmod +x scripts/run_local.sh
./scripts/run_local.sh
```

### 3. 수집 후 GitHub에 푸시

```bash
# 변경사항 확인
git status

# 뉴스 파일 추가
git add data/news.csv

# 커밋
git commit -m "Update news data with cross-validation"

# 푸시
git push
```

### 4. GitHub Actions (자동 실행)

GitHub Actions는 **RSS만 사용**합니다 (API 키 불필요):
- 매일 한국시간 오전 9시 자동 실행
- RSS 피드로 뉴스 수집
- 변경사항이 있으면 자동 커밋

## 보안 구조

```
┌─────────────────────────────────────┐
│ 로컬 환경 (당신의 컴퓨터)            │
│ - .env 파일에 API 키 저장 ✅         │
│ - Git에 커밋되지 않음 (안전)         │
│ - 교차검증으로 고품질 뉴스 수집      │
└─────────────────────────────────────┘
              ↓ (수동 푸시)
┌─────────────────────────────────────┐
│ GitHub 저장소                       │
│ - news.csv 파일만 포함              │
│ - API 키 없음 ✅                     │
│ - 공개되어도 안전                    │
└─────────────────────────────────────┘
              ↓ (자동 실행)
┌─────────────────────────────────────┐
│ GitHub Actions                      │
│ - RSS만 사용 (API 키 불필요)         │
│ - 매일 자동 실행                     │
│ - 보완적인 뉴스 수집                 │
└─────────────────────────────────────┘
```

## 사용 시나리오

### 시나리오 1: 로컬에서 고품질 뉴스 수집
1. `.env` 파일에 API 키 추가
2. `python scripts/fetch_news.py` 실행
3. 교차검증된 뉴스가 `data/news.csv`에 저장
4. 수동으로 GitHub에 푸시

### 시나리오 2: 자동 백업 (RSS)
- GitHub Actions가 매일 자동으로 RSS 뉴스 수집
- API 키 없이도 기본적인 뉴스 수집 가능

## 보안 주의사항

- ✅ `.env` 파일은 `.gitignore`에 포함되어 Git에 커밋되지 않습니다
- ✅ GitHub Secrets는 암호화되어 저장됩니다
- ❌ 절대 코드에 API 키를 하드코딩하지 마세요
- ❌ `.env` 파일을 Git에 커밋하지 마세요

## API 타입별 사용법

### RSS (기본, 무료)
```bash
NEWS_API_TYPE=rss
# API 키 불필요
```

### OpenAI
```bash
NEWS_API_TYPE=openai
OPENAI_API_KEY=sk-your-key-here
```

### Claude
```bash
NEWS_API_TYPE=claude
CLAUDE_API_KEY=sk-ant-your-key-here
```

