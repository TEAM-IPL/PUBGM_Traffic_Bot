#!/usr/bin/env python3
"""
뉴스 수집 스크립트 (최적화 버전)
- RSS 수집 → 스마트 필터링 → 단계별 AI 정제
- 무료 API (Gemini, Groq) + 유료 API (OpenAI, Claude) 조합
"""

import os
import sys
import json
import csv
import feedparser
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import time
import logging
import hashlib

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 프로젝트 루트 디렉토리
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
SCRIPTS_DIR = PROJECT_ROOT / 'scripts'
KEYWORDS_FILE = SCRIPTS_DIR / 'keywords.json'
NEWS_CSV = DATA_DIR / 'news.csv'
CACHE_FILE = DATA_DIR / 'news_cache.json'

# 환경 변수 로드 (로컬 개발 환경)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
    logger.info("로컬 환경: .env 파일에서 환경 변수 로드")
except ImportError:
    logger.info("GitHub Actions 환경: os.getenv 사용")


# ============================================================
# API 우선순위 및 비용 설정
# ============================================================
API_PRIORITY = {
    'free': ['groq', 'gemini'],  # 무료 API 우선
    'paid': ['openai', 'claude']  # 유료 API는 선택적
}

API_COSTS = {
    'groq': 0,       # 무료
    'gemini': 0,     # 무료 티어
    'openai': 0.0001,  # GPT-4o-mini per request
    'claude': 0.003    # Claude per request
}


def load_keywords() -> Dict:
    """키워드 설정 파일 로드"""
    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"키워드 파일을 찾을 수 없습니다: {KEYWORDS_FILE}")
        return {
            "base_keywords": ["PUBG Mobile"],
            "country_keywords": {},
            "categories": ["gaming"]
        }
    except json.JSONDecodeError:
        logger.error("키워드 파일 JSON 파싱 오류")
        return {"base_keywords": ["PUBG Mobile"], "country_keywords": {}, "categories": ["gaming"]}


def get_continent(country: str) -> str:
    """국가명으로 대륙 반환"""
    continent_map = {
        'USA': 'NORTH AMERICA', 'Canada': 'NORTH AMERICA', 'Mexico': 'NORTH AMERICA',
        'Brazil': 'SOUTH AMERICA', 'Argentina': 'SOUTH AMERICA',
        'Germany': 'EUROPE', 'UK': 'EUROPE', 'France': 'EUROPE', 'Italy': 'EUROPE', 'Spain': 'EUROPE',
        'China': 'ASIA', 'India': 'ASIA', 'Japan': 'ASIA', 'Korea': 'ASIA', 'South Korea': 'ASIA',
        'South Africa': 'AFRICA', 'Egypt': 'AFRICA', 'Nigeria': 'AFRICA',
        'Australia': 'OCEANIA', 'New Zealand': 'OCEANIA',
        'Russia': 'RUSSIA & CIS'
    }
    return continent_map.get(country, 'OTHER')


def map_to_group_category(detail_category: str) -> str:
    """
    세부 카테고리를 그룹 카테고리로 매핑
    
    Args:
        detail_category: 세부 카테고리 (예: internet_shutdown, war_conflict 등)
    
    Returns:
        그룹 카테고리 (outage_block, social_crisis, seasonal_calendar, gaming_competitor, other)
    """
    # 🔴 장애 및 차단 (Outage & Block)
    outage_block = [
        'internet_shutdown', 'tech_outage', 'power_outage', 'censorship',
        'cyber_attack', 'infrastructure_damage'
    ]
    
    # 🟠 사회적 위기 (Social Crisis)
    social_crisis = [
        'war_conflict', 'terrorism_explosion', 'natural_disaster',
        'protest_strike', 'curfew', 'pandemic', 'economic'
    ]
    
    # 🟢 시즌 및 일정 (Seasonal & Calendar)
    seasonal_calendar = [
        'holiday', 'school_calendar', 'election'
    ]
    
    # 🔵 게임 및 경쟁 (Gaming & Competitor)
    gaming_competitor = [
        'gaming', 'competitor_game', 'social_trend', 'sports_event', 'major_event'
    ]
    
    if detail_category in outage_block:
        return 'outage_block'
    elif detail_category in social_crisis:
        return 'social_crisis'
    elif detail_category in seasonal_calendar:
        return 'seasonal_calendar'
    elif detail_category in gaming_competitor:
        return 'gaming_competitor'
    else:
        return 'other'


# ============================================================
# 캐싱 시스템
# ============================================================

def get_cache_key(text: str) -> str:
    """텍스트에서 캐시 키 생성"""
    return hashlib.md5(text.encode()).hexdigest()[:16]


def load_cache() -> Dict:
    """캐시 파일 로드"""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"캐시 로드 실패: {e}")
    return {}


def save_cache(cache: Dict):
    """캐시 파일 저장"""
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"캐시 저장 실패: {e}")


# ============================================================
# 무료 API: Groq (Llama 3.1)
# ============================================================

def fetch_from_groq(news_items: List[Dict], batch_size: int = 5) -> List[Dict]:
    """
    Groq API로 뉴스 배치 분석 (무료, 초고속)
    - Llama 3.1 70B 사용
    - 분당 30회, 일 14,400회 무료
    
    API 키 발급: https://console.groq.com/
    """
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        logger.info("GROQ_API_KEY 없음 - Groq 스킵")
        return news_items
    
    try:
        import requests
        
        results = []
        for i in range(0, len(news_items), batch_size):
            batch = news_items[i:i+batch_size]
            
            # 배치 프롬프트 생성
            news_text = "\n".join([
                f"{j+1}. 제목: {item.get('title', '')}\n   요약: {item.get('summary', '')[:200]}"
                for j, item in enumerate(batch)
            ])
            
            prompt = f"""다음 {len(batch)}개 뉴스를 분석해주세요. 각 뉴스에 대해 JSON 배열로 응답해주세요.

{news_text}

각 뉴스에 대해:
- category: 카테고리 (gaming, holiday, war_conflict, natural_disaster, internet_shutdown, protest_strike, economic, other 중 하나)
- traffic_impact: 모바일 게임 트래픽에 미치는 영향 (한국어로 1-2문장)
- relevant: 관련성 (true/false)

JSON 배열만 응답하세요:
[{{"id": 1, "category": "...", "traffic_impact": "...", "relevant": true}}, ...]"""

            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "You are a news analyst. Return only valid JSON array."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1000
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content']
                
                # JSON 추출
                import re
                json_match = re.search(r'\[[\s\S]*\]', content)
                if json_match:
                    analysis = json.loads(json_match.group())
                    
                    for j, item in enumerate(batch):
                        if j < len(analysis):
                            item['category'] = analysis[j].get('category', item.get('category', 'other'))
                            item['traffic_impact'] = analysis[j].get('traffic_impact', '')
                            item['api_source'] = 'groq'
                            if not analysis[j].get('relevant', True):
                                item['skip'] = True
                        results.append(item)
                else:
                    results.extend(batch)
            else:
                logger.warning(f"Groq API 오류: {response.status_code}")
                results.extend(batch)
            
            time.sleep(0.5)  # Rate limit 방지
        
        logger.info(f"Groq 분석 완료: {len(results)}개")
        return results
        
    except Exception as e:
        logger.error(f"Groq API 호출 실패: {e}")
        return news_items


# ============================================================
# 네이버 검색 API (국내 뉴스) - 엄격한 필터링 적용
# ============================================================

# 광고/마케팅/관련없는 뉴스 제외 키워드
NEGATIVE_KEYWORDS = [
    # 마케팅/광고
    '캠페인', '프로모션', '이벤트', '출시', '신제품', '할인', '세일', '팝업', '콜라보',
    'campaign', 'promotion', 'launch', 'sale', 'popup', 'collaboration',
    # 연예/엔터
    '걸그룹', '보이그룹', '아이돌', '콘서트', '앨범', '뮤직비디오', '팬미팅',
    # 음식/브랜드
    '던킨', '스타벅스', '맥도날드', '버거킹', '엠앤엠', '초콜릿', '커피',
    # 기타 비관련
    '패션', '뷰티', '화장품', '의류', '쇼핑'
]

