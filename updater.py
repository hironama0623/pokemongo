import os
import json
import datetime
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# 日本時間 (JST)
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
today_date_str = now.strftime("%Y-%m-%d")
now_str = now.strftime("%Y/%m/%d %H:%M JST")
print(f"[{now_str}] 3大サイト（ポケマピ / GameWith / 9DB）巡回＆クロス照合を開始します...")

# 既存データの読み込み
try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {"events": [], "latest_news": []}

existing_news = existing_data.get("latest_news", [])

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

scraped_texts = []

# 1. ポケマピ (イベント一覧・速報)
try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_texts.append("【ポケマピ 最新イベント・ニュース】\n" + soup.get_text(separator="\n", strip=True)[:10000])
except Exception as e:
    print(f"ポケマピ取得スキップ: {e}")

# 2. GameWith (最新イベント速報)
try:
    res = requests.get("https://pokemongo.gamewith.jp/article/show/24434", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_texts.append("【GameWith 最新速報】\n" + soup.get_text(separator="\n", strip=True)[:8000])
except Exception as e:
    print(f"GameWith取得スキップ: {e}")

# 3. 9DB (イベントカレンダー・レイド情報)
try:
    res = requests.get("https://9db.jp/pokego/data/1", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_texts.append("【9DB 最新スケジュール・対策】\n" + soup.get_text(separator="\n", strip=True)[:8000])
except Exception as e:
    print(f"9DB取得スキップ: {e}")

combined_text = "\n\n".join(scraped_texts)

# Gemini API クライアント
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が設定されていません。")
    exit(1)

client = genai.Client(api_key=api_key)

known_titles = [n.get("title", "") for n in existing_news]

prompt = f"""
あなたはポケモンGO攻略情報の検証・構造化を行う専門AIアナリストです。
現在の基準日時（日本時間）: {now_str} (今日の日付: {today_date_str})

提供された「ポケマピ」「GameWith」「9DB」の3サイトのテキストを相互に照合し、情報の整合性を厳格に確認した上で出力してください。

【厳格な整合性・クロスバリデーションルール】
1. 3サイト間で情報が一致している確定情報のみを採用してください。1サイトの誤記や推測、AIの創作ポケモンは絶対に含めないでください。
   （例：ハロウィンパート1にケロマツは出現しません。ケロマツはパート2です。パート1とパート2の内容を混同しないでください）
2. 基準日（{today_date_str}）より前に完全に終了したイベント（10/24終了のUMAマックスバトルデイ等）は「new_news」に含めないでください。
3. ニュース件名は「[日付] 件名」がわかるようにし、クリック時に読める詳細要約（2〜3行）と、連動するイベントID（targetId）を付与してください。
4. 単日イベントは startDay == endDay を厳守してください。

出力スキーマ（純粋なJSONのみ出力）：
{{
  "new_news": [
    {{
      "id": "一意のID",
      "date": "YYYY-MM-DD",
      "date_label": "M/D",
      "title": "ニュース件名",
      "details": "ニュースの詳細要約",
      "targetId": "連動するイベントID（なければ空文字）"
    }}
  ],
  "events": [
    {{
      "id": "一意のID",
      "month": 開始月(数値),
      "title": "イベント名",
      "barClass": "bar-main / bar-raid / bar-dmax / bar-collab / bar-gbl",
      "category": "main / raid / dmax / collab / gbl",
      "startDay": 開始日(数値),
      "endDay": 終了日(数値),
      "startDate": "YYYY-MM-DD",
      "endDate": "YYYY-MM-DD",
      "dateText": "開催日程テキスト",
      "summary": "概要",
      "bonuses": ["ボーナス一覧"],
      "wilds": [{{"dex": 図鑑番号, "name": "名前", "shiny": true/false, "note": "備考"}}],
      "raids": [{{"dex": 図鑑番号, "name": "名前", "shiny": true/false, "note": "備考", "targetKey": "キー", "isDmax": true/false}}],
      "tasks": [{{"task": "タスク内容", "rewardDex": 図鑑番号, "rewardName": "報酬名", "shiny": true/false}}]
    }}
  ]
}}

【3サイト統合テキスト】:
{combined_text}
"""

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    ai_result = json.loads(response.text)
    new_extracted_news = ai_result.get("new_news", [])
    extracted_events = ai_result.get("events", [])

    # マージと重複除外
    all_news_pool = new_extracted_news + existing_news
    seen_ids = set()
    seen_titles = set()
    unique_news = []

    today_dt = now.date()

    for item in all_news_pool:
        nid = item.get("id", "")
        ntitle = item.get("title", "")
        
        # 終了したUMAイベント関連ニュースは完全にパージ
        if "UMA" in ntitle or "uma" in nid:
            date_str = item.get("date", today_date_str)
            if date_str <= "2026-10-24":
                continue

        if nid not in seen_ids and ntitle not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(ntitle)
            unique_news.append(item)

    # 10日間保持ルール（11日以上前の古いニュースを削除）
    valid_news = []
    for item in unique_news:
        date_str = item.get("date", today_date_str)
        try:
            item_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            diff_days = (today_dt - item_dt).days
            if diff_days <= 10:
                valid_news.append(item)
            else:
                print(f"[自動削除] 11日以上前のニュースを除外: {item.get('title')}")
        except Exception:
            valid_news.append(item)

    valid_news.sort(key=lambda x: x.get("date", today_date_str), reverse=True)

    final_events = extracted_events if len(extracted_events) > 0 else existing_data.get("events", [])

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news,
        "events": final_events
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 整合性チェック完了: ニュース{len(valid_news)}件保持")

except Exception as e:
    print(f"解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
