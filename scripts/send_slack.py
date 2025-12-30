"""
PUBGM 트래픽 영향 뉴스를 슬랙으로 발송하는 스크립트
매일 아침 9시 자동 발송용
- AI 요약 기능 포함 (Groq/OpenAI)
"""
import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

NEWS_CSV = 'data/news.csv'

# 트래픽 영향 분석용 키워드 (실제 영향 있는 것만)
IMPACT_KEYWORDS = {
    'high_impact': [
        # 인프라 장애 (확실한 영향)
        'internet shutdown', 'internet outage', 'power outage', 'blackout', 
        '인터넷 차단', '인터넷 장애', '정전', '대규모 정전',
        # 자연재해 (통신 인프라 영향 시)
        'earthquake damage', 'flood damage', 'typhoon damage',
        '지진 피해', '홍수 피해', '태풍 피해', '통신망', '인프라 피해'
    ],
    'medium_impact': [
        # 사회적 혼란 (인터넷 차단 동반 시)
        'curfew', 'martial law', '통금', '계엄',
        # 대규모 공휴일
        'national holiday', '국경일', '연휴'
    ]
}

# 제외할 키워드 (트래픽과 무관)
# ※ protest/시위는 트래픽 영향 있으므로 제외하지 않음!
# ※ KT는 통신장애 뉴스에 필요하므로 'KT 위즈'로 구체화!
EXCLUDE_KEYWORDS = [
    # 연예/시상식/OTT
    'MAMA', 'Awards', '시상식', '콘서트', 'concert', '앨범', 'album',
    'K-pop', 'idol', '아이돌', '걸그룹', '보이그룹', 'mourning',
    '드라마', '예능', '시청률', '넷플릭스', 'Netflix', 
    '열애설', '결별설', '스캔들', '영화제', '레드카펫',
    # 시위 - 구체적 케이스만 제외
    'immigration protest', 'hindu protest', 'farmer protest',
    # 정치/법원
    'PPP', '국민의힘', '더불어민주당', '민주당', '국회',
    'court hearing', '법원', '재판', '탄핵', 'Choo Kyung-ho',
    '추경호', '이재명', '윤석열', '한동훈', 'impeachment',
    # 한국 관련 (글로벌 관점에서 제외)
    '한국', 'South Korea', 'Korea', '북한', 'North Korea',
    '서울', 'Seoul', '네이트', 'nate.com',
    # e스포츠
    'esports', 'e-sports', 'e스포츠', '이스포츠',
    'PMGC', 'PMPL', 'tournament', '토너먼트', '대회',
    'championship', 'league', '리그', '프로선수', '프로팀',
    # 광고/마케팅
    '광고', '협찬', '마케팅', '캠페인', 'campaign', '프로모션',
    'sponsored', 'sponsorship', 'PPL', '보도자료',
    # 금융/증시
    '증시', '코스피', '코스닥', '나스닥', '주가', '장 마감',
    'stock price', 'earnings', 'IPO', '실적발표', '배당',
    # 채용
    '채용', '공채', '구인', 'hiring', 'recruitment',
    # 부동산
    '분양', '청약', '전세', '월세', '매매가', '집값',
    # 날씨/생활 (대형 재해는 TRAFFIC에서 잡음)
    '오늘의 날씨', '미세먼지', '레시피', '맛집',
    # 스포츠 (e스포츠/월드컵/올림픽 제외)
    'KT 위즈', 'kt wiz', '프로야구', '프로축구', 'NBA', 'MLB',
    'Spike War', '스파이크 워', '배구', 'volleyball', 'V리그',
    "Kim Yo-han's serve", '서브 리시브',
    # ※ 북한 사이버 공격은 게임 서버 영향 가능성 있어 살림!
]

# 카테고리 그룹 정보
CATEGORY_INFO = {
    'outage_block': {'icon': '🔴', 'name': '장애/차단', 'color': '#ff4757'},
    'social_crisis': {'icon': '🟠', 'name': '사회 위기', 'color': '#ffa502'},
    'seasonal_calendar': {'icon': '🟢', 'name': '시즌/일정', 'color': '#2ed573'},
    'gaming_competitor': {'icon': '🔵', 'name': '게임/경쟁', 'color': '#5352ed'},
    'other': {'icon': '⚪', 'name': '기타', 'color': '#95a5a6'}
}


