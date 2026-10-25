import os
import json
import datetime
import re
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# 日本時間 (JST)
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
today_date_str = now.strftime("%Y-%m-%d")
now_str = now.strftime("%Y/%m/%d %H:%M JST")
print(f"[{now_str}] 4大サイト巡回スクレイピング＆Gemini精密解析を開始します...")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {"latest_news": []}

existing_news = existing_data.get("latest_news", [])

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

scraped_sections = []

def extract_structured_text(html_text, max_chars=8000):
    soup = BeautifulSoup(html_text, "html.parser")
    title = soup.find("title").get_text(strip=True) if soup.find("title") else ""
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe"]):
        tag.decompose()
    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "th", "td"]):
        txt = el.get_text(" ", strip=True)
        if not txt or len(txt) < 2:
            continue
        if el.name in ["h1", "h2", "h3", "h4"]:
            lines.append(f"\n### 【見出し: {txt}】")
        else:
            lines.append(txt)
    return title, "\n".join(lines)[:max_chars]

# 1. ポケマピ (イベント一覧 + 最新記事上位5件を動的取得)
pokemapi_urls = []
try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        title, body = extract_structured_text(res.text, 8000)
        scraped_sections.append(f"=== [ポケマピ イベントカレンダー一覧] ===\n{body}")
        soup = BeautifulSoup(res.text, "html.parser")
        for link in soup.find_all("a", href=re.compile(r"/board/\d+/")):
            url = link["href"]
            if not url.startswith("http"):
                url = "https://pokemongo-get.com" + url
            if url not in pokemapi_urls:
                pokemapi_urls.append(url)
            if len(pokemapi_urls) >= 5:
                break
except Exception as e:
    print(f"ポケマピ一覧取得スキップ: {e}")

for url in pokemapi_urls:
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            title, body = extract_structured_text(res.text, 7000)
            scraped_sections.append(f"=== [ポケマピ最新記事: {title} ({url})] ===\n{body}")
    except Exception as e:
        print(f"ポケマピ記事取得スキップ ({url}): {e}")

# 2. GameWith (トップ・最新イベントまとめ)
for gw_url in ["https://pokemongo.gamewith.jp/", "https://pokemongo.gamewith.jp/article/show/24434"]:
    try:
        gw_res = requests.get(gw_url, headers=headers, timeout=10)
        if gw_res.status_code == 200:
            title, body = extract_structured_text(gw_res.text, 6000)
            scraped_sections.append(f"=== [GameWith: {title}] ===\n{body}")
    except Exception as e:
        print(f"GameWith取得スキップ ({gw_url}): {e}")

# 3. 9DB みんポケ (トップ・最新イベント・マックスバトル)
try:
    db_res = requests.get("https://9db.jp/pokemongo/", headers=headers, timeout=10)
    if db_res.status_code == 200:
        title, body = extract_structured_text(db_res.text, 6000)
        scraped_sections.append(f"=== [9DB みんポケ: {title}] ===\n{body}")
except Exception as e:
    print(f"9DB取得スキップ: {e}")

# 4. Pokémon GO 公式サイト (日本語ニュース一覧)
try:
    off_res = requests.get("https://pokemongo.com/ja/news", headers=headers, timeout=10)
    if off_res.status_code == 200:
        title, body = extract_structured_text(off_res.text, 6000)
        scraped_sections.append(f"=== [ポケモンGO公式サイト 最新ニュース] ===\n{body}")
except Exception as e:
    print(f"公式サイト取得スキップ: {e}")

combined_text = "\n\n".join(scraped_sections)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGO攻略サイト（ポケマピ、GameWith、9DB、公式サイト）の情報を統合・検証するデータベース管理AIです。
現在の基準日時（日本時間）: {now_str} (今日の日付: {today_date_str})

以下の【スクレイピング取得テキスト】のみを根拠として、直近で発表された重要ニュース・開催予定イベントの速報をJSON形式で出力してください。

