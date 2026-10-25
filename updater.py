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
print(f"[{now_str}] 攻略サイト詳細ページ巡回＆解析を開始します...")

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

# 1. ポケマピのイベント一覧から「直近の個別イベント詳細記事URL」を自動抽出して巡回
detail_urls = []
try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        soup = BeautifulSoup(res.text, "html.parser")
        # /board/数字/ のリンクを上位抽出（ハロウィン等の直近イベント記事）
        links = soup.find_all("a", href=re.compile(r"/board/\d+/"))
        for link in links:
            url = link["href"]
            if not url.startswith("http"):
                url = "https://pokemongo-get.com" + url
            if url not in detail_urls:
                detail_urls.append(url)
            if len(detail_urls) >= 4:  # 直近の重要イベント4記事に限定して深掘り
                break
except Exception as e:
    print(f"イベント一覧取得エラー: {e}")

# 2. 直近個別詳細ページをスクレイピング（ハロウィン詳細などの全ポケモンリストを取得）
for durl in detail_urls:
    try:
        res = requests.get(durl, headers=headers, timeout=10)
        if res.status_code == 200:
            dsoup = BeautifulSoup(res.text, "html.parser")
            title = dsoup.find("title").get_text() if dsoup.find("title") else durl
            for tag in dsoup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            text_chunk = dsoup.get_text(separator="\n", strip=True)[:7000]
            scraped_texts.append(f"【ポケマピ詳細記事: {title} ({durl})】\n{text_chunk}")
            print(f"詳細ページ取得成功: {title}")
    except Exception as e:
        print(f"詳細ページ取得スキップ ({durl}): {e}")

# 3. GameWith & 9DB の最新速報も補完取得
try:
    gw_res = requests.get("https://pokemongo.gamewith.jp/article/show/24434", headers=headers, timeout=10)
    if gw_res.status_code == 200:
        gsoup = BeautifulSoup(gw_res.text, "html.parser")
        for tag in gsoup(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()
        scraped_texts.append("【GameWith 最新速報】\n" + gsoup.get_text(separator="\n", strip=True)[:6000])
except Exception as e:
    print(f"GameWith取得スキップ: {e}")

combined_text = "\n\n".join(scraped_texts)

# 4. Gemini API による精密解析
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGOの最新イベントと出現ポケモンを網羅的にデータベース化する専門AIです。
現在の基準日時（日本時間）: {now_str} (今日: {today_date_str})

以下に提供された「ポケマピ詳細記事（各イベントの個別ページ）」および速報テキストを読み込み、出現ポケモンやタスク報酬を1匹も漏らさずに抽出してください。

【厳格な検証ルール】
1. 【重要】「UMAトリオ」「マックスバトルデイ」等の10/24終了イベントは完全に終了した過去のものです。いかなる理由があっても本日のニュース（new_news）に含めないでください。
2. ハロウィン2026 パート1等の重要イベントについては、詳細記事に記載されている野生出現ポケモン、レイド、フィールドリサーチタスクを省略せず可能な限りすべて抽出してください。
   （例：モルペコ、衣装ピカチュウ、ボチ、ミカルゲ、フワンテ、ヒトモシ、カゲボウズ、ゴース、ボクレー、バケッチャ等、記事内のポケモンを網羅すること）
3. パート1とパート2の内容を混同しないでください（魔女帽子ケロマツはパート2です）。

出力形式（純粋なJSONのみ出力）：
{{
  "new_news": [
    {{
      "id": "一意のID",
      "date": "YYYY-MM-DD",
      "date_label": "M/D",
      "title": "ニュース件名",
      "details": "詳細要約（2〜3行）",
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
      "dateText": "日程テキスト",
      "summary": "概要",
      "bonuses": ["ボーナス一覧"],
      "wilds": [{{"dex": 図鑑番号, "name": "名前", "shiny": true/false, "note": "備考"}}],
      "raids": [{{"dex": 図鑑番号, "name": "名前", "shiny": true/false, "note": "備考", "targetKey": "キー", "isDmax": true/false}}],
      "tasks": [{{"task": "タスク内容", "rewardDex": 図鑑番号, "rewardName": "報酬名", "shiny": true/false}}]
    }}
  ]
}}

【巡回記事テキスト】:
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
        
        # UMAニュースはタイトル・ID・日程問わず完全永久ブロック
        if "UMA" in ntitle or "uma" in nid or "ユクシー" in ntitle or "マックスバトルデイ" in ntitle:
            continue

        if nid not in seen_ids and ntitle not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(ntitle)
            unique_news.append(item)

    # 10日間ルール（11日以上前の古いニュースを削除）
    valid_news = []
    for item in unique_news:
        date_str = item.get("date", today_date_str)
        try:
            item_dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            diff_days = (today_dt - item_dt).days
            if diff_days <= 10:
                valid_news.append(item)
            else:
                print(f"[自動パージ] 11日以上前のニュースを除外: {item.get('title')}")
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

    print(f"[{now_str}] 解析完了: 有効ニュース{len(valid_news)}件")

except Exception as e:
    print(f"AI解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
