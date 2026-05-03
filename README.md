# 🏠 부동산 뉴스 자동 분석 봇 (Daily Real Estate Bot)

매일 네이버 경제 랭킹 뉴스에서 부동산 관련 소식을 수집하여 AI(Gemini 3 Flash)로 분석하고 블로그 포스팅 원고를 생성하는 자동화 봇입니다.

## 🚀 주요 기능
- **자동 수집**: 최근 48시간 내의 인기 부동산 뉴스 10개 수집
- **AI 분석**: 뉴스별 요약, 시장 흐름 분석, 투자 전략 제안
- **자동 저장**: TXT 및 DOCX(워드) 파일로 저장
- **자동 실행**: GitHub Actions를 통한 매일 오전 5시 자동 실행

## 🛠️ GitHub 설정 방법

이 저장소를 본인의 GitHub에 올린 후 다음 설정을 완료해야 합니다:

1. **GitHub Secrets 설정**:
   - 저장소의 `Settings` > `Secrets and variables` > `Actions`로 이동합니다.
   - `New repository secret` 버튼을 클릭합니다.
   - **Name**: `GEMINI_API_KEY`
   - **Value**: 본인의 Google AI Studio API 키를 입력합니다.

2. **자동 실행 확인**:
   - 상단 `Actions` 탭에서 "Daily Real Estate News Bot" 워크플로우가 정상적으로 작동하는지 확인하세요.
   - `Run workflow` 버튼을 눌러 즉시 실행해 볼 수도 있습니다.

## 📂 저장 위치
분석 리포트는 `reports/` 폴더 내에 일자별로 저장됩니다.

---
제작: Antigravity AI
