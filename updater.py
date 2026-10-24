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
now_str = now.strftime("%Y/%m/%d %H:%M JST")
print(f"[{now_str}] AIによる最新攻略データ解析を開始します...")

# 既存データの読み込み
try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {"events": [], "latest_news": []}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 1. 攻略サイトからテキスト情報を取得
scraped_text = ""
try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        scraped_text = soup.get_text(separator="\n", strip=True)[:15000]
except Exception as e:
    print(f"Web取得スキップ: {e}")

# 2. Gemini API で解析
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が設定されていません。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGOのデータ抽出・構造化AIです。
以下は日本の攻略サイトから取得した最新テキストです。
本日の日本日時は「{now_str}」です。

【重要：タイムゾーンと地域限定（海外）の処理ルール】
1. 【カレンダー日程は100%日本時間（国内基準）】
   - イベント期間（startDay, endDay, startDate, endDate）は、必ず「日本国内（日本時間/JST）での開催日程」のみを基準にしてください。
   - 海外現地時間（欧米等）の時差によって日本時間の翌日にまたがる場合でも、カレンダーバーの終了日（endDay）を引き延ばさないでください。
   - （例：UMAマックスバトルデイは、日本国内開催が10/24(土)14:00〜17:00なので、startDay: 24, endDay: 24 とする）

2. 【海外限定・時差ポケモンの日本時間換算はカード詳細に記載】
   - アグノム・エムリット等の地域限定ポケモンや海外レイドがある場合、概要（summary）または bonuses に、日本時間換算のスケジュールをそれぞれ明記してください。
   - （例：ユクシー[日本/アジア]: 10/24 14:00〜17:00 / エムリット[欧州等]: 日本時間10/24 21:00〜25 0:00 / アグノム[米大陸]: 日本時間10/25 3:00〜6:00 等）

3. 【その他の基本ルール】
   - カテゴリ（category）: 'main', 'raid', 'dmax', 'collab', 'gbl' のいずれか。
   - barClass: category に応じて 'bar-main', 'bar-raid', 'bar-dmax', 'bar-collab', 'bar-gbl'。
   - latest_news: 直近の重要公式ニュース（3〜5件）。
   - 終了から30日以上過ぎた過去イベントは除外。

以下のJSONスキーマ通りの純粋なJSONのみを出力してください（Markdown装飾不要）：
{{
  "latest_news": [
    {{ "title": "ニュースタイトル", "link": "#該当イベントIDまたはURL" }}
  ],
  "events": [
    {{
      "id": "一意のID (例: ev-dmax-uma)",
      "month": 開始月(数値),
      "title": "イベント名",
      "barClass": "バー用クラス名",
      "category": "カテゴリ名",
      "startDay": 日本基準の開始日(数値),
      "endDay": 日本基準の終了日(数値),
      "startDate": "YYYY-MM-DD",
      "endDate": "YYYY-MM-DD",
      "dateText": "日本国内の開催日程テキスト",
      "summary": "概要（海外枠がある場合は日本時間換算の各スケジュールもここに記載）",
      "bonuses": ["ボーナスや海外出現枠の補足など"],
      "wilds": [
        {{ "dex": 図鑑番号(数値), "name": "ポケモン名", "shiny": true/false, "note": "備考" }}
      ],
      "raids": [
        {{ "dex": 図鑑番号(数値), "name": "ボス名", "shiny": true/false, "note": "難易度・地域等", "targetKey": "識別キー", "isDmax": true/false }}
      ],
      "tasks": [
        {{ "task": "タスク内容", "rewardDex": 報酬ポケ図鑑番号, "rewardName": "報酬名", "shiny": true/false }}
      ]
    }}
  ]
}}

【攻略サイトのテキスト】:
{scraped_text}
"""

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        )
    )
    ai_data = json.loads(response.text)
    ai_data["updated_at"] = now_str

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(ai_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] AIによる全データ抽出・自動コミット準備が完了しました。")

except Exception as e:
    print(f"AI解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
