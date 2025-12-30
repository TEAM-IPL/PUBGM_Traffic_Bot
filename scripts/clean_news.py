"""
news.csv에서 게임/트래픽과 무관한 뉴스를 정리하는 스크립트
"""
import pandas as pd
import os
import re

NEWS_CSV = 'data/news.csv'

# 제외할 키워드 패턴
# ※ 주의: protest/시위는 TRAFFIC_REQUIRED에 있으므로 여기서 제외하면 안됨!
# ※ 주의: KT는 통신장애 뉴스에 필요하므로 'KT 위즈'로 구체화!
EXCLUDE_KEYWORDS = [
    # ========== 군사/방산 ==========
    '자주포', '전차', '미사일', '무기', '군수', '방산', '국방',
    'K9', 'K2', '한화에어로', '한화디펜스', 'defense contract',
    '방위사업', 'military contract', 'arms deal',
    'DMZ', 'Korean War soldiers', '유해 발굴', '전사자',
    
    # ========== 연예/시상식 ==========
    'MAMA', 'Awards', '시상식', 'mourning', 'Hong Kong tragedy',
    'K-pop', 'idol', '아이돌', '걸그룹', '보이그룹',
    '콘서트', '앨범', '팬미팅', '뮤직비디오',
    'concert', 'album', 'fan meeting',
    
    # ========== 연예/OTT/가십 (강화) ==========
    '드라마', '예능', '시청률', '예능 프로그램', '리얼리티쇼', '리얼리티 쇼',
    'OTT', '넷플릭스', '디즈니+', '티빙', '웨이브', '쿠팡플레이',
    'Netflix', 'Disney+', 'OST',
    '열애설', '결별설', '연예계', '연예인 커플', '스캔들',
    '영화제', '레드카펫', 'celebrity', 'entertainment news', 'showbiz',
    
    # ========== 시위 - 구체적 케이스만 ==========
    # ※ 일반 protest/시위는 트래픽 영향 있으므로 제외하지 않음!
    'immigration protest', 'hindu protest', 'farmer protest',
    
    # ========== 정치/법원 ==========
    'PPP', '국민의힘', '더불어민주당', '민주당', '국회',
    'court hearing', '법원', '재판', '탄핵', '대통령',
    'Choo Kyung-ho', '추경호', '이재명', '윤석열', '한동훈',
    'National Assembly', 'impeachment', 'legislature',
    
    # ========== 한국 관련 (글로벌 관점에서 제외) ==========
    '한국', 'South Korea', 'Korea', '북한', 'North Korea',
    '서울', 'Seoul', '부산', '대구', '인천',
    '네이트', 'nate.com',
    
    # ========== e스포츠 ==========
    'esports', 'e-sports', 'e스포츠', '이스포츠',
    'PMGC', 'PMPL', 'PCS', 'PGC', 'tournament', '토너먼트',
    '대회', 'championship', 'league', '리그',
    'pro player', '프로선수', 'pro team', '프로팀',
    
    # ========== 스포츠 (e스포츠/월드컵/올림픽 제외) ==========
    # ※ KT 위즈만 제외 (KT 통신장애는 살려야 함!)
    'KT 위즈', 'kt wiz', 'KT위즈',
    '구원투수', '스토브리그', 'WAR 전체', 'xportsnews',
    '프로축구', '프로야구', 'NBA', 'MLB',
    '야구 결과', '축구 결과', '경기 결과',
    # 배구
    'Spike War', '스파이크 워', '배구', 'volleyball', '발리볼',
    "Kim Yo-han's serve", '서브 리시브', 'receive log',
    'V리그', 'V-League',
    # ※ FIFA/월드컵/올림픽은 트래픽 영향 있으므로 제외하지 않음!
    
    # ========== 사이버보안/APT (정부/기관 대상만 제외) ==========
    # ※ 북한 사이버 공격은 게임 서버 영향 가능성 있어 살림!
    
    # ========== 반도체/경제 (비유적 표현) ==========
    'Chip War', 'SK하이닉스', 'AI 거품론',
    
    # ========== 광고/마케팅 (강화) ==========
    '광고', '협찬', '마케팅', '보도자료', 'PPL',
    '캠페인', 'campaign', '프로모션', 'promotion',
    '팝업', 'popup', '콜라보', 'collaboration', '신제품',
    'sponsored', 'sponsorship', 'affiliate',
    '브랜드 캠페인', '브랜드 콜라보', 'branded content',
    
    # ========== 금융/증시/투자 (강화) ==========
    '증시', '코스피', '코스닥', '나스닥',
    '장중', '장 마감', '장 초반', '마감 지수',
    '주가', '주식시장', '투자자', '기관투자자',
    '증권사', '증권가', '리포트', '리서치센터',
    '실적발표', '분기 실적', '연간 실적',
    'earnings', 'quarterly earnings', 'annual earnings',
    'IR', 'conference call', '배당', 'dividend',
    '펀드', 'ETF', '리츠', '재테크',
    'stock price', 'investor', 'IPO', '공모주',
    
    # ========== 채용/커리어 (강화) ==========
    '채용', '공채', '수시채용', '채용 공고',
    '신입사원', '경력직', '인재 채용',
    '구인', '구인 공고',
    'job opening', 'hiring', 'recruitment',
    'career fair', '채용 설명회', '인턴 모집', '공모전',
    
    # ========== 부동산/주거 (추가) ==========
    '분양', '청약', '입주자 모집',
    '전세', '월세', '매매', '전월세',
    '전세가', '매매가', '집값', '아파트 단지',
    '오피스텔', '상가 분양', '오피스 임대',
    '부동산 시장', '부동산 규제',
    'real estate', 'housing market',
    
    # ========== 날씨/생활정보 (강화) ==========
    # ※ 대형 자연재해는 TRAFFIC_REQUIRED에서 잡으므로 일상 날씨만 제외
    '오늘의 날씨', '주간 날씨', '기상청',
    '기온', '미세먼지', '체감온도',
    'weather forecast', 'weekly forecast',
    
    # ========== 레시피/맛집/생활 (추가) ==========
    '레시피', '요리법', '집밥', '간편식',
    '맛집 탐방', '식당 리뷰', '카페 추천',
    'restaurant review', 'food blog',
    '맛집', 'restaurant', '여행', 'travel tip',
    
    # ========== 음식/브랜드 ==========
    '던킨', '스타벅스', '맥도날드', '버거킹', '엠앤엠', 'M&M',
    '초콜릿', '커피', 'coffee', '음료',
    
    # ========== 패션/뷰티 ==========
    '패션', 'fashion', '뷰티', 'beauty', '화장품', 'cosmetic',
    '의류', 'clothing', '쇼핑', 'shopping',
    
    # ========== 정치/외교 (일반) ==========
    # ※ 계엄/쿠데타 등 위기는 TRAFFIC_REQUIRED에서 잡음
    '대통령', '국회', '외교부', '장관', '정상회담',
]

