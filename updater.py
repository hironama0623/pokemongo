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

# 1. 攻略サイト（ポケマピ・GameWith）からテキスト情報をスクレイピング
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

# 2. Gemini API でテキストを解析し、完全な構造化JSONを生成
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が設定されていません。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGOのデータ抽出AIです。
以下は日本のポケモンGO攻略サイトから取得した最新テキストです。
基準日（今日）は「{now_str}」です。

【指示】
1. 現在開催中および今後開催予定のイベント、レイド、ダイマックス情報をすべて抽出してください。
2. 日程を正確に解析してください。例えば「10/24(土) 14:00〜17:00」のように単日限定なら、開始日と終了日を必ず同じ「2026-10-24」にしてください。
3. カテゴリ（category）は 'main'(メイン/シーズン), 'raid'(レイド), 'dmax'(ダイマックス), 'collab'(コラボ), 'gbl'(GBL) のいずれかに分類してください。
4. barClass は category に応じて 'bar-main', 'bar-raid', 'bar-dmax', 'bar-collab', 'bar-gbl' にしてください。
5. 直近の最重要公式速報ニュース（3〜5件）を latest_news に抽出してください。
6. 過去のイベントのうち、終了日から30日以上過ぎたものは除外し、終了後30日以内のものは含めてください。

必ず以下のJSONスキーマ通りの純粋なJSONのみを出力してください（Markdownの装飾は不要）：
{{
  "latest_news": [
    {{ "title": "ニュースタイトル", "link": "#該当イベントIDまたはURL" }}
  ],
  "events": [
    {{
      "id": "一意のID (例: ev-dmax-uma-day)",
      "month": 開始月(数値),
      "title": "イベント名",
      "barClass": "バー用クラス名",
      "category": "カテゴリ名",
      "startDay": 開始日(数値),
      "endDay": 終了日(数値),
      "startDate": "YYYY-MM-DD",
      "endDate": "YYYY-MM-DD",
      "dateText": "画面表示用日程テキスト (例: 10/24(土) 14:00〜17:00 [本日限定])",
      "summary": "概要説明",
      "bonuses": ["ボーナス1", "ボーナス2"],
      "wilds": [
        {{ "dex": 図鑑番号(数値), "name": "ポケモン名", "shiny": true/false, "note": "出現形態" }}
      ],
      "raids": [
        {{ "dex": 図鑑番号(数値), "name": "レイドボス名", "shiny": true/false, "note": "難易度等", "targetKey": "ボス識別キー", "isDmax": true/false }}
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

    # 3. data.json へ保存
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(ai_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] AIによる全データ抽出・自動コミット準備が完了しました。")

except Exception as e:
    print(f"AI解析エラー: {e}")
    # エラー時は日時だけ更新して維持
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
