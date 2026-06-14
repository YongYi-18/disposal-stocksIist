#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions 專用：抓取處置股資料 → 儲存 data.json
由 .github/workflows/update-data.yml 自動執行，不需手動操作
"""

import json, re, urllib.request
from datetime import datetime, date, timezone, timedelta

TWSE_URL = "https://openapi.twse.com.tw/v1/announcement/punish"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"
TZ_TW    = timezone(timedelta(hours=8))

# ── 抓取 ──────────────────────────────────────────────────────────────────

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json'
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f'[錯誤] {url}: {e}')
        return None

# ── 日期 ──────────────────────────────────────────────────────────────────

WEEKDAY_CN = ['一', '二', '三', '四', '五', '六', '日']

def roc_to_date(y, m, d):
    try:
        return date(int(y) + 1911, int(m), int(d))
    except Exception:
        return None

def parse_dates_twse(period):
    matches = re.findall(r'(\d+)/(\d+)/(\d+)', period)
    dates = [roc_to_date(y, m, d) for y, m, d in matches]
    return (dates[0] if len(dates) > 0 else None,
            dates[1] if len(dates) > 1 else None)

def parse_dates_tpex(period):
    matches = re.findall(r'(\d{3})(\d{2})(\d{2})', period)
    dates = [roc_to_date(y, m, d) for y, m, d in matches]
    return (dates[0] if len(dates) > 0 else None,
            dates[1] if len(dates) > 1 else None)

def fmt_date_wd(d):
    if d is None:
        return '-'
    return f'{d.year}/{d.month:02d}/{d.day:02d}({WEEKDAY_CN[d.weekday()]})'

def fmt_period(sd, ed):
    return f'{fmt_date_wd(sd)} ～ {fmt_date_wd(ed)}'

def days_left(end_date):
    return (end_date - date.today()).days if end_date else None

# ── 撮合週期 ──────────────────────────────────────────────────────────────

CN_NUM = {
    '六十':60,'五十五':55,'五十':50,'四十五':45,'四十':40,'三十五':35,
    '三十':30,'二十九':29,'二十八':28,'二十七':27,'二十六':26,'二十五':25,
    '二十四':24,'二十三':23,'二十二':22,'二十一':21,'二十':20,
    '十九':19,'十八':18,'十七':17,'十六':16,'十五':15,
    '十四':14,'十三':13,'十二':12,'十一':11,'十':10,
    '九':9,'八':8,'七':7,'六':6,'五':5,'四':4,'三':3,'二':2,'一':1
}

def extract_cycle(text):
    if not text:
        return '-'
    m = re.search(r'每[隔約\s]*(\d+|[一二三四五六七八九十]+)\s*分鐘撮合', text)
    if m:
        raw = m.group(1)
        n = CN_NUM.get(raw, raw)
        return (str(int(n)) if str(n).isdigit() else str(n)) + '分鐘'
    return '隨機' if '隨機' in text else '-'

# ── 主程式 ────────────────────────────────────────────────────────────────

def main():
    stocks = []
    errors = []

    # 上市
    twse_raw = fetch_json(TWSE_URL)
    if twse_raw is None:
        errors.append('上市')
    else:
        for item in twse_raw:
            p = item.get('DispositionPeriod', '')
            sd, ed = parse_dates_twse(p)
            d = days_left(ed)
            det = item.get('Detail', '') or ''
            stocks.append({
                'market':   '上市',
                'code':     item.get('Code', ''),
                'name':     item.get('Name', ''),
                'cycle':    extract_cycle(det),
                'days':     d,
                'days_s':   d if d is not None else 9999,
                'period':   fmt_period(sd, ed),
                'reasons':  item.get('ReasonsOfDisposition', ''),
                'measures': item.get('DispositionMeasures', ''),
                'detail':   det,
            })

    # 上櫃
    tpex_raw = fetch_json(TPEX_URL)
    if tpex_raw is None:
        errors.append('上櫃')
    else:
        for item in tpex_raw:
            p_raw = item.get('DispositionPeriod', '')
            sd, ed = parse_dates_tpex(p_raw)
            d = days_left(ed)
            det = item.get('DisposalCondition', '') or ''
            stocks.append({
                'market':   '上櫃',
                'code':     item.get('SecuritiesCompanyCode', ''),
                'name':     item.get('CompanyName', ''),
                'cycle':    extract_cycle(det),
                'days':     d,
                'days_s':   d if d is not None else 9999,
                'period':   fmt_period(sd, ed),
                'reasons':  item.get('DispositionReasons', ''),
                'measures': '',
                'detail':   det,
            })

    if not stocks:
        print('兩個 API 皆失敗，保留現有 data.json 不覆蓋')
        return

    stocks.sort(key=lambda x: (0 if x['market'] == '上市' else 1, x['code']))

    now_tw = datetime.now(TZ_TW).strftime('%Y-%m-%d %H:%M')
    data = {
        'stocks':     stocks,
        'updated_at': now_tw + ' (台灣時間)',
        'total':      len(stocks),
        'twse':       sum(1 for s in stocks if s['market'] == '上市'),
        'tpex':       sum(1 for s in stocks if s['market'] == '上櫃'),
        'errors':     errors,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"完成：上市 {data['twse']} 筆、上櫃 {data['tpex']} 筆，時間 {now_tw}")
    if errors:
        print(f"警告：以下資料來源失敗 → {', '.join(errors)}")


if __name__ == '__main__':
    main()
