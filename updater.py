import json
import datetime
import requests
from bs4 import BeautifulSoup

# 日本時間 (JST) のタイムスタンプ取得
jst = datetime.timezone(datetime.timedelta(hours=9))
now_str = datetime.datetime.now(jst).strftime("%Y/%m/%d %H:%M JST")
print(f"[{now_str}] データの収集と更新を開始します...")

# 既存のデータをベースとして読み込む（ネットワークエラー時の安全対策）
try:
    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    data = {}

# 最終更新日時を記録
data["updated_at"] = now_str

# --- 1. GameWith / ポケマピ / 9DB からのデータ収集（スクレイピング＆フェッチ） ---
# ※Web構造の変化に強いフェイルセーフ設計にしています
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 速報ニュースの自動収集例（GameWith 最新ニュース）
try:
    res = requests.get("https://pokemongo.gamewith.jp/", headers=headers, timeout=10)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        # サイトからニュースの見出しを抽出（見つからなければ既存を維持）
        news_items = []
        for tag in soup.select(".article-list-item a, .news-feed a")[:5]:
            title = tag.get_text(strip=True)
            if title and len(title) > 5:
                news_items.append({"title": title, "link": tag.get("href", "#")})
        if news_items:
            data["latest_news"] = news_items
except Exception as e:
    print(f"GameWith ニュース取得スキップ: {e}")

# --- 2. data.json へ書き出し保存 ---
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("data.json の更新が正常に完了しました。")