【絶対遵守のファクトチェック・ルール】
1. 過去の知識（2024年や2025年のハロウィン・過去イベントの記憶など）を絶対に混ぜないでください。スクレイピングされたテキスト内に明記されている事実・日付・ポケモンのみを記載してください。
2. 基準日（{today_date_str}）より前にすでに終了したイベント（例：10/24終了のオリオン座流星群やUMAマックスバトルデイ等）はニュースに含めないでください。
3. 各ニュースの `targetId` には、フロントエンド側のイベントID（以下の候補から最も近いもの、該当なしは空文字 ""）を指定してください：
   - "ev-halloween-p1" (ハロウィン2026パート1: 10/27〜11/1)
   - "ev-halloween-p2" (ハロウィン2026パート2: 11/1〜11/5)
   - "ev-supermega-chandelure" (シャンデラのスーパーメガレイド・デイ: 10/31)
   - "ev-dmax-sableye-week" (ダイマックスヤミラミ・マックスマンデー: 10/26〜11/1)
   - "ev-raid-giratina-o" (ギラティナオリジン・メガヤミラミ: 10/28〜)
   - "ev-dmax-machop-week" (ダイマックスワンリキー: 11/2〜11/8)
   - "ev-gopass-nov" (GOパス11月・グラードン: 11/3〜)
   - "ev-wildweek-2026" (ワイルドウィーク・剣の王ザシアン/盾の王ザマゼンタ・銀の王冠: 11/9〜11/13)
   - "ev-wildarea-2026" (GOワイルドエリア2026グローバル・W/Bキュレム・キョダイジュラルドン・DMaxディアルガ/パルキア: 11/14〜11/15)
   - "ev-cd-pawniard" (コマタナのコミュニティデイ: 11/21)
   - "ev-tusk-wish-deoxys" (黄昏時の願い・デオキシス・メガメタグロス: 11/24〜)

出力JSONスキーマ（純粋なJSONのみを出力）：
{{
  "new_news": [
    {{
      "id": "news-一意の英数字スラッグ",
      "date": "YYYY-MM-DD",
      "date_label": "M/D",
      "title": "ニュース件名（具体的な日付やポケモン名を含める）",
      "details": "詳細要約（開催期間、初登場ポケモン、ボーナス、注意点などを2〜3文で具体的に記述）",
      "targetId": "連動するイベントID"
    }}
  ]
}}

【スクレイピング取得テキスト】:
{combined_text}
"""

try:
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )
    except Exception:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

    ai_result = json.loads(response.text)
    new_extracted_news = ai_result.get("new_news", [])

    all_news_pool = new_extracted_news + existing_news
    seen_ids = set()
    seen_titles = set()
    unique_news = []
    today_dt = now.date()

    # 古い誤情報ワードや不完全なオブジェクトを除外
    banned_keywords = ["UMA", "ユクシー", "モルペコ", "オリオン座"]

    for item in all_news_pool:
        # title と details と date が揃っている正常なデータのみ採用
        nid = item.get("id", "")
        ntitle = item.get("title", "")
        ndetails = item.get("details", "")
        if not nid or not ntitle or not ndetails:
            continue
        if any(bk in ntitle or bk in ndetails for bk in banned_keywords):
            continue
        if nid not in seen_ids and ntitle not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(ntitle)
            unique_news.append(item)

    # 12日間保持・それ以前は自動パージ
    valid_news = []
    for item in unique_news:
        date_str = item.get("date", today_date_str)
        try:
            item_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            if (today_dt - item_dt).days <= 12:
                valid_news.append(item)
        except Exception:
            valid_news.append(item)

    valid_news.sort(key=lambda x: x.get("date", today_date_str), reverse=True)
    # 最大8件までに制限して見やすさを維持
    valid_news = valid_news[:8]

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 更新完了: 有効ニュース {len(valid_news)} 件")

except Exception as e:
    print(f"解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
