import json
import datetime
import requests
from bs4 import BeautifulSoup
import re

# 日本時間 (JST) タイムスタンプ
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
now_str = now.strftime("%Y/%m/%d %H:%M JST")
today_date = now.date()

print(f"[{now_str}] ポケモンGO最新攻略データの自動収集を開始します...")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 既存データのロード（バックアップ用）
try:
    with open("data.json", "r", encoding="utf-8") as f:
        current_data = json.load(f)
except Exception:
    current_data = {"events": [], "latest_news": []}

latest_news = []
events = []

# =============================================================================
# 1. GameWith から最新速報ニュースを自動抽出
# =============================================================================
try:
    gw_res = requests.get("https://pokemongo.gamewith.jp/", headers=headers, timeout=10)
    if gw_res.status_code == 200:
        soup = BeautifulSoup(gw_res.text, "html.parser")
        for tag in soup.select(".article-list-item a, .news-feed a")[:6]:
            title = tag.get_text(strip=True)
            link = tag.get("href", "#")
            if title and len(title) > 6:
                latest_news.append({"title": title, "link": link})
except Exception as e:
    print(f"ニュース取得スキップ: {e}")

if not latest_news:
    latest_news = current_data.get("latest_news", [])

# =============================================================================
# 2. ポケマピ / GameWith イベントスケジュールからイベント＆日程を自動抽出
# =============================================================================
try:
    # ポケマピのイベントカレンダーページを巡回
    sched_res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if sched_res.status_code == 200:
        soup = BeautifulSoup(sched_res.text, "html.parser")
        event_cards = soup.select(".event_item, .event_card, .article_card, .event-list li")

        for card in event_cards:
            title_tag = card.select_one(".event_title, .title, a")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if not title or len(title) < 4:
                continue

            date_text = ""
            date_tag = card.select_one(".event_date, .date, .time")
            if date_tag:
                date_text = date_tag.get_text(strip=True)

            # 日付解析ロジック (例: 10/24(土) 14:00 〜 10/24(土) 17:00 等)
            dates = re.findall(r'(\d{1,2})/(\d{1,2})', date_text)
            if dates:
                start_month, start_day = int(dates[0][0]), int(dates[0][1])
                if len(dates) >= 2:
                    end_month, end_day = int(dates[1][0]), int(dates[1][1])
                else:
                    end_month, end_day = start_month, start_day

                start_date_str = f"2026-{start_month:02d}-{start_day:02d}"
                end_date_str = f"2026-{end_month:02d}-{end_day:02d}"
            else:
                start_month, start_day = now.month, now.day
                end_month, end_day = now.month, now.day
                start_date_str = now.strftime("%Y-%m-%d")
                end_date_str = now.strftime("%Y-%m-%d")

            # カテゴリの自動判定
            cat = "main"
            bar_class = "bar-main"
            if any(k in title for k in ["レイド", "パルキア", "ギラティナ", "ランドロス", "メガ"]):
                cat = "raid"
                bar_class = "bar-raid"
            elif any(k in title for k in ["ダイマックス", "マックスバトル", "キョダイ", "UMA", "ユクシー"]):
                cat = "dmax"
                bar_class = "bar-dmax"
            elif any(k in title for k in ["コラボ", "FCソウル", "プロ野球", "イオン"]):
                cat = "collab"
                bar_class = "bar-collab"
            elif any(k in title for k in ["GBL", "リーグ", "バトル"]):
                cat = "gbl"
                bar_class = "bar-gbl"

            ev_id = "ev-auto-" + re.sub(r'[^a-zA-Z0-9]', '', title)[:12]

            events.append({
                "id": ev_id,
                "month": start_month,
                "title": title,
                "barClass": bar_class,
                "category": cat,
                "startDay": start_day,
                "endDay": end_day,
                "startDate": start_date_str,
                "endDate": end_date_str,
                "dateText": date_text if date_text else f"{start_month}/{start_day}〜{end_month}/{end_day}",
                "summary": "攻略サイトより自動取得した最新イベント情報です。",
                "bonuses": [],
                "wilds": [],
                "raids": [],
                "tasks": []
            })
except Exception as e:
    print(f"スケジュール自動スクレイピング例外: {e}")

# スクレイピングで拾えなかった場合のフォールバック（既存の手動マスタからマージ）
if len(events) < 3:
    events = current_data.get("events", [])

# =============================================================================
# 3. 過去イベントの自動仕分け・クリーンアップ（過去1ヶ月キープ、30日超破棄）
# =============================================================================
cleaned_events = []
for ev in events:
    end_str = ev.get("endDate")
    if end_str:
        try:
            end_d = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
            diff_days = (today_date - end_d).days
            if diff_days > 30:
                print(f"30日以上経過のため自動消去: {ev.get('title')}")
                continue
        except Exception:
            pass
    cleaned_events.append(ev)

# =============================================================================
# 4. data.json へ最新情報を一括保存
# =============================================================================
output_data = {
    "updated_at": now_str,
    "latest_news": latest_news,
    "events": cleaned_events
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output_data, f, ensure_ascii=False, indent=2)

print(f"[{now_str}] 全データの自動更新と30日ライフサイクル処理が完了しました。")