def filter_relevant_news(news_list):
    """트래픽과 관련 있는 뉴스만 필터링 (중복 제거 포함)"""
    relevant = []
    seen_titles = set()  # 중복 제거용
    
    for news in news_list:
        title = (news.get('title', '') or '')
        title_lower = title.lower()
        summary = (news.get('summary', '') or '').lower()
        text = f"{title_lower} {summary}"
        
        # 중복 체크 (제목 앞 30자로 판단)
        title_key = title_lower[:30]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        
        # 제외 키워드 체크
        if any(kw.lower() in text for kw in EXCLUDE_KEYWORDS):
            continue
        
        # 영향도 체크 (실제 영향 있는 키워드만)
        impact_level = None
        for level, keywords in IMPACT_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                impact_level = level
                break
        
        if impact_level:
            news['impact_level'] = impact_level
            relevant.append(news)
    
    # 영향도 순으로 정렬 (high > medium)
    priority = {'high_impact': 0, 'medium_impact': 1}
    relevant.sort(key=lambda x: priority.get(x.get('impact_level', 'medium_impact'), 2))
    
    return relevant


def generate_ai_summary(news_list):
    """AI를 사용하여 트래픽 영향 요약 생성 (summary.json 우선 사용)"""
    
    # 먼저 summary.json 확인 (fetch_news.py에서 생성한 상세 요약)
    summary_file = 'data/summary.json'
    if os.path.exists(summary_file):
        try:
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            
            if summary_data.get('has_issues') and summary_data.get('summary'):
                # 마크다운을 슬랙 형식으로 변환
                summary_text = summary_data['summary']
                # **text** -> *text* (슬랙 볼드)
                import re
                summary_text = re.sub(r'\*\*([^*]+)\*\*', r'*\1*', summary_text)
                return summary_text
            elif not summary_data.get('has_issues'):
                return "✅ *특이사항 없음*\n지난 24시간 동안 모바일 게임 트래픽에 영향을 줄 만한 주요 이슈가 감지되지 않았습니다."
        except Exception as e:
            print(f"summary.json 읽기 오류: {e}")
    
    if not news_list:
        return "✅ *특이사항 없음*\n지난 24시간 동안 모바일 게임 트래픽에 영향을 줄 만한 주요 이슈가 감지되지 않았습니다."
    
    # Groq API 사용 (summary.json 없을 때 fallback)
    groq_key = os.getenv('GROQ_API_KEY')
    openai_key = os.getenv('OPENAI_API_KEY')
    
    # 뉴스 요약 텍스트 준비
    news_text = ""
    for i, news in enumerate(news_list[:10]):  # 최대 10개
        title = news.get('title', '')[:100]
        country = news.get('country', 'Unknown')
        impact = news.get('impact_level', 'unknown')
        news_text += f"{i+1}. [{country}] {title} (영향도: {impact})\n"
    
    prompt = f"""뉴스를 보고 모바일 게임 트래픽 영향을 간단히 정리해줘.

{news_text}

작성 규칙:
- 국가별로 한 줄씩, 총 2-3줄 이내
- 자연스러운 한국어로 (번역체 금지)
- 이모지: 🔴 심각, 🟠 주의, 🟢 긍정
- 트래픽 영향 없으면: "✅ 특이사항 없음"

좋은 예시:
🔴 인도네시아 - 홍수 피해로 통신망 불안정, 당분간 접속자 감소 예상
🟠 파키스탄 - 일부 지역 정전, 소폭 하락 가능성

나쁜 예시 (이렇게 쓰지 마):
- "지역 사회가 혼란스럽게 됨" (번역체)
- "트래픽에 영향을 줄 수 있다" (애매함)
- "게임 개발자들은 최적화해야 한다" (불필요)"""

    # Groq API 시도
    if groq_key:
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"Groq API error: {e}")
    
    # OpenAI API 시도
    if openai_key:
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 300,
                    "temperature": 0.3
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip()
        except Exception as e:
            print(f"OpenAI API error: {e}")
    
    # API 없으면 기본 요약 생성
    if news_list:
        high_impact = [n for n in news_list if n.get('impact_level') == 'high_impact']
        if high_impact:
            countries = list(set([n.get('country', 'Unknown') for n in high_impact[:3]]))
            return f"🔴 *주의 필요*\n{', '.join(countries)} 지역에서 트래픽에 영향을 줄 수 있는 이슈가 감지되었습니다. 해당 지역 트래픽 모니터링을 권장합니다."
        else:
            return "🟢 *경미한 이슈*\n일부 뉴스가 감지되었으나 트래픽에 큰 영향은 없을 것으로 예상됩니다."
    
    return "✅ *특이사항 없음*\n지난 24시간 동안 모바일 게임 트래픽에 영향을 줄 만한 주요 이슈가 감지되지 않았습니다."