# 반드시 포함해야 하는 게임 키워드 (PUBGM 관련/경쟁 게임만)
GAMING_REQUIRED = [
    # PUBG 직접 관련
    'pubg', '펍지', '배틀그라운드', 'krafton', '크래프톤', 'bgmi',
    'pmgc', 'pmpl', 'pcs', 'pgc',  # PUBG 대회
    
    # 장르 (FPS/슈터/배틀로얄)
    'fps', 'fps게임', 'fps 게임', '슈터', 'shooter', 
    '배틀로얄', 'battle royale', '배틀 로얄',
    
    # 경쟁 모바일 게임
    'free fire', '프리파이어', '가레나', 'garena',
    'call of duty mobile', 'cod mobile', '콜오브듀티 모바일',
    'apex legends mobile', '에이펙스 레전드 모바일',
    'fortnite mobile', '포트나이트 모바일',
    
    # 경쟁 플랫폼/게임
    'roblox', '로블록스',
    'fortnite', '포트나이트',
    'apex legends', '에이펙스 레전드', '에이펙스',
    
    # 모바일 게임 e스포츠
    'mobile esports', '모바일 e스포츠', '모바일 이스포츠'
]

# 트래픽 영향 키워드 (트래픽 뉴스용)
TRAFFIC_REQUIRED = [
    '인터넷 차단', 'internet shutdown', '통신 장애', 'network outage',
    '정전', 'power outage', '지진', 'earthquake', '태풍', 'typhoon',
    '홍수', 'flood', '전쟁', 'war', '폭발', 'explosion', '테러',
    '공휴일', 'holiday', '연휴', '명절', '방학', '시험',
    '시위', 'protest', '폭동', 'riot', '계엄', 'curfew'
]


