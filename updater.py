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
print(f"[{now_str}] 3大サイト構造化スクレイピング＆Gemini Pro精密解析を開始します...")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {"events": [], "latest_news": []}

existing_news = existing_data.get("latest_news", [])

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

scraped_sections = []

# 1. 重要イベント詳細記事の直接巡回 + 一覧からの自動抽出
target_detail_urls = [
    "https://pokemongo-get.com/board/10711/"
]

try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        links = soup.find_all("a", href=re.compile(r"/board/\d+/"))
        for link in links:
            url = link["href"]
            if not url.startswith("http"):
                url = "https://pokemongo-get.com" + url
            if url not in target_detail_urls:
                target_detail_urls.append(url)
            if len(target_detail_urls) >= 4:
                break
except Exception as e:
    print(f"一覧取得スキップ: {e}")

# 2. 見出し（H2/H3）を維持してセクションごとに構造化抽出
for url in target_detail_urls:
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            title = soup.find("title").get_text() if soup.find("title") else url
            for tag in soup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            
            article_body = []
            for el in soup.find_all(["h2", "h3", "h4", "p", "li", "th", "td"]):
                txt = el.get_text(strip=True)
                if not txt:
                    continue
                if el.name in ["h2", "h3", "h4"]:
                    article_body.append(f"\n### 【セクション見出し: {txt}】")
                else:
                    article_body.append(txt)
            
            scraped_sections.append(f"=== [ポケマピ詳細記事: {title} ({url})] ===\n" + "\n".join(article_body)[:10000])
    except Exception as e:
        print(f"詳細取得スキップ ({url}): {e}")

# 3. GameWith ＆ 9DB の速報補完
try:
    gw_res = requests.get("https://pokemongo.gamewith.jp/article/show/24434", headers=headers, timeout=10)
    if gw_res.status_code == 200:
        gsoup = BeautifulSoup(gw_res.text, "html.parser")
        for tag in gsoup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_sections.append("=== [GameWith 最新情報] ===\n" + gsoup.get_text(separator="\n", strip=True)[:6000])
except Exception:
    pass

combined_text = "\n\n".join(scraped_sections)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGO攻略情報の整合性検証・データベース化を行う最高責任者AIです。
現在の基準日時（日本時間）: {now_str} (今日の日付: {today_date_str})

提供された複数の攻略サイトの見出し付き構造化テキストを精査し、論理的に100%正確なJSONデータを出力してください。

【絶対遵守の整合性ルール】
1. セクション見出し（パート1 / パート2、野生 / レイド / GBL報酬 / タスク）の境界を厳格に区別してください。
   - モルペコは「GBLリワード報酬」および「タイムチャレンジ報酬」限定です。絶対に「wilds（野生出現）」に入れないでください。
   - ハロウィンパート1の野生は「衣装なしの通常ゴースト・あくタイプ」です。
   - 魔女帽子ケロマツ、衣装モクロー、ボチの色違い初解禁、キョダイマックスゲンガーは「パート2」の要素です。パート1に混入させないでください。
2. 基準日（{today_date_str}）より前に終了したイベント（10/24終了のUMAマックスバトルデイ等）はニュースに含めないでください。

出力JSONスキーマ（純粋なJSONのみ）：
{{
  "new_news": [
    {{
      "id": "一意のID",
      "date": "YYYY-MM-DD",
      "date_label": "M/D",
      "title": "ニュース件名",
      "details": "詳細要約（2〜3行）",
      "targetId": "連動するイベントID"
    }}
  ]
}}

【構造化テキスト】:
{combined_text}
"""

try:
    # 推論精度の高い gemini-2.5-pro を使用（利用不可環境時は flash にフォールバック）
    try:
        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
    except Exception:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

    ai_result = json.loads(response.text)
    new_extracted_news = ai_result.get("new_news", [])

    all_news_pool = new_extracted_news + existing_news
    seen_ids = set()
    seen_titles = set()
    unique_news = []
    today_dt = now.date()

    for item in all_news_pool:
        nid = item.get("id", "")
        ntitle = item.get("title", "")
        if "UMA" in ntitle or "uma" in nid or "ユクシー" in ntitle or "マックスバトルデイ" in ntitle:
            continue
        if nid not in seen_ids and ntitle not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(ntitle)
            unique_news.append(item)

    # 10日間保持・11日目以降は自動パージ
    valid_news = []
    for item in unique_news:
        date_str = item.get("date", today_date_str)
        try:
            item_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            if (today_dt - item_dt).days <= 10:
                valid_news.append(item)
        except Exception:
            valid_news.append(item)

    valid_news.sort(key=lambda x: x.get("date", today_date_str), reverse=True)

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news,
        "events": existing_data.get("events", [])
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 更新完了: 有効ニュース{len(valid_news)}件")

except Exception as e:
    print(f"解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
