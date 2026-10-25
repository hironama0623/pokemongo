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
print(f"[{now_str}] 攻略サイト巡回＆AI解析を開始します...")

# 既存データの読み込み (差分検知 & 10日間保持用)
try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {"events": [], "latest_news": []}

existing_news = existing_data.get("latest_news", [])

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 1. 攻略サイト（ポケマピ、GameWith等）から最新テキストを取得
scraped_texts = []

# ポケマピ (最新イベント・速報)
try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_texts.append("【ポケマピ 最新イベント・ニュース】\n" + soup.get_text(separator="\n", strip=True)[:10000])
except Exception as e:
    print(f"ポケマピ取得スキップ: {e}")

# GameWith (ポケモンGO 最新情報・速報)
try:
    res = requests.get("https://pokemongo.gamewith.jp/article/show/24434", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_texts.append("【GameWith 最新速報】\n" + soup.get_text(separator="\n", strip=True)[:8000])
except Exception as e:
    print(f"GameWith取得スキップ: {e}")

combined_text = "\n\n".join(scraped_texts)

# 2. Gemini API で差分解析
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が設定されていません。")
    exit(1)

client = genai.Client(api_key=api_key)

# 既存のニュースタイトルリストをAIに伝えて重複を防止
known_titles = [n.get("title", "") for n in existing_news]

prompt = f"""
あなたはポケモンGOの最新情報・速報ニュースを分析・構造化する専門AIです。
本日の基準日時（日本時間）は「{now_str}」です。今日の日付は「{today_date_str}」です。

以下は攻略サイトから取得した最新テキストです。
また、すでに登録済みのニュース件名一覧は以下の通りです：
{json.dumps(known_titles, ensure_ascii=False)}

【ニュース抽出の厳格ルール】
1. テキストを精査し、公式発表、最新速報、イベント予告、ボーナス、不具合情報などの重要ニュースを抽出してください。
2. すでに登録済みのニュースと同じ内容・同じ件名のものは重複して出力しないでください（新着のもの、または更新があったもののみを抽出）。
3. 各ニュースには以下を含めてください：
   - id: 一意のID (例: news-20261025-twitch)
   - date: 発表日または検知日 (YYYY-MM-DD形式、不明な場合は本日の日付「{today_date_str}」)
   - date_label: M/D形式 (例: 10/25)
   - title: 簡潔でわかりやすい件名 (例: ポケモンナイトアウトTwitch公式配信でモルペコ配布)
   - details: クリック時に読める詳細説明・攻略ポイント（2〜3行程度）
   - targetId: 該当するイベントやレイドのID（例: ev-twitch, ev-palkia-char, dmax-sneasel 等。該当がなければ空文字 ""）

【イベント抽出のルール】
- 日本国内基準（JST）で現在開催中および今後開催されるイベントを抽出してください。
- 1日限定イベント（レイドデイ、マックスバトルデイ等）は必ず startDay == endDay としてください。

以下のJSONスキーマ通りの純粋なJSONのみを出力してください（Markdown装飾不要）：
{{
  "new_news": [
    {{
      "id": "一意のID",
      "date": "YYYY-MM-DD",
      "date_label": "M/D",
      "title": "ニュース件名",
      "details": "ニュースの詳細要約",
      "targetId": "連動するイベントID（または空文字）"
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
      "wilds": [{{ "dex": 図鑑番号, "name": "名前", "shiny": true/false, "note": "備考" }}],
      "raids": [{{ "dex": 図鑑番号, "name": "名前", "shiny": true/false, "note": "備考", "targetKey": "キー", "isDmax": true/false }}],
      "tasks": [{{ "task": "タスク", "rewardDex": 図鑑番号, "rewardName": "報酬名", "shiny": true/false }}]
    }}
  ]
}}

【取得テキスト】:
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

    # 3. ニュースのマージ ＆ 10日間保持（11日目以降の自動削除パージ）
    all_news_pool = new_extracted_news + existing_news
    
    # 重複除外 (IDまたはタイトル基準)
    seen_ids = set()
    seen_titles = set()
    unique_news = []
    
    for item in all_news_pool:
        nid = item.get("id")
        ntitle = item.get("title")
        if nid not in seen_ids and ntitle not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(ntitle)
            unique_news.append(item)

    # 10日間ルール：今日から10日より前の古いニュースは削除
    today_dt = now.date()
    valid_news = []
    for item in unique_news:
        date_str = item.get("date", today_date_str)
        try:
            item_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            diff_days = (today_dt - item_dt).days
            if diff_days <= 10:  # 10日以内なら保持
                valid_news.append(item)
            else:
                print(f"[自動削除] 11日以上経過したニュースを除外: {item.get('title')}")
        except Exception:
            valid_news.append(item)

    # 日付降順（新しいものが上）にソート
    valid_news.sort(key=lambda x: x.get("date", today_date_str), reverse=True)

    # イベントの更新（AIが抽出したイベントがあれば更新、なければ既存維持）
    final_events = extracted_events if len(extracted_events) > 0 else existing_data.get("events", [])

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news,
        "events": final_events
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] ニュース更新完了: 有効ニュース{len(valid_news)}件 (新着+{len(new_extracted_news)}件)")

except Exception as e:
    print(f"AI解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
