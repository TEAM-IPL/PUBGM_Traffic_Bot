# API 설정 가이드

## 📰 뉴스 수집 파이프라인

이 프로젝트는 **스마트 파이프라인**으로 뉴스를 수집합니다:

```
RSS 수집 (무료) → 스마트 필터링 → AI 정제 (무료/유료)
```

---

## 🆓 무료 API (추천)

### 1. RSS 피드 (기본, API 키 불필요) ✅

**완전 무료, 별도 설정 불필요!**

- Google News RSS 피드를 사용하여 실시간 뉴스 검색
- 상승/하락 국가와 관련된 뉴스를 자동으로 필터링

---

### 2. DeepSearch News API ⭐ **고품질 뉴스!**

**NYT, BBC, CNN 등 글로벌 주요 매체 검색!**

| 항목 | 내용 |
|------|------|
| 소스 | NYT, BBC, Washington Post, CNN, 조선, 한겨레 등 |
| 특징 | 고품질, 키워드 검색, 트렌딩 토픽 |
| 비용 | 유료 (플랜별 상이) |

**API 키 발급:**

1. https://deepsearch.com 접속
2. 계정 생성 및 API 키 발급

**.env 파일에 추가:**
```bash
DEEPSEARCH_API_KEY=64af66a6cxxxxxxxxxxxx
```

---

### 4. Groq API (무료, 초고속) ⚡ **강력 추천!**

**Llama 3.1 70B 모델 무료 사용!**

| 항목 | 내용 |
|------|------|
| 무료 한도 | 분당 30회, 일 14,400회 |
| 속도 | 초고속 (업계 최고) |
| 모델 | Llama 3.1 70B, Mixtral 등 |

**API 키 발급:**

1. https://console.groq.com/ 접속
2. Google/GitHub 계정으로 로그인
3. "API Keys" → "Create API Key"
4. API 키 복사

**.env 파일에 추가:**
```bash
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

---

## 💰 유료 API (선택사항)

### 5. OpenAI API (GPT-4o-mini) 🤖

**고품질 분석, 저렴한 가격**

| 항목 | 내용 |
|------|------|
| 비용 | ~$0.0001/요청 (GPT-4o-mini) |
| 특징 | 안정적, 고품질 |

**API 키 발급:**
1. https://platform.openai.com/api-keys 접속
2. 계정 생성 및 API 키 발급

**.env 파일에 추가:**
```bash
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

---

### 6. Claude API (Anthropic) 🤖

**심층 분석, 맥락 이해 우수**

| 항목 | 내용 |
|------|------|
| 비용 | ~$0.003/요청 |
| 특징 | 복잡한 추론 우수 |

**API 키 발급:**
1. https://console.anthropic.com/ 접속
2. API 키 발급

**.env 파일에 추가:**
```bash
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxx
# 또는
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

---

## 🚀 추천 설정

### 기본 (Groq만, 완전 무료)
```bash
# .env 파일
GROQ_API_KEY=gsk_xxxx      # AI 분류 (무료, 초고속)
```

### 추천 (DeepSearch + Groq)
```bash
# .env 파일
DEEPSEARCH_API_KEY=64af66a6c_xxxx  # 고품질 글로벌 뉴스
GROQ_API_KEY=gsk_xxxx              # AI 분류 (무료)
```

### 최고 품질 (전체 API)
```bash
# .env 파일
DEEPSEARCH_API_KEY=64af66a6c_xxxx  # 고품질 뉴스
GROQ_API_KEY=gsk_xxxx              # 1차: 빠른 분류
OPENAI_API_KEY=sk_xxxx             # 2차: 심층 분석 (상위 10개)
USE_PAID_API=true                  # 유료 API 활성화
```

---

## 📊 비용 비교

| 방식 | 일일 비용 | 월간 비용 |
|------|----------|----------|
| RSS만 | $0 | $0 |
| RSS + Groq | $0 | $0 |
| + DeepSearch | 플랜별 상이 | 플랜별 상이 |
| + OpenAI (상위 10개) | ~$0.001 | ~$0.03 |

---

## 🔒 보안

- `.env` 파일은 `.gitignore`에 포함되어 GitHub에 업로드되지 않습니다
- 로컬에서만 API 키를 사용하고, GitHub Pages에는 정제된 CSV만 배포됩니다

## 🚀 사용 방법

### 기본 사용 (RSS만)

별도 설정 없이 바로 사용 가능합니다!

### API 사용

1. `.env` 파일 생성
2. API 키 입력
3. `python scripts/fetch_news.py` 실행

## 📝 참고사항

- **RSS 피드**: 무료, API 키 불필요, 즉시 사용 가능
- **DeepSearch**: 고품질 글로벌 뉴스, 유료 플랜
- **Groq**: 무료, 초고속 AI 분류
- **OpenAI/Claude**: 유료, 심층 분석용

## 🔒 보안

- `config.js`는 `.gitignore`에 포함되어 있어 GitHub에 업로드되지 않습니다
- GitHub Secrets를 사용하면 안전하게 API 키를 관리할 수 있습니다
- 클라이언트 사이드에서 API 키를 사용하므로, 제한된 API 키 사용을 권장합니다

