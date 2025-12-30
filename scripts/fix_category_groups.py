#!/usr/bin/env python3
"""
기존 CSV 파일의 빈 category_group을 자동으로 채우는 스크립트
"""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
NEWS_CSV = PROJECT_ROOT / 'data' / 'news.csv'

def map_to_group_category(detail_category: str) -> str:
    """세부 카테고리를 그룹 카테고리로 매핑"""
    if not detail_category or pd.isna(detail_category):
        return 'other'
    
    detail_category = str(detail_category).strip().lower()
    
    outage_block = ['internet_shutdown', 'tech_outage', 'power_outage', 'censorship', 'cyber_attack', 'infrastructure_damage']
    social_crisis = ['war_conflict', 'terrorism_explosion', 'natural_disaster', 'protest_strike', 'curfew', 'pandemic', 'economic']
    seasonal_calendar = ['holiday', 'school_calendar', 'election']
    gaming_competitor = ['gaming', 'competitor_game', 'social_trend', 'sports_event', 'major_event']
    
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

def main():
    if not NEWS_CSV.exists():
        print(f"뉴스 파일을 찾을 수 없습니다: {NEWS_CSV}")
        return
    
    # CSV 읽기
    df = pd.read_csv(NEWS_CSV, encoding='utf-8-sig')
    print(f"총 {len(df)}개 뉴스 로드")
    
    # category_group이 비어있거나 없으면 자동 매핑
    if 'category_group' not in df.columns:
        df['category_group'] = None
    
    # 빈 category_group 채우기
    empty_count = df['category_group'].isna().sum() | (df['category_group'] == '').sum()
    print(f"빈 category_group: {empty_count}개")
    
    for idx, row in df.iterrows():
        if pd.isna(row.get('category_group')) or row.get('category_group') == '':
            category = row.get('category', 'other')
            df.at[idx, 'category_group'] = map_to_group_category(category)
    
    # 통계 출력
    print("\n카테고리 그룹별 통계:")
    print(df['category_group'].value_counts())
    
    # 저장
    df.to_csv(NEWS_CSV, index=False, encoding='utf-8-sig')
    print(f"\n[NEWS_CSV] 파일 업데이트 완료")

if __name__ == '__main__':
    main()