# 게임 관련 필수 키워드 (PUBGM 관련/경쟁 게임만)
GAMING_REQUIRED_KEYWORDS = [
    # PUBG 직접 관련
    'pubg', '펍지', '배틀그라운드', '크래프톤', 'krafton', 'bgmi',
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

# 트래픽 영향 필수 키워드 (실제 영향을 주는 이벤트만)
TRAFFIC_IMPACT_KEYWORDS = {
    'disaster': ['지진 발생', '지진 피해', '태풍 상륙', '태풍 피해', '홍수 피해', '폭우 피해',
                 'earthquake hit', 'typhoon damage', 'flood damage'],
    'conflict': ['전쟁 발발', '군사 충돌', '폭탄 테러', '무력 충돌', '미사일 공격',
                 'war outbreak', 'military conflict', 'bombing', 'missile attack'],
    'outage': ['인터넷 차단', '통신 장애', '정전 사태', '서비스 장애', '접속 장애',
               'internet shutdown', 'network outage', 'power outage', 'service down'],
    'holiday': ['국경일', '공휴일 지정', '연휴 시작', '명절 연휴', '휴일 확정',
                'national holiday', 'public holiday announced', 'holiday begins']
}

def is_relevant_news(title: str, description: str) -> tuple:
    """
    뉴스의 관련성을 판단하고 카테고리를 반환
    Returns: (is_relevant, news_type, category, priority)
    """
    text = f"{title} {description}".lower()
    
    # 1. 네거티브 키워드 체크 - 광고/마케팅 제외
    for neg_kw in NEGATIVE_KEYWORDS:
        if neg_kw.lower() in text:
            return (False, None, None, None)
    
    # 2. 게임 뉴스 체크 (명확한 게임 키워드 필수)
    for game_kw in GAMING_REQUIRED_KEYWORDS:
        if game_kw.lower() in text:
            return (True, 'gaming', 'gaming', 'medium')
    
    # 3. 트래픽 영향 뉴스 체크 (구체적인 이벤트 키워드 필수)
    for category, keywords in TRAFFIC_IMPACT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                priority = 'high' if category in ['disaster', 'conflict', 'outage'] else 'medium'
                return (True, 'traffic_impact', category, priority)
    
    # 4. 어디에도 해당 안 됨 - 제외
    return (False, None, None, None)


def fetch_from_naver(keywords: List[str], max_results: int = 50) -> List[Dict]:
    """
    네이버 검색 API로 국내 뉴스 검색 (엄격한 필터링)
    - 일 25,000회 무료
    - 국내 300+ 언론사 커버
    - 관련 없는 뉴스 자동 제외
    
    API 발급: https://developers.naver.com/
    """
    client_id = os.getenv('NAVER_CLIENT_ID')
    client_secret = os.getenv('NAVER_CLIENT_SECRET')
    
    if not client_id or not client_secret:
        logger.info("NAVER API 키 없음 - 네이버 스킵")
        return []
    
    try:
        import requests
        import urllib.parse
        
        results = []
        filtered_count = 0
        
        for keyword in keywords[:15]:  # 최대 15개 키워드
            try:
                response = requests.get(
                    f"https://openapi.naver.com/v1/search/news.json",
                    params={
                        "query": keyword,
                        "display": 10,  # 최대 10개
                        "sort": "date"  # 최신순
                    },
                    headers={
                        "X-Naver-Client-Id": client_id,
                        "X-Naver-Client-Secret": client_secret
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    
                    for item in items:
                        # HTML 태그 제거
                        title = item.get('title', '').replace('<b>', '').replace('</b>', '')
                        description = item.get('description', '').replace('<b>', '').replace('</b>', '')
                        
                        # 관련성 검사 (엄격한 필터링)
                        is_relevant, news_type, category, priority = is_relevant_news(title, description)
                        
                        if not is_relevant:
                            filtered_count += 1
                            continue  # 관련 없는 뉴스 제외
                        
                        # 날짜 파싱 (RFC 2822 형식)
                        pub_date = item.get('pubDate', '')
                        try:
                            from email.utils import parsedate_to_datetime
                            dt = parsedate_to_datetime(pub_date)
                            date_str = dt.strftime('%Y-%m-%d')
                        except:
                            date_str = datetime.now().strftime('%Y-%m-%d')
                        
                        news_item = {
                            'date': date_str,
                            'country': 'Korea',
                            'continent': 'ASIA',
                            'title': title,
                            'summary': description[:500],
                            'url': item.get('originallink') or item.get('link', ''),
                            'source': '네이버 뉴스',
                            'category': category,
                            'news_type': news_type,
                            'priority': priority,
                            'api_source': 'naver'
                        }
                        
                        results.append(news_item)
                    
                    logger.info(f"네이버 '{keyword}': {len(items)}개 중 관련 뉴스만 수집")
                else:
                    logger.warning(f"네이버 API 오류: {response.status_code} - {response.text[:100]}")
                
                time.sleep(0.1)  # Rate limit (초당 10회 제한)
                
            except Exception as e:
                logger.error(f"네이버 '{keyword}' 검색 실패: {e}")
                continue
        
        # 중복 제거
        seen_urls = set()
        unique_results = []
        for item in results:
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                unique_results.append(item)
        
        logger.info(f"네이버 총 수집: {len(unique_results)}개 (필터링 제외: {filtered_count}개)")
        return unique_results[:max_results]
        
    except Exception as e:
        logger.error(f"네이버 API 호출 실패: {e}")
        return []


# ============================================================
# DeepSearch News API (국내/해외 고품질 뉴스)
# ============================================================

def fetch_from_deepsearch(keywords: List[str], countries: List[str] = None, max_results: int = 50) -> List[Dict]:
    """
    DeepSearch News API로 고품질 뉴스 검색
    - 국내: 조선, 한겨레, 동아 등
    - 해외: NYT, BBC, Washington Post, CNN 등
    
    API 문서: https://api-v2.deepsearch.com
    """
    api_key = os.getenv('DEEPSEARCH_API_KEY')
    if not api_key:
        logger.info("DEEPSEARCH_API_KEY 없음 - DeepSearch 스킵")
        return []
    
    try:
        import requests
        from datetime import datetime, timedelta
        
        results = []
        
        # 날짜 범위 (최근 24시간)
        date_to = datetime.now().strftime('%Y-%m-%d')
        date_from = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        for keyword in keywords[:10]:  # 최대 10개 키워드
            try:
                # 해외 뉴스 검색 (global-articles)
                response = requests.get(
                    "https://api-v2.deepsearch.com/v1/global-articles",
                    params={
                        "api_key": api_key,
                        "keyword": keyword,
                        "date_from": date_from,
                        "date_to": date_to,
                        "page_size": 10,
                        "page": 1
                    },
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    articles = data.get('data', [])
                    
                    for article in articles:
                        news_item = {
                            'date': article.get('published_at', '')[:10] if article.get('published_at') else date_to,
                            'country': None,
                            'continent': None,
                            'title': article.get('title', ''),
                            'summary': article.get('summary', '')[:500],
                            'url': article.get('url', ''),
                            'source': article.get('publisher', 'DeepSearch'),
                            'category': 'other',
                            'news_type': 'traffic_impact',
                            'priority': 'high',
                            'api_source': 'deepsearch'
                        }
                        
                        # 국가 추론 (키워드에서)
                        if countries:
                            for country in countries:
                                if country.lower() in keyword.lower() or country.lower() in news_item['title'].lower():
                                    news_item['country'] = country
                                    news_item['continent'] = get_continent(country)
                                    break
                        
                        results.append(news_item)
                    
                    logger.info(f"DeepSearch '{keyword}': {len(articles)}개 수집")
                else:
                    logger.warning(f"DeepSearch API 오류: {response.status_code}")
                
                time.sleep(0.5)  # Rate limit
                
            except Exception as e:
                logger.error(f"DeepSearch 키워드 '{keyword}' 검색 실패: {e}")
                continue
        
        # 중복 제거 (URL 기준)
        seen_urls = set()
        unique_results = []
        for item in results:
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                unique_results.append(item)
        
        logger.info(f"DeepSearch 총 수집: {len(unique_results)}개 (중복 제거됨)")
        return unique_results[:max_results]
        
    except Exception as e:
        logger.error(f"DeepSearch API 호출 실패: {e}")
        return []


def fetch_trending_from_deepsearch(sections: List[str] = None) -> List[Dict]:
    """
    DeepSearch에서 트렌딩 토픽 가져오기
    - 해외 주요 이슈 자동 수집
    """
    api_key = os.getenv('DEEPSEARCH_API_KEY')
    if not api_key:
        return []
    
    try:
        import requests
        
        sections = sections or ['world', 'business', 'technology']
        results = []
        
        for section in sections:
            try:
                response = requests.get(
                    f"https://api-v2.deepsearch.com/v1/global-articles/topics/{section}/trending",
                    params={
                        "api_key": api_key,
                        "page_size": 5
                    },
                    timeout=15
                )
                
                if response.status_code == 200:
                    data = response.json()
                    topics = data.get('data', [])
                    
                    for topic in topics:
                        news_item = {
                            'date': topic.get('date', '')[:10] if topic.get('date') else '',
                            'country': None,
                            'continent': None,
                            'title': topic.get('title', '') or topic.get('title_kr', ''),
                            'summary': topic.get('briefing', '')[:500],
                            'url': f"https://deepsearch.com/topic/{topic.get('id', '')}",
                            'source': 'DeepSearch Trending',
                            'category': 'major_event',
                            'news_type': 'traffic_impact',
                            'priority': 'high',
                            'api_source': 'deepsearch_trending'
                        }
                        results.append(news_item)
                    
                    logger.info(f"DeepSearch Trending '{section}': {len(topics)}개")
                    
            except Exception as e:
                logger.error(f"DeepSearch Trending '{section}' 실패: {e}")
                continue
            
            time.sleep(0.3)
        
        return results
        
    except Exception as e:
        logger.error(f"DeepSearch Trending 실패: {e}")
        return []


# ============================================================
# 단계별 AI 정제 (최적화)
# ============================================================

def smart_refine_batch(news_items: List[Dict], use_paid_api: bool = False) -> List[Dict]:
    """
    스마트 배치 정제
    1단계: Groq (무료, 빠름) - 기본 분류 + 요약
    2단계: OpenAI/Claude (유료, 선택적) - 상위 10개 최종 검증
    """
    if not news_items:
        return []
    
    logger.info(f"스마트 정제 시작: {len(news_items)}개")
    
    # 캐시 로드
    cache = load_cache()
    cached_count = 0
    to_process = []
    
    for item in news_items:
        cache_key = get_cache_key(item.get('title', '') + item.get('url', ''))
        if cache_key in cache:
            # 캐시에서 결과 복원
            cached = cache[cache_key]
            item.update(cached)
            cached_count += 1
        else:
            to_process.append(item)
    
    if cached_count > 0:
        logger.info(f"캐시에서 {cached_count}개 복원")
    
    if not to_process:
        return news_items
    
    # 1단계: Groq으로 빠른 분류 (무료, 초고속)
    groq_key = os.getenv('GROQ_API_KEY')
    if groq_key:
        logger.info("1단계: Groq (Llama 3.1)으로 빠른 분류...")
        to_process = fetch_from_groq(to_process)
    
    # 2단계: 유료 API (선택적, 상위 10개만)
    if use_paid_api:
        openai_key = os.getenv('OPENAI_API_KEY')
        claude_key = os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        
        if openai_key or claude_key:
            # HIGH priority 중 상위 10개만 유료 API로 검증
            high_priority = [n for n in to_process if n.get('priority') == 'high']
            top_news = high_priority[:10]
            
            if top_news:
                logger.info(f"2단계: 유료 API로 심층 분석 ({len(top_news)}개)...")
                
                for item in top_news:
                    api_type = 'openai' if openai_key else 'claude'
                    refined = refine_news_with_ai(item, api_type)
                    if refined:
                        item.update(refined)
                        item['api_source'] = api_type
                    time.sleep(0.5)
    
    # 캐시 업데이트
    for item in to_process:
        cache_key = get_cache_key(item.get('title', '') + item.get('url', ''))
        cache[cache_key] = {
            'category': item.get('category'),
            'category_group': item.get('category_group'),
            'traffic_impact': item.get('traffic_impact'),
            'api_source': item.get('api_source')
        }
    
    save_cache(cache)
    
    # category_group 매핑
    for item in news_items:
        if not item.get('category_group'):
            item['category_group'] = map_to_group_category(item.get('category', 'other'))
    
    logger.info(f"스마트 정제 완료: {len(news_items)}개")
    return news_items


# ============================================================
# 스마트 필터링 (HIGH/MEDIUM/LOW Priority)
# ============================================================

# HIGH Priority 키워드 (AI 정제 필수 - 트래픽 영향 뉴스)
HIGH_PRIORITY_KEYWORDS = {
    'critical': [
        'internet shutdown', 'blackout', 'power outage', 'outage',
        'war', 'explosion', 'bombing', 'attack', 'terrorism', 'terrorist',
        'earthquake', 'flood', 'disaster', 'emergency', 'tsunami', 'typhoon',
        'curfew', 'protest', 'riot', 'strike', 'unrest',
        'shutdown', 'ban', 'block', 'censorship'
    ],
    'countries': [
        'Iraq', 'Pakistan', 'Turkey', 'Russia', 'Egypt',
        'Saudi Arabia', 'Indonesia', 'Hong Kong', 'Iran', 'Syria',
        'Baghdad', 'Karachi', 'Istanbul', 'Moscow', 'Cairo', 'Jakarta'
    ]
}

# MEDIUM Priority 키워드 (규칙 기반 자동 분류) - 더 엄격한 게임 키워드
MEDIUM_RULES = {
    'gaming': [
        # PUBG/Krafton 관련 (필수)
        'PUBG', 'pubg mobile', 'battlegrounds mobile', 'Krafton', 'BGMI',
        'PMGC', 'PMPL', 'pubg esports',
        # 경쟁작
        'Free Fire', 'Call of Duty Mobile', 'COD Mobile',
        # 게임 업계 (구체적인 키워드만)
        'mobile game revenue', 'mobile game update', 'game patch',
        'esports tournament', 'e-sports championship',
        # 한국어
        '펍지', '배틀그라운드', '크래프톤', '모바일게임 매출', '게임 업데이트'
    ],
    'holiday': [
        # 실제 공휴일만 (마케팅 제외)
        'national holiday', 'public holiday', 'bank holiday',
        'Eid al-Fitr', 'Eid al-Adha', 'Christmas Day', 'New Year Day',
        'Ramadan begins', 'Diwali celebration',
        '국경일', '공휴일', '명절 연휴', '추석', '설날'
    ],
    'school': [
        # 학사일정
        'school holiday', 'school vacation', 'exam period', 'semester break',
        'summer vacation', 'winter vacation',
        '방학 시작', '시험 기간', '개학'
    ]
}

# LOW Priority (제외할 패턴) - 확장된 네거티브 키워드
# ※ protest/시위는 트래픽 영향 있으므로 제외하지 않음!
# ※ KT는 통신장애 뉴스에 필요하므로 'KT 위즈'로 구체화!
# ※ 월드컵/올림픽은 트래픽 영향 있으므로 제외하지 않음!
EXCLUDE_PATTERNS = [
    # ========== 광고/마케팅 (강화) ==========
    '광고', 'sponsored', 'affiliate', 'promotion', '프로모션',
    '캠페인', 'campaign', '팝업', 'popup', '콜라보', 'collaboration',
    '출시', 'launch', '신제품', '할인', 'sale', '세일',
    '협찬', '마케팅', 'PPL', '보도자료', 'branded content',
    
    # ========== 금융/증시/투자 (강화) ==========
    '주식', '증시', '코스피', '코스닥', '나스닥',
    '장중', '장 마감', '장 초반', '마감 지수',
    '주가', '주식시장', '투자자', '기관투자자',
    '증권사', '증권가', '리포트', '리서치센터',
    '실적발표', '분기 실적', '연간 실적',
    'stock price', 'earnings', 'quarterly earnings', 'annual earnings',
    'investor', '투자', '배당', 'dividend',
    '펀드', 'ETF', '리츠', '재테크', 'IPO', '공모주',
    'IR', 'conference call',
    
    # ========== 채용/커리어 (강화) ==========
    '채용', '공채', '수시채용', '채용 공고',
    '신입사원', '경력직', '인재 채용',
    '구인', '구인 공고',
    'hiring', 'job opening', 'career', 'recruitment',
    'career fair', '채용 설명회', '인턴 모집', '공모전',
    
    # ========== 연예/엔터테인먼트 (강화) ==========
    '걸그룹', '보이그룹', '아이돌', 'idol', 'K-pop',
    '콘서트', 'concert', '앨범', 'album', '뮤직비디오', '팬미팅', 'fan meeting',
    'MAMA', 'Awards', '시상식', 'mourning',
    
    # ========== 연예/OTT/가십 (추가) ==========
    '드라마', '예능', '시청률', '예능 프로그램', '리얼리티쇼',
    'OTT', '넷플릭스', '디즈니+', '티빙', '웨이브', '쿠팡플레이',
    'Netflix', 'Disney+', 'OST',
    '열애설', '결별설', '연예계', '연예인 커플', '스캔들',
    '영화제', '레드카펫', 'celebrity', 'entertainment news', 'showbiz',
    
    # ========== 음식/브랜드 ==========
    '던킨', '스타벅스', '맥도날드', '버거킹', '엠앤엠', 'M&M',
    '초콜릿', '커피', 'coffee', '음료',
    
    # ========== 패션/뷰티 ==========
    '패션', 'fashion', '뷰티', 'beauty', '화장품', 'cosmetic',
    '의류', 'clothing', '쇼핑', 'shopping',
    
    # ========== 군사/방산 ==========
    '자주포', '전차', '미사일', '무기', '군수', '방산', '국방',
    'K9', 'K2', '한화에어로', '한화디펜스', 'defense contract',
    'military contract', 'arms deal', '방위사업',
    'DMZ', 'Korean War soldiers', '유해 발굴', '전사자',
    
    # ========== 정치/외교 (일반) ==========
    '대통령', '국회', '외교부', '장관', '정상회담', 'summit',
    '조약', 'treaty', '협정',
    
    # ========== 스포츠 (e스포츠/월드컵/올림픽 제외) ==========
    # ※ KT 위즈만 제외 (KT 통신장애는 살려야 함!)
    'KT 위즈', 'kt wiz', 'KT위즈',
    '프로축구', '프로야구', 'NBA', 'MLB',
    '야구 결과', '축구 결과', '경기 결과',
    '구원투수', '스토브리그', 'WAR 전체',
    # ※ FIFA/월드컵/올림픽은 트래픽 영향 있으므로 제외하지 않음!
    
    # ========== 부동산/주거 (추가) ==========
    '분양', '청약', '입주자 모집',
    '전세', '월세', '매매', '전월세',
    '전세가', '매매가', '집값', '아파트 단지',
    '오피스텔', '상가 분양', '오피스 임대',
    '부동산 시장', '부동산 규제',
    '부동산', 'real estate', 'housing market',
    
    # ========== 날씨/생활정보 (추가) ==========
    # ※ 대형 자연재해는 트래픽 영향으로 잡으므로 일상 날씨만 제외
    '오늘의 날씨', '주간 날씨', '기상청',
    '기온', '미세먼지', '체감온도',
    '날씨', 'weather forecast', 'weekly forecast',
    
    # ========== 레시피/맛집/생활 (추가) ==========
    '레시피', '요리법', '집밥', '간편식',
    '맛집 탐방', '식당 리뷰', '카페 추천',
    'restaurant review', 'food blog',
    '맛집', 'restaurant', '여행', 'travel tip',
    
    # ========== 시위 - 구체적 케이스만 ==========
    # ※ 일반 protest/시위는 트래픽 영향 있으므로 제외하지 않음!
    'immigration protest', 'hindu protest', 'farmer protest',
]


def classify_news_priority(title: str, summary: str) -> tuple:
    """
    뉴스의 우선순위를 분류 (엄격한 기준)
    
    Args:
        title: 뉴스 제목
        summary: 뉴스 요약
    
    Returns:
        (priority, news_type, auto_category)
        - priority: 'high', 'medium', 'low'
        - news_type: 'traffic_impact', 'gaming', None
        - auto_category: 자동 분류된 카테고리 (medium인 경우)
    """
    text = f"{title} {summary}".lower()
    
    # 1. LOW Priority 체크 (제외) - 광고/마케팅/비관련 뉴스
    for pattern in EXCLUDE_PATTERNS:
        if pattern.lower() in text:
            return ('low', None, None)
    
    # 2. HIGH Priority 체크 (트래픽 영향 뉴스 - AI 정제 대상)
    for keyword in HIGH_PRIORITY_KEYWORDS['critical']:
        if keyword.lower() in text:
            return ('high', 'traffic_impact', None)
    
    for country in HIGH_PRIORITY_KEYWORDS['countries']:
        if country.lower() in text:
            # 국가 언급 + 위기 키워드가 있으면 HIGH
            for keyword in HIGH_PRIORITY_KEYWORDS['critical']:
                if keyword.lower() in text:
                    return ('high', 'traffic_impact', None)
    
    # 3. MEDIUM Priority 체크 (규칙 기반 자동 분류)
    for category, keywords in MEDIUM_RULES.items():
        for keyword in keywords:
            if keyword.lower() in text:
                if category == 'gaming':
                    return ('medium', 'gaming', 'gaming')
                elif category == 'holiday':
                    return ('medium', 'traffic_impact', 'holiday')
                elif category == 'school':
                    return ('medium', 'traffic_impact', 'school_calendar')
    
    # 4. 기본값: LOW (관련 없으면 제외!)
    # 이전: ('medium', 'gaming', 'gaming') - 모든 뉴스가 게임으로 분류됨
    # 수정: ('low', None, None) - 관련 없는 뉴스는 제외
    return ('low', None, None)


def clean_html_tags(text: str) -> str:
    """HTML 태그 제거"""
    import re
    # HTML 태그 제거
    clean = re.sub(r'<[^>]+>', '', text)
    # HTML 엔티티 제거
    clean = re.sub(r'&[a-zA-Z]+;', ' ', clean)
    # 여러 공백을 하나로
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()


def fetch_news_from_openai(keyword: str, countries: List[Dict] = None) -> List[Dict]:
    """
    OpenAI API를 사용하여 뉴스 검색 및 분석
    
    Args:
        keyword: 검색 키워드
        countries: 관련 국가 리스트 (선택사항)
    
    Returns:
        뉴스 리스트
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.warning("OPENAI_API_KEY가 설정되지 않았습니다.")
        return []
    
    try:
        import requests
        
        # 국가 정보 포함
        country_context = ""
        if countries:
            country_names = [c.get('country', '') for c in countries if c.get('country')]
            if country_names:
                country_context = f" 특히 {', '.join(country_names[:5])} 국가와 관련된"
        
        prompt = f"""다음 키워드와 관련된 최신 뉴스를 검색하고 분석해주세요: {keyword}{country_context}

다음 JSON 형식으로 응답해주세요 (최대 10개):
[
  {{
    "title": "뉴스 제목",
    "summary": "요약 (2-3문장)",
    "url": "뉴스 링크 (가능한 경우)",
    "source": "출처",
    "date": "YYYY-MM-DD 형식",
    "country": "관련 국가 (없으면 null)",
    "reason": "트래픽 변화와의 연관성 분석"
  }}
]

최근 7일 이내의 뉴스만 포함하고, PUBG Mobile이나 모바일 게임과 관련된 뉴스만 알려주세요."""

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",  # 또는 "gpt-4", "gpt-3.5-turbo"
                "messages": [
                    {"role": "system", "content": "You are a news analyst. Return only valid JSON array."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 2000
            },
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"OpenAI API 오류: {response.status_code} - {response.text}")
            return []
        
        data = response.json()
        content = data['choices'][0]['message']['content']
        
        # JSON 추출
        import re
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            news_data = json.loads(json_match.group())
            
            # 형식 변환
            news_list = []
            for item in news_data:
                news_list.append({
                    'date': item.get('date', datetime.now().strftime('%Y-%m-%d')),
                    'country': item.get('country'),
                    'continent': get_continent(item.get('country', '')) if item.get('country') else None,
                    'title': item.get('title', ''),
                    'summary': item.get('summary', '')[:500],
                    'url': item.get('url', '#'),
                    'source': item.get('source', 'OpenAI'),
                    'category': 'gaming'
                })
            
            logger.info(f"OpenAI API로 '{keyword}'에서 {len(news_list)}개 뉴스 수집 완료")
            return news_list
        else:
            logger.warning("OpenAI 응답에서 JSON을 찾을 수 없습니다.")
            return []
            
    except Exception as e:
        logger.error(f"OpenAI API 호출 실패: {e}")
        return []


def fetch_news_from_claude(keyword: str, countries: List[Dict] = None) -> List[Dict]:
    """
    Claude API를 사용하여 뉴스 검색 및 분석
    
    Args:
        keyword: 검색 키워드
        countries: 관련 국가 리스트 (선택사항)
    
    Returns:
        뉴스 리스트
    """
    # CLAUDE_API_KEY 또는 ANTHROPIC_API_KEY 지원 (둘 다 동일)
    api_key = os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        logger.warning("CLAUDE_API_KEY 또는 ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return []
    
    try:
        import requests
        
        # 국가 정보 포함
        country_context = ""
        if countries:
            country_names = [c.get('country', '') for c in countries if c.get('country')]
            if country_names:
                country_context = f" 특히 {', '.join(country_names[:5])} 국가와 관련된"
        
        prompt = f"""다음 키워드와 관련된 최신 뉴스를 검색하고 분석해주세요: {keyword}{country_context}

다음 JSON 형식으로 응답해주세요 (최대 10개):
[
  {{
    "title": "뉴스 제목",
    "summary": "요약 (2-3문장)",
    "url": "뉴스 링크 (가능한 경우)",
    "source": "출처",
    "date": "YYYY-MM-DD 형식",
    "country": "관련 국가 (없으면 null)",
    "reason": "트래픽 변화와의 연관성 분석"
  }}
]

최근 7일 이내의 뉴스만 포함하고, PUBG Mobile이나 모바일 게임과 관련된 뉴스만 알려주세요."""

        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            },
            json={
                "model": "claude-3-5-sonnet-20241022",  # 또는 "claude-3-opus-20240229"
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Claude API 오류: {response.status_code} - {response.text}")
            return []
        
        data = response.json()
        content = data['content'][0]['text']
        
        # JSON 추출
        import re
        json_match = re.search(r'\[[\s\S]*\]', content)
        if json_match:
            news_data = json.loads(json_match.group())
            
            # 형식 변환
            news_list = []
            for item in news_data:
                news_list.append({
                    'date': item.get('date', datetime.now().strftime('%Y-%m-%d')),
                    'country': item.get('country'),
                    'continent': get_continent(item.get('country', '')) if item.get('country') else None,
                    'title': item.get('title', ''),
                    'summary': item.get('summary', '')[:500],
                    'url': item.get('url', '#'),
                    'source': item.get('source', 'Claude'),
                    'category': 'gaming'
                })
            
            logger.info(f"Claude API로 '{keyword}'에서 {len(news_list)}개 뉴스 수집 완료")
            return news_list
        else:
            logger.warning("Claude 응답에서 JSON을 찾을 수 없습니다.")
            return []
            
    except Exception as e:
        logger.error(f"Claude API 호출 실패: {e}")
        return []


def fetch_news_from_api(keyword: str, api_type: str = 'rss', countries: List[Dict] = None) -> List[Dict]:
    """
    API를 사용하여 뉴스 가져오기 (확장 가능)
    
    Args:
        keyword: 검색 키워드
        api_type: API 타입 ('rss', 'openai', 'claude', 'gemini' 등)
        countries: 관련 국가 리스트 (선택사항)
    
    Returns:
        뉴스 리스트
    """
    # RSS는 기본으로 사용
    if api_type == 'rss':
        return fetch_news_from_rss(keyword)
    
    # OpenAI API 사용
    elif api_type == 'openai':
        news = fetch_news_from_openai(keyword, countries)
        if news:
            return news
        else:
            logger.info("OpenAI API 실패, RSS로 폴백")
            return fetch_news_from_rss(keyword)
    
    # Claude API 사용
    elif api_type == 'claude':
        news = fetch_news_from_claude(keyword, countries)
        if news:
            return news
        else:
            logger.info("Claude API 실패, RSS로 폴백")
            return fetch_news_from_rss(keyword)
    
    # Gemini API 사용 (API 키 필요)
    elif api_type == 'gemini':
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            logger.warning("GEMINI_API_KEY가 설정되지 않았습니다. RSS를 사용합니다.")
            return fetch_news_from_rss(keyword)
        
        try:
            # Gemini API 호출 로직 (추후 구현)
            logger.info(f"Gemini API 사용 (키워드: {keyword})")
            return []  # TODO: Gemini API 구현
        except Exception as e:
            logger.error(f"Gemini API 호출 실패: {e}")
            return fetch_news_from_rss(keyword)  # 폴백
    
    else:
        logger.warning(f"알 수 없는 API 타입: {api_type}. RSS를 사용합니다.")
        return fetch_news_from_rss(keyword)


def fetch_news_from_rss(keyword: str, max_retries: int = 3) -> List[Dict]:
    """
    Google News RSS에서 뉴스 가져오기
    
    Args:
        keyword: 검색 키워드
        max_retries: 최대 재시도 횟수
    
    Returns:
        뉴스 리스트
    """
    news_list = []
    # URL 인코딩으로 특수문자 처리
    import urllib.parse
    encoded_keyword = urllib.parse.quote(keyword)
    rss_url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=ko&gl=KR&ceid=KR:ko"
    
    for attempt in range(max_retries):
        try:
            # 로그에는 키워드만 표시 (URL 전체는 표시하지 않음)
            logger.info(f"RSS 피드 가져오기 시도 {attempt + 1}/{max_retries}: 키워드='{keyword}'")
            feed = feedparser.parse(rss_url)
            
            if feed.bozo and feed.bozo_exception:
                logger.warning(f"RSS 파싱 경고: {feed.bozo_exception}")
            
            for entry in feed.entries[:10]:  # 최대 10개
                # 날짜 파싱
                try:
                    pub_date = datetime(*entry.published_parsed[:6])
                except (AttributeError, TypeError):
                    pub_date = datetime.now()
                
                # 오늘부터 24시간 이내 뉴스만
                if pub_date < datetime.now() - timedelta(days=1):
                    continue
                
                # HTML 태그 제거
                clean_title = clean_html_tags(entry.get('title', ''))
                clean_summary = clean_html_tags(entry.get('summary', ''))[:500]
                
                # 우선순위 및 뉴스 타입 분류
                priority, news_type, auto_category = classify_news_priority(clean_title, clean_summary)
                
                # LOW priority는 제외
                if priority == 'low':
                    continue
                
                news_item = {
                    'date': pub_date.strftime('%Y-%m-%d'),
                    'country': None,  # 키워드에서 추출
                    'continent': None,
                    'title': clean_title,
                    'summary': clean_summary,
                    'url': entry.get('link', ''),
                    'source': entry.get('source', {}).get('title', 'Google News'),
                    'category': auto_category if auto_category else 'gaming',
                    'news_type': news_type if news_type else 'gaming',
                    'priority': priority
                }
                
                # 국가명 추출 (키워드에서)
                keywords_config = load_keywords()
                priority_countries = keywords_config.get('priority_countries', {})
                for country in priority_countries.keys():
                    if country.lower() in keyword.lower():
                        news_item['country'] = country
                        news_item['continent'] = get_continent(country)
                        break
                
                news_list.append(news_item)
            
            logger.info(f"'{keyword}'에서 {len(news_list)}개 뉴스 수집 완료")
            break  # 성공하면 중단
            
        except Exception as e:
            logger.error(f"RSS 가져오기 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(5)  # 5초 대기 후 재시도
            else:
                logger.error(f"'{keyword}' 키워드로 뉴스 수집 실패")
    
    return news_list


def refine_news_with_ai(news_item: Dict, api_type: str = 'openai') -> Optional[Dict]:
    """
    RSS로 수집한 뉴스를 AI로 정제 (카테고리 분류, 트래픽 영향 분석)
    
    Args:
        news_item: RSS로 수집한 뉴스 아이템
        api_type: 사용할 API ('openai' 또는 'claude')
    
    Returns:
        정제된 뉴스 딕셔너리 또는 None (관련 없음)
    """
    api_key = None
    api_url = None
    headers = {}
    payload = {}
    
    if api_type == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return news_item  # API 키 없으면 원본 반환
        
        api_url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""다음 뉴스를 분석하여 모바일 게임 트래픽에 영향을 줄 수 있는지 판단해주세요:

제목: {news_item.get('title', '')}
내용: {news_item.get('summary', '')}
URL: {news_item.get('url', '')}

다음 JSON 형식으로 응답해주세요:
{{
  "relevant": true 또는 false (모바일 게임 트래픽에 영향을 줄 수 있으면 true),
  "category": "세부 카테고리 중 하나 (아래 목록 참고)",
  "country": "관련 국가명 (없으면 null)",
  "traffic_impact": "트래픽에 미치는 영향 설명 (간단히)",
  "summary_kr": "한국어로 2-3줄 요약"
}}

세부 카테고리 목록 (정확히 하나 선택):

🔴 장애 및 차단 (Outage & Block):
- internet_shutdown: 인터넷 차단, 통신 장애
- tech_outage: 소셜미디어/앱스토어/클라우드 장애
- power_outage: 정전, 전력 공급 중단
- censorship: 검열, 앱/게임 금지
- cyber_attack: 사이버 공격, DDoS, 해킹
- infrastructure_damage: 인프라 손상, 교량/건물 붕괴

🟠 사회적 위기 (Social Crisis):
- war_conflict: 전쟁, 분쟁, 군사 작전
- terrorism_explosion: 테러, 폭발, 폭탄 공격
- natural_disaster: 지진, 홍수, 태풍, 산불 등 천재지변
- protest_strike: 시위, 파업, 폭동
- curfew: 통금, 봉쇄, 비상사태
- pandemic: 팬데믹, 전염병, 격리
- economic: 경제 위기, 인플레이션, 통화 평가절하

🟢 시즌 및 일정 (Seasonal & Calendar):
- holiday: 공휴일, 명절, 축제
- school_calendar: 방학, 시험기간 등 학사일정
- election: 선거, 투표, 정치 이벤트

🔵 게임 및 경쟁 (Gaming & Competitor):
- gaming: 게임 관련 뉴스
- competitor_game: 경쟁 게임 출시/업데이트
- social_trend: 바이럴 트렌드, 인플루언서, e스포츠 토너먼트
- sports_event: 월드컵, 올림픽 등 스포츠 이벤트
- major_event: 주요 문화 행사, 게임 컨벤션

⚪ 기타:
- other: 분류 불가

관련이 없으면 relevant: false로 설정하세요."""

        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "You are a news analyst. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
    
    elif api_type == 'claude':
        api_key = os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return news_item  # API 키 없으면 원본 반환
        
        api_url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        prompt = f"""다음 뉴스를 분석하여 모바일 게임 트래픽에 영향을 줄 수 있는지 판단해주세요:

제목: {news_item.get('title', '')}
내용: {news_item.get('summary', '')}
URL: {news_item.get('url', '')}

다음 JSON 형식으로 응답해주세요:
{{
  "relevant": true 또는 false (모바일 게임 트래픽에 영향을 줄 수 있으면 true),
  "category": "세부 카테고리 중 하나 (아래 목록 참고)",
  "country": "관련 국가명 (없으면 null)",
  "traffic_impact": "트래픽에 미치는 영향 설명 (간단히)",
  "summary_kr": "한국어로 2-3줄 요약"
}}

세부 카테고리 목록 (정확히 하나 선택):

🔴 장애 및 차단 (Outage & Block):
- internet_shutdown: 인터넷 차단, 통신 장애
- tech_outage: 소셜미디어/앱스토어/클라우드 장애
- power_outage: 정전, 전력 공급 중단
- censorship: 검열, 앱/게임 금지
- cyber_attack: 사이버 공격, DDoS, 해킹
- infrastructure_damage: 인프라 손상, 교량/건물 붕괴

🟠 사회적 위기 (Social Crisis):
- war_conflict: 전쟁, 분쟁, 군사 작전
- terrorism_explosion: 테러, 폭발, 폭탄 공격
- natural_disaster: 지진, 홍수, 태풍, 산불 등 천재지변
- protest_strike: 시위, 파업, 폭동
- curfew: 통금, 봉쇄, 비상사태
- pandemic: 팬데믹, 전염병, 격리
- economic: 경제 위기, 인플레이션, 통화 평가절하

🟢 시즌 및 일정 (Seasonal & Calendar):
- holiday: 공휴일, 명절, 축제
- school_calendar: 방학, 시험기간 등 학사일정
- election: 선거, 투표, 정치 이벤트

🔵 게임 및 경쟁 (Gaming & Competitor):
- gaming: 게임 관련 뉴스
- competitor_game: 경쟁 게임 출시/업데이트
- social_trend: 바이럴 트렌드, 인플루언서, e스포츠 토너먼트
- sports_event: 월드컵, 올림픽 등 스포츠 이벤트
- major_event: 주요 문화 행사, 게임 컨벤션

⚪ 기타:
- other: 분류 불가

관련이 없으면 relevant: false로 설정하세요."""

        payload = {
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 500,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
    
    else:
        return news_item  # 알 수 없는 API 타입이면 원본 반환
    
    try:
        import requests
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            logger.warning(f"AI API 오류: {response.status_code}, 원본 뉴스 사용")
            return news_item
        
        data = response.json()
        
        # 응답에서 텍스트 추출
        if api_type == 'openai':
            content = data['choices'][0]['message']['content']
        else:  # claude
            content = data['content'][0]['text']
        
        # JSON 추출
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            ai_result = json.loads(json_match.group())
            
            # 관련 없으면 None 반환
            if not ai_result.get('relevant', False):
                return None
            
            # 세부 카테고리
            detail_category = ai_result.get('category', 'other')
            
            # 정제된 정보 병합
            refined_item = {
                **news_item,
                'category': detail_category,  # 세부 카테고리 저장
                'category_group': map_to_group_category(detail_category),  # 그룹 카테고리 추가
                'summary': ai_result.get('summary_kr', news_item.get('summary', '')),
                'traffic_impact': ai_result.get('traffic_impact', '')
            }
            
            # 국가 정보 업데이트
            if ai_result.get('country'):
                refined_item['country'] = ai_result.get('country')
                refined_item['continent'] = get_continent(ai_result.get('country'))
            
            return refined_item
        else:
            logger.warning("AI 응답에서 JSON을 찾을 수 없습니다. 원본 사용")
            return news_item
            
    except Exception as e:
        logger.error(f"AI 정제 실패: {e}, 원본 뉴스 사용")
        return news_item


def cross_validate_news(openai_news: List[Dict], claude_news: List[Dict]) -> List[Dict]:
    """
    OpenAI와 Claude API 결과를 교차검증하여 신뢰도 높은 뉴스 반환
    
    Args:
        openai_news: OpenAI API로 수집한 뉴스
        claude_news: Claude API로 수집한 뉴스
    
    Returns:
        교차검증된 뉴스 리스트 (신뢰도 점수 포함)
    """
    validated_news = []
    seen_titles = set()
    
    # 제목 유사도 비교 함수 (간단한 버전)
    def title_similarity(title1: str, title2: str) -> float:
        """두 제목의 유사도 계산 (0.0 ~ 1.0)"""
        title1_lower = title1.lower()
        title2_lower = title2.lower()
        
        # 완전 일치
        if title1_lower == title2_lower:
            return 1.0
        
        # 단어 기반 유사도
        words1 = set(title1_lower.split())
        words2 = set(title2_lower.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    # OpenAI 뉴스 처리
    for news in openai_news:
        title = news.get('title', '').lower()
        if title in seen_titles:
            continue
        
        # Claude 결과와 비교
        matched = False
        best_match_score = 0.0
        best_match = None
        
        for claude_item in claude_news:
            claude_title = claude_item.get('title', '').lower()
            similarity = title_similarity(title, claude_title)
            
            if similarity > 0.7:  # 70% 이상 유사하면 일치로 간주
                matched = True
                if similarity > best_match_score:
                    best_match_score = similarity
                    best_match = claude_item
        
        if matched and best_match:
            # 두 API가 일치하는 뉴스: 신뢰도 높음
            validated_item = news.copy()
            validated_item['confidence'] = 'high'
            validated_item['validation'] = f"OpenAI + Claude 일치 (유사도: {best_match_score:.0%})"
            validated_item['openai_summary'] = news.get('summary', '')
            validated_item['claude_summary'] = best_match.get('summary', '')
            # 더 긴 요약 사용
            if len(best_match.get('summary', '')) > len(news.get('summary', '')):
                validated_item['summary'] = best_match.get('summary', '')
            validated_news.append(validated_item)
            seen_titles.add(title)
            seen_titles.add(best_match.get('title', '').lower())
        else:
            # OpenAI만 찾은 뉴스: 신뢰도 중간
            validated_item = news.copy()
            validated_item['confidence'] = 'medium'
            validated_item['validation'] = 'OpenAI only'
            validated_news.append(validated_item)
            seen_titles.add(title)
    
    # Claude만 찾은 뉴스 추가
    for news in claude_news:
        title = news.get('title', '').lower()
        if title not in seen_titles:
            validated_item = news.copy()
            validated_item['confidence'] = 'medium'
            validated_item['validation'] = 'Claude only'
            validated_news.append(validated_item)
            seen_titles.add(title)
    
    # 신뢰도 순으로 정렬 (high > medium)
    validated_news.sort(key=lambda x: (x.get('confidence') == 'high', x.get('title', '')))
    
    logger.info(f"교차검증 완료: 총 {len(validated_news)}개 (High: {sum(1 for n in validated_news if n.get('confidence') == 'high')}, Medium: {sum(1 for n in validated_news if n.get('confidence') == 'medium')})")
    
    return validated_news


def fetch_news_with_cross_validation(keyword: str, countries: List[Dict] = None) -> List[Dict]:
    """
    OpenAI와 Claude API를 모두 사용하여 교차검증
    
    Args:
        keyword: 검색 키워드
        countries: 관련 국가 리스트
    
    Returns:
        교차검증된 뉴스 리스트
    """
    logger.info(f"교차검증 시작: {keyword}")
    
    # 두 API 모두 호출
    openai_news = fetch_news_from_openai(keyword, countries)
    time.sleep(1)  # API 부하 방지
    claude_news = fetch_news_from_claude(keyword, countries)
    
    # 교차검증
    if openai_news or claude_news:
        validated = cross_validate_news(openai_news, claude_news)
        return validated
    else:
        # 둘 다 실패 시 RSS 폴백
        logger.warning("OpenAI와 Claude 모두 실패, RSS로 폴백")
        return fetch_news_from_rss(keyword)


def remove_duplicates(existing_news: List[Dict], new_news: List[Dict]) -> List[Dict]:
    """
    중복 뉴스 제거 (URL 기준)
    
    Args:
        existing_news: 기존 뉴스 리스트
        new_news: 새로 수집한 뉴스 리스트
    
    Returns:
        중복 제거된 새 뉴스 리스트
    """
    existing_urls = {news['url'] for news in existing_news if news.get('url')}
    unique_news = [news for news in new_news if news.get('url') not in existing_urls]
    
    logger.info(f"중복 제거: {len(new_news)}개 중 {len(unique_news)}개 유니크")
    return unique_news


def load_existing_news() -> List[Dict]:
    """기존 CSV 파일에서 뉴스 로드"""
    if not NEWS_CSV.exists():
        logger.info("기존 뉴스 파일이 없습니다. 새로 생성합니다.")
        return []
    
    try:
        df = pd.read_csv(NEWS_CSV, encoding='utf-8-sig')
        return df.to_dict('records')
    except Exception as e:
        logger.error(f"기존 뉴스 파일 읽기 실패: {e}")
        return []


def save_to_csv(all_news: List[Dict]):
    """
    뉴스를 CSV 파일로 저장
    
    Args:
        all_news: 저장할 뉴스 리스트
    """
    if not all_news:
        logger.warning("저장할 뉴스가 없습니다.")
        return
    
    try:
        # 데이터 디렉토리 생성
        DATA_DIR.mkdir(exist_ok=True)
        
        # DataFrame 생성
        df = pd.DataFrame(all_news)
        
        # 컬럼 순서 지정 (news_type 및 교차검증 컬럼 포함)
        base_columns = ['date', 'country', 'continent', 'title', 'summary', 'url', 'source', 'category', 'category_group', 'news_type', 'traffic_impact']
        optional_columns = ['priority', 'confidence', 'validation', 'openai_summary', 'claude_summary']
        
        # 모든 컬럼 확인
        all_columns = base_columns + [col for col in optional_columns if col in df.columns]
        df = df.reindex(columns=all_columns)
        
        # 날짜순 정렬 (최신순)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date', ascending=False)
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        
        # CSV 저장 (UTF-8 with BOM for Excel compatibility)
        df.to_csv(NEWS_CSV, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_MINIMAL)
        
        logger.info(f"뉴스 {len(all_news)}개를 {NEWS_CSV}에 저장했습니다.")
        
    except Exception as e:
        logger.error(f"CSV 저장 실패: {e}")
        raise


def main():
    """메인 함수 - 스마트 필터링 적용"""
    logger.info("=" * 50)
    logger.info("뉴스 수집 시작 (RSS + DeepSearch + AI 정제)")
    logger.info("=" * 50)
    
    # 사용 가능한 API 확인
    apis_available = []
    if os.getenv('DEEPSEARCH_API_KEY'):
        apis_available.append('DeepSearch')
    if os.getenv('GROQ_API_KEY'):
        apis_available.append('Groq')
    if os.getenv('OPENAI_API_KEY'):
        apis_available.append('OpenAI')
    if os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY'):
        apis_available.append('Claude')
    
    logger.info(f"사용 가능한 API: {', '.join(apis_available) if apis_available else 'RSS만 사용'}")
    
    try:
        # 키워드 로드
        keywords_config = load_keywords()
        base_keywords = keywords_config.get('base_keywords', [])
        gaming_keywords = keywords_config.get('gaming_keywords', {})
        priority_countries = keywords_config.get('priority_countries', {})
        traffic_impact_keywords = keywords_config.get('traffic_impact_keywords', {})
        
        # 기존 뉴스 로드
        existing_news = load_existing_news()
        logger.info(f"기존 뉴스: {len(existing_news)}개")
        
        all_raw_news = []
        
        # ============================================================
        # 0단계: DeepSearch로 고품질 글로벌 뉴스 수집 (선택적)
        # ============================================================
        if os.getenv('DEEPSEARCH_API_KEY'):
            logger.info("=" * 50)
            logger.info("0단계: DeepSearch 고품질 글로벌 뉴스 수집...")
            logger.info("=" * 50)
            
            # 트래픽 영향 키워드로 검색
            deepsearch_keywords = [
                "internet shutdown", "power outage", "earthquake",
                "war conflict", "protest", "holiday", "gaming mobile"
            ]
            
            # 주요 국가 리스트
            country_list = list(priority_countries.keys())
            
            deepsearch_news = fetch_from_deepsearch(deepsearch_keywords, country_list, max_results=30)
            all_raw_news.extend(deepsearch_news)
            
            # 트렌딩 토픽도 수집
            trending_news = fetch_trending_from_deepsearch(['world', 'technology'])
            all_raw_news.extend(trending_news)
            
            logger.info(f"DeepSearch 수집 완료: {len(deepsearch_news) + len(trending_news)}개")
        
        # ============================================================
        # 0-B단계: 네이버 검색 API로 국내 뉴스 수집 (선택적)
        # ============================================================
        if os.getenv('NAVER_CLIENT_ID') and os.getenv('NAVER_CLIENT_SECRET'):
            logger.info("=" * 50)
            logger.info("0-B단계: 네이버 국내 뉴스 수집...")
            logger.info("=" * 50)
            
            # 국내 뉴스 검색 키워드
            naver_keywords = [
                "PUBG 모바일", "펍지 모바일", "배틀그라운드 모바일",
                "크래프톤", "모바일 게임",
                "인터넷 장애", "통신 장애",
                "지진 속보", "태풍 속보"
            ]
            
            naver_news = fetch_from_naver(naver_keywords, max_results=30)
            all_raw_news.extend(naver_news)
            
            logger.info(f"네이버 수집 완료: {len(naver_news)}개")
        
        # ============================================================
        # 1단계: 게임 뉴스 수집 (gaming_keywords)
        # ============================================================
        logger.info("=" * 50)
        logger.info("1단계: 게임 뉴스 수집 중...")
        logger.info("=" * 50)
        
        # 기본 PUBG 키워드
        for keyword in base_keywords:
            news = fetch_news_from_rss(keyword)
            for item in news:
                item['news_type'] = 'gaming'
            all_raw_news.extend(news)
            time.sleep(0.5)
        
        # 게임 키워드 (각 카테고리당 2개씩)
        for category, keywords in gaming_keywords.items():
            for keyword in keywords[:2]:
                news = fetch_news_from_rss(keyword)
                for item in news:
                    item['news_type'] = 'gaming'
                    item['category'] = 'gaming' if category in ['pubg', 'krafton', 'esports'] else 'competitor_game'
                all_raw_news.extend(news)
                time.sleep(0.5)
        
        gaming_count = len(all_raw_news)
        logger.info(f"게임 뉴스 수집 완료: {gaming_count}개")
        
        # ============================================================
        # 2단계: 트래픽 영향 뉴스 수집 (주요 국가 + 위기 키워드)
        # ============================================================
        logger.info("=" * 50)
        logger.info("2단계: 트래픽 영향 뉴스 수집 중...")
        logger.info("=" * 50)
        
        # 주요 국가별 검색
        for country, country_info in priority_countries.items():
            # 국가 키워드 (최대 1개)
            for keyword in country_info.get('keywords', [])[:1]:
                news = fetch_news_from_rss(keyword)
                for item in news:
                    item['country'] = country
                    item['continent'] = get_continent(country)
                all_raw_news.extend(news)
                time.sleep(0.5)
            
            # 국가별 주제 키워드 (최대 2개)
            for topic in country_info.get('topics', [])[:2]:
                keyword = f"{country} {topic}"
                news = fetch_news_from_rss(keyword)
                for item in news:
                    item['country'] = country
                    item['continent'] = get_continent(country)
                all_raw_news.extend(news)
                time.sleep(0.5)
        
        # 트래픽 영향 키워드 (각 카테고리당 1개, 총 15개)
        keyword_count = 0
        max_traffic_keywords = 15
        for category, keywords in traffic_impact_keywords.items():
            if keyword_count >= max_traffic_keywords:
                break
            for keyword in keywords[:1]:
                if keyword_count >= max_traffic_keywords:
                    break
                news = fetch_news_from_rss(keyword)
                all_raw_news.extend(news)
                keyword_count += 1
                time.sleep(0.5)
        
        traffic_count = len(all_raw_news) - gaming_count
        logger.info(f"트래픽 영향 뉴스 수집 완료: {traffic_count}개")
        logger.info(f"총 RSS 수집: {len(all_raw_news)}개")
        
        # ============================================================
        # 3단계: 스마트 필터링 및 분류
        # ============================================================
        logger.info("=" * 50)
        logger.info("3단계: 스마트 필터링 중...")
        logger.info("=" * 50)
        
        high_priority_news = []
        medium_priority_news = []
        
        for news_item in all_raw_news:
            priority = news_item.get('priority', 'medium')
            
            if priority == 'high':
                high_priority_news.append(news_item)
            else:
                # MEDIUM: 규칙 기반 자동 분류 완료
                if not news_item.get('category_group'):
                    news_item['category_group'] = map_to_group_category(news_item.get('category', 'gaming'))
                medium_priority_news.append(news_item)
        
        logger.info(f"HIGH Priority (AI 정제 대상): {len(high_priority_news)}개")
        logger.info(f"MEDIUM Priority (규칙 기반): {len(medium_priority_news)}개")
        
        # ============================================================
        # 4단계: 스마트 AI 정제 (무료 API 우선)
        # ============================================================
        logger.info("=" * 50)
        logger.info("4단계: 스마트 AI 정제 시작...")
        logger.info("=" * 50)
        
        # 사용 가능한 API 확인
        available_apis = []
        if os.getenv('GROQ_API_KEY'):
            available_apis.append('Groq (무료)')
        if os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'):
            available_apis.append('Gemini (무료)')
        if os.getenv('OPENAI_API_KEY'):
            available_apis.append('OpenAI (유료)')
        if os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY'):
            available_apis.append('Claude (유료)')
        
        if available_apis:
            logger.info(f"사용 가능한 API: {', '.join(available_apis)}")
        else:
            logger.info("API 키 없음 - 규칙 기반 분류만 사용")
        
        # 유료 API 사용 여부 (환경 변수로 제어)
        use_paid = os.getenv('USE_PAID_API', 'false').lower() == 'true'
        
        # 스마트 정제 실행 (HIGH Priority만)
        all_refined_news = smart_refine_batch(high_priority_news, use_paid_api=use_paid)
        
        # skip 표시된 뉴스 제거
        all_refined_news = [n for n in all_refined_news if not n.get('skip')]
        
        # MEDIUM Priority 뉴스 추가 (규칙 기반 분류)
        for item in medium_priority_news:
            if not item.get('category_group'):
                item['category_group'] = map_to_group_category(item.get('category', 'gaming'))
        all_refined_news.extend(medium_priority_news)
        
        logger.info(f"총 처리된 뉴스: {len(all_refined_news)}개")
        
        # 뉴스 타입별 통계
        gaming_final = sum(1 for n in all_refined_news if n.get('news_type') == 'gaming')
        traffic_final = sum(1 for n in all_refined_news if n.get('news_type') == 'traffic_impact')
        logger.info(f"  - 🎮 게임 뉴스: {gaming_final}개")
        logger.info(f"  - ⚡ 트래픽 영향 뉴스: {traffic_final}개")
        
        # 중복 제거
        unique_new_news = remove_duplicates(existing_news, all_refined_news)
        
        # 기존 뉴스와 합치기
        all_news = existing_news + unique_new_news
        
        # 저장
        if unique_new_news:
            save_to_csv(all_news)
            logger.info(f"✅ {len(unique_new_news)}개의 새 뉴스를 추가했습니다.")
            
            # ============================================================
            # 5단계: AI 요약 생성
            # ============================================================
            logger.info("=" * 50)
            logger.info("5단계: 트래픽 영향 AI 요약 생성...")
            logger.info("=" * 50)
            
            # 최근 24시간 뉴스만 요약 대상
            now = datetime.now()
            recent_news = [
                n for n in all_news 
                if n.get('published_date') and 
                (now - datetime.fromisoformat(n['published_date'].replace('Z', '+00:00').replace('+00:00', ''))).days < 1
            ]
            
            if not recent_news:
                recent_news = all_news[:50]  # fallback
            
            generate_traffic_summary(recent_news)
            
            return 0  # 성공 (변경사항 있음)
        else:
            logger.info("새로운 뉴스가 없습니다.")
            
            # 뉴스가 없어도 요약은 갱신
            logger.info("기존 뉴스로 요약 갱신...")
            generate_traffic_summary(existing_news[:50] if existing_news else [])
            
            return 1  # 변경사항 없음
            
    except Exception as e:
        logger.error(f"뉴스 수집 중 오류 발생: {e}", exc_info=True)
        return -1  # 실패


def generate_traffic_summary(news_list: List[Dict]) -> Dict:
    """
    트래픽 영향 뉴스에 대한 AI 요약 생성
    - 모바일 게임 트래픽 전문가 관점
    - Groq API 사용 (무료)
    """
    SUMMARY_FILE = DATA_DIR / 'summary.json'
    
    # 트래픽 영향 뉴스만 필터링
    traffic_news = [n for n in news_list if n.get('news_type') == 'traffic_impact']
    
    # 제외 키워드 (트래픽과 무관한 뉴스)
    exclude_keywords = [
        'mama', 'awards', '시상식', 'concert', '콘서트', 'idol', '아이돌',
        '광고', '캠페인', '프로모션', '증시', '코스피', '채용', '분양',
        'immigration protest', 'hindu protest', 'farmer protest'
    ]
    
    # 필터링된 뉴스
    filtered_news = []
    seen_titles = set()
    for news in traffic_news:
        title = (news.get('title') or '').lower()
        title_key = title[:30]
        
        # 중복 체크
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        
        # 제외 키워드 체크
        if any(kw in title for kw in exclude_keywords):
            continue
            
        filtered_news.append(news)
    
    logger.info(f"요약 대상 뉴스: {len(filtered_news)}개 (전체 트래픽 뉴스: {len(traffic_news)}개)")
    
    if not filtered_news:
        summary_data = {
            'generated_at': datetime.now().isoformat(),
            'news_count': 0,
            'has_issues': False,
            'summary': '✅ 특이사항 없음\n\n최근 24시간 동안 모바일 게임 트래픽에 영향을 줄 만한 주요 이슈가 감지되지 않았습니다.',
            'affected_countries': [],
            'key_issues': []
        }
        
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        logger.info("요약 생성 완료: 특이사항 없음")
        return summary_data
    
    # 유효한 국가만 추출 (NaN, None, 'Unknown' 제외)
    def get_valid_countries(news_list):
        countries = []
        for n in news_list:
            country = n.get('country')
            if country and str(country) not in ['nan', 'NaN', 'Unknown', 'None', '']:
                countries.append(country)
        return list(set(countries))
    
    # Groq API로 요약 생성
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        logger.warning("GROQ_API_KEY 없음 - 기본 요약 생성")
        summary_data = {
            'generated_at': datetime.now().isoformat(),
            'news_count': len(filtered_news),
            'has_issues': True,
            'summary': f'트래픽 영향 뉴스 {len(filtered_news)}건이 감지되었습니다.',
            'affected_countries': get_valid_countries(filtered_news),
            'key_issues': [{'title': n.get('title', '')[:80], 'country': n.get('country', '')} for n in filtered_news[:5]]
        }
        
        with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        return summary_data
    
    try:
        import requests
        
        # 뉴스 텍스트 준비 (최대 5개로 줄임)
        news_items = []
        for n in filtered_news[:5]:
            country = n.get('country', '')
            if str(country) in ['nan', 'NaN', 'Unknown', 'None', '']:
                country = '글로벌'
            title = n.get('title', '')[:60]
            news_items.append(f"[{country}] {title}")
        
        news_text = "\n".join(news_items)
        
        prompt = f"""아래 뉴스를 분석해 모바일 게임 트래픽 영향을 요약해줘.

{news_text}

요청:
1. 핵심 영향 2-3문장
2. 국가별 예상 영향 1문장씩
3. 간결한 한국어로"""

        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "모바일 게임 트래픽 전문가. 간결하게 한국어로 답변."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 500
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            ai_summary = data['choices'][0]['message']['content']
            
            # 영향 국가 추출 (유효한 국가만)
            affected_countries = get_valid_countries(filtered_news)
            
            # key_issues 생성 (NaN 처리)
            key_issues = []
            for n in filtered_news[:5]:
                country = n.get('country', '')
                if str(country) in ['nan', 'NaN', 'Unknown', 'None', '']:
                    country = ''
                key_issues.append({
                    'title': n.get('title', '')[:80],
                    'country': country,
                    'category': n.get('category', 'other')
                })
            
            summary_data = {
                'generated_at': datetime.now().isoformat(),
                'news_count': len(filtered_news),
                'has_issues': True,
                'summary': ai_summary,
                'affected_countries': affected_countries,
                'key_issues': key_issues
            }
            
            logger.info("AI 요약 생성 완료")
        else:
            logger.warning(f"Groq API 오류: {response.status_code} - {response.text[:200]}")
            
            # key_issues 생성 (NaN 처리)
            key_issues = []
            for n in filtered_news[:5]:
                country = n.get('country', '')
                if str(country) in ['nan', 'NaN', 'Unknown', 'None', '']:
                    country = ''
                key_issues.append({
                    'title': n.get('title', '')[:80],
                    'country': country
                })
            
            summary_data = {
                'generated_at': datetime.now().isoformat(),
                'news_count': len(filtered_news),
                'has_issues': True,
                'summary': f'트래픽 영향 뉴스 {len(filtered_news)}건이 감지되었습니다. (API 오류로 상세 분석 불가)',
                'affected_countries': get_valid_countries(filtered_news),
                'key_issues': key_issues
            }
    
    except Exception as e:
        logger.error(f"요약 생성 오류: {e}")
        summary_data = {
            'generated_at': datetime.now().isoformat(),
            'news_count': len(filtered_news),
            'has_issues': True,
            'summary': f'트래픽 영향 뉴스 {len(filtered_news)}건 감지됨. (요약 생성 오류)',
            'affected_countries': [],
            'key_issues': []
        }
    
    # 저장
    with open(SUMMARY_FILE, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"요약 저장 완료: {SUMMARY_FILE}")
    return summary_data


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)

