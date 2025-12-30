# 전체 워크플로우 가이드

## 🔄 최종 구조

### 1. 로컬에서 뉴스 수집 (고품질, 교차검증)

```
로컬 컴퓨터
├─ .env 파일 (API 키 저장) ✅ 안전
│  ├─ OPENAI_API_KEY
│  └─ CLAUDE_API_KEY
│
├─ scripts/fetch_news.py 실행
│  ├─ OpenAI API 호출
│  ├─ Claude API 호출
│  └─ 교차검증 (신뢰도 평가)
│
└─ data/news.csv 생성
   ├─ 뉴스 제목
   ├─ 요약
   ├─ URL
   ├─ 날짜
   ├─ 국가/대륙
   ├─ 신뢰도 (high/medium)
   └─ 검증 정보
```

### 2. GitHub에 푸시

```bash
git add data/news.csv
git commit -m "Update news data"
git push
```

**푸시되는 내용:**
- ✅ `data/news.csv` - 정제된 뉴스 데이터만
- ❌ `.env` 파일 - 푸시 안 됨 (`.gitignore`에 포함)
- ❌ API 키 - 절대 포함되지 않음

### 3. GitHub Pages 배포

```
GitHub Pages 사이트
└─ data/news.csv (공개)
   ├─ 뉴스 제목
   ├─ 요약
   ├─ URL
   ├─ 날짜
   ├─ 국가/대륙
   ├─ 신뢰도
   └─ 검증 정보
```

**배포되는 내용:**
- ✅ 정제된 뉴스 데이터만
- ❌ API 키 없음
- ❌ 원본 API 응답 없음
- ❌ 민감한 정보 없음

## 📊 데이터 흐름

```
[로컬] .env (API 키)
  ↓
[로컬] fetch_news.py 실행
  ↓
[로컬] OpenAI + Claude API 호출
  ↓
[로컬] 교차검증 및 정제
  ↓
[로컬] news.csv 생성 (정제된 데이터만)
  ↓
[GitHub] news.csv 푸시
  ↓
[GitHub Pages] news.csv 공개
  ↓
[사용자] 웹에서 뉴스 확인
```

## 🔒 보안 체크리스트

- [x] `.env` 파일은 Git에 커밋되지 않음
- [x] API 키는 로컬에만 존재
- [x] `news.csv`에는 뉴스 데이터만 포함
- [x] API 키는 절대 노출되지 않음
- [x] 원본 API 응답은 저장되지 않음
- [x] 정제된 데이터만 배포됨

## ✅ 최종 확인

**로컬에서:**
- API 키 사용 ✅
- 교차검증 실행 ✅
- 정제된 CSV 생성 ✅

**GitHub에:**
- 정제된 CSV만 푸시 ✅
- API 키 없음 ✅

**배포된 사이트:**
- 정제된 뉴스만 표시 ✅
- API 키 없음 ✅
- 보안 문제 없음 ✅