def get_recent_news(hours=24):
    """최근 N시간 내 뉴스 가져오기"""
    if not os.path.exists(NEWS_CSV):
        return [], []
    
    df = pd.read_csv(NEWS_CSV, encoding='utf-8-sig')
    
    # 날짜 필터링
    cutoff_date = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d')
    df = df[df['date'] >= cutoff_date]
    
    # 타입별 분리
    traffic_news = df[df['news_type'] == 'traffic_impact'].to_dict('records')
    gaming_news = df[df['news_type'] == 'gaming'].to_dict('records')
    
    return traffic_news, gaming_news


def create_slack_message(traffic_news, gaming_news):
    """슬랙 메시지 포맷 생성 - 일일 리포트 형식 (AI 요약 포함)"""
    
    today_short = datetime.now().strftime('%y.%m.%d')
    today_weekday = ['월', '화', '수', '목', '금', '토', '일'][datetime.now().weekday()]
    
    # 관련 뉴스만 필터링
    relevant_news = filter_relevant_news(traffic_news)
    
    # AI 요약 생성
    print("Generating AI summary...")
    ai_summary = generate_ai_summary(relevant_news)
    print("AI Summary generated.")
    
    # 메시지 블록 구성
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📊 [{today_short} {today_weekday}] PUBGM 일일 트래픽 리포트",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "안녕하세요! 일일 리포트 전달드립니다."
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "📊 대시보드",
                    "emoji": True
                },
                "url": "https://sangwonji.github.io/TEST3/",
                "style": "primary"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "*CSV 활용 방법* :point_right: 대시보드 접속 → 파일 선택 → CSV 첨부 → Load CSV\nCSV는 댓글에서 확인 부탁드립니다 :bow:"
                }
            ]
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📈 24시간 뉴스 수집 현황*\n• ⚡ 트래픽 영향: *{len(traffic_news)}건* 수집 → 주요 이슈 *{len(relevant_news)}건*\n• 🎮 게임 뉴스: *{len(gaming_news)}건*"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🥽 GPT + CLAUDE 분석 의견*\n{ai_summary}"
            }
        }
    ]
    
    # 주요 영향 국가 (관련 뉴스가 있을 때만)
    if relevant_news:
        countries = list(set([str(n.get('country', '')) for n in relevant_news if n.get('country') and str(n.get('country', '')) not in ['Unknown', 'nan', '']]))[:5]
        if countries:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"🌍 *주요 영향 국가:* {', '.join(countries)}"
                    }
                ]
            })
    
    return {"blocks": blocks}


def send_to_slack(message):
    """슬랙으로 메시지 발송"""
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    
    if not webhook_url:
        print("Error: SLACK_WEBHOOK_URL not set in .env")
        print("\n[Preview] Message saved to slack_preview.json")
        # 파일로 저장 (인코딩 문제 방지)
        with open('slack_preview.json', 'w', encoding='utf-8') as f:
            json.dump(message, f, ensure_ascii=False, indent=2)
        return False
    
    try:
        response = requests.post(
            webhook_url,
            json=message,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            print("Slack message sent successfully!")
            return True
        else:
            print(f"Slack API error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Error sending to Slack: {e}")
        return False


def main():
    print("="*50)
    print("PUBGM Traffic Report - Slack Sender")
    print("="*50)
    
    # 최근 24시간 뉴스 가져오기
    traffic_news, gaming_news = get_recent_news(hours=24)
    
    print(f"\nTraffic Impact News: {len(traffic_news)}")
    print(f"Gaming News: {len(gaming_news)}")
    
    # 슬랙 메시지 생성
    message = create_slack_message(traffic_news, gaming_news)
    
    # 발송
    send_to_slack(message)


if __name__ == "__main__":
    main()