def should_exclude(title: str, summary: str) -> bool:
    """뉴스가 제외 대상인지 확인"""
    text = f"{title} {summary}".lower()
    
    for keyword in EXCLUDE_KEYWORDS:
        if keyword.lower() in text:
            return True
    return False


def is_valid_gaming_news(title: str, summary: str) -> bool:
    """유효한 게임 뉴스인지 확인"""
    text = f"{title} {summary}".lower()
    
    for keyword in GAMING_REQUIRED:
        if keyword.lower() in text:
            return True
    return False


def is_valid_traffic_news(title: str, summary: str) -> bool:
    """유효한 트래픽 영향 뉴스인지 확인"""
    text = f"{title} {summary}".lower()
    
    for keyword in TRAFFIC_REQUIRED:
        if keyword.lower() in text:
            return True
    return False


def clean_news():
    if not os.path.exists(NEWS_CSV):
        print(f"Error: {NEWS_CSV} not found.")
        return
    
    df = pd.read_csv(NEWS_CSV, encoding='utf-8-sig')
    original_count = len(df)
    print(f"원본 뉴스 개수: {original_count}")
    
    # 삭제할 인덱스 리스트
    to_remove = []
    
    for idx, row in df.iterrows():
        title = str(row.get('title', ''))
        summary = str(row.get('summary', ''))
        news_type = str(row.get('news_type', ''))
        
        # 1. 제외 키워드 체크
        if should_exclude(title, summary):
            to_remove.append(idx)
            continue
        
        # 2. 게임 뉴스인데 게임 키워드가 없는 경우
        if news_type == 'gaming' and not is_valid_gaming_news(title, summary):
            # 트래픽 영향 뉴스인지 확인
            if is_valid_traffic_news(title, summary):
                # 트래픽 뉴스로 재분류
                df.at[idx, 'news_type'] = 'traffic_impact'
            else:
                to_remove.append(idx)
            continue
        
        # 3. news_type이 비어있는 경우
        if not news_type or news_type == '' or news_type == 'nan':
            if is_valid_gaming_news(title, summary):
                df.at[idx, 'news_type'] = 'gaming'
            elif is_valid_traffic_news(title, summary):
                df.at[idx, 'news_type'] = 'traffic_impact'
            else:
                to_remove.append(idx)
            continue
    
    # 삭제
    df = df.drop(to_remove)
    
    # 저장
    df.to_csv(NEWS_CSV, index=False, encoding='utf-8-sig')
    
    removed_count = len(to_remove)
    final_count = len(df)
    
    print("\n" + "="*50)
    print(f"[OK] Cleaning Complete")
    print(f"   Original: {original_count}")
    print(f"   Removed: {removed_count}")
    print(f"   Final: {final_count}")
    print("="*50)
    
    # 통계
    print("\n[STATS] News Type Distribution:")
    print(df['news_type'].value_counts())


if __name__ == "__main__":
    clean_news()

