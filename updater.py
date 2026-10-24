import json
import datetime
import requests
from bs4 import BeautifulSoup
import re

jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
now_str = now.strftime("%Y/%m/%d %H:%M JST")
today_date = now.date()

print(f"[{now_str}] 自動更新処理を開始します...")

# 既存のデータを読み込む（安全対策）
try:
    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    data = {"events": [], "raids": {}, "latest_news": []}

data["updated_at"] = now_str

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# --- 1. 速報ニュースの取得 ---
try:
    res = requests.get("https://pokemongo.gamewith.jp/", headers=headers, timeout=10)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        news_items = []
        for tag in soup.select(".article-list-item a, .news-feed a")[:6]:
            title = tag.get_text(strip=True)
            if title and len(title) > 6:
                news_items.append({"title": title, "link": tag.get("href", "#")})
        if news_items:
            data["latest_news"] = news_items
except Exception as e:
    print(f"ニュース取得スキップ: {e}")

# --- 2. 過去イベントの自動仕分け・クリーンアップ（過去1ヶ月キープ） ---
# 終了日から30日以上経過したものは削除、30日以内は保持
cleaned_events = []
for ev in data.get("events", []):
    end_str = ev.get("endDate") # "YYYY-MM-DD" 形式
    if end_str:
        try:
            end_d = datetime.datetime.strptime(end_str, "%Y-%m-%d").date()
            diff_days = (today_date - end_d).days
            if diff_days > 30:
                print(f"30日以上経過のため削除: {ev.get('title')}")
                continue # 30日超えは破棄
        except Exception:
            pass
    cleaned_events.append(ev)

data["events"] = cleaned_events

# --- 3. data.json へ保存 ---
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("data.json の自動更新・古いデータ整理が完了しました。")
