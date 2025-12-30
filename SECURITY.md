# 보안 가이드

## 환경 변수 관리

### 로컬 개발 환경
1. `.env.example` 파일을 참고하여 `.env` 파일 생성
2. `.env` 파일에 API 키 입력
3. **절대 `.env` 파일을 Git에 커밋하지 마세요**

### GitHub Actions 환경
1. GitHub 저장소 → Settings → Secrets and variables → Actions
2. "New repository secret" 클릭
3. API 키를 Secrets에 저장
4. 코드에서 `os.getenv('API_KEY_NAME')`으로 접근

## 보안 체크리스트

- [x] `.env` 파일이 `.gitignore`에 포함됨
- [x] API 키가 코드에 하드코딩되지 않음
- [x] 로그에 민감한 정보가 노출되지 않음
- [x] CSV 파일에 공개 데이터만 포함
- [x] GitHub Actions 권한 최소화

## 주의사항

1. **API 키 노출 금지**
   - 코드에 직접 입력하지 마세요
   - 커밋 전에 `git status`로 확인하세요
   - 실수로 커밋했다면 즉시 키를 재발급하세요

2. **로그 관리**
   - 로그에 API 키나 토큰이 포함되지 않도록 주의
   - 프로덕션 환경에서는 로그 레벨을 조정

3. **CSV 파일**
   - 공개 저장소에 업로드되는 파일
   - 민감한 정보를 포함하지 마세요

