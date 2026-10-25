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
    existing_data = {"latest_news": [], "field_research_updates": {}, "dynamic_events": []}

existing_news = existing_data.get("latest_news", [])
existing_fr_updates = existing_data.get("field_research_updates", {})
existing_events = existing_data.get("dynamic_events", [])

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
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "th", "td", "dt", "dd"]):
        txt = el.get_text(" ", strip=True)
        if not txt or len(txt) < 2:
            continue
        if el.name in ["h1", "h2", "h3", "h4"]:
            lines.append(f"\n### 【見出し: {txt}】")
        else:
            lines.append(txt)
    return title, "\n".join(lines)[:max_chars]

# 1. ポケマピ (イベント一覧 + 開催中/直近イベント記事を優先して最大8件取得)
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
            if len(pokemapi_urls) >= 8:
                break
except Exception as e:
    print(f"ポケマピ一覧取得スキップ: {e}")

for url in pokemapi_urls:
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            title, body = extract_structured_text(res.text, 8000)
            scraped_sections.append(f"=== [ポケマピ記事詳細: {title} ({url})] ===\n{body}")
    except Exception as e:
        print(f"ポケマピ記事取得スキップ ({url}): {e}")

# 2. GameWith (トップ・最新イベント・タスク一覧)
for gw_url in [
    "https://pokemongo.gamewith.jp/",
    "https://pokemongo.gamewith.jp/article/show/24434",
    "https://pokemongo.gamewith.jp/article/show/102551" # フィールドリサーチ一覧
]:
    try:
        gw_res = requests.get(gw_url, headers=headers, timeout=10)
        if gw_res.status_code == 200:
            title, body = extract_structured_text(gw_res.text, 6500)
            scraped_sections.append(f"=== [GameWith: {title}] ===\n{body}")
    except Exception as e:
        print(f"GameWith取得スキップ ({gw_url}): {e}")

# 3. 9DB みんポケ (トップ・フィールドリサーチ一覧)
for db_url in [
    "https://9db.jp/pokemongo/",
    "https://9db.jp/pokemongo/data/4314" # みんポケ フィールドリサーチ一覧
]:
    try:
        db_res = requests.get(db_url, headers=headers, timeout=10)
        if db_res.status_code == 200:
            title, body = extract_structured_text(db_res.text, 6500)
            scraped_sections.append(f"=== [9DB みんポケ: {title}] ===\n{body}")
    except Exception as e:
        print(f"9DB取得スキップ ({db_url}): {e}")

# 4. Pokémon GO 公式サイト
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

以下の【スクレイピング取得テキスト】のみを根拠として、以下の3つのデータをJSON形式で出力してください：
1. `new_news`: 最新ニュース速報
2. `field_research_updates`: イベント開始後に判明した「イベント限定フィールドリサーチ（ポケストップから入手する具体的なタスク条件と報酬ポケモン一覧）」
3. `dynamic_events`: 新しく詳細が発表されたイベント情報

【既存イベントID一覧（`targetId` や `field_research_updates` のキーに使用）】
- "ev-halloween-p1" (ハロウィン2026パート1: 10/27〜11/1)
- "ev-halloween-p2" (ハロウィン2026パート2: 11/1〜11/5)
- "ev-supermega-chandelure" (シャンデラのスーパーメガレイド・デイ: 10/31)
- "ev-dmax-sableye-week" (ダイマックスヤミラミ週間: 10/26〜11/1)
- "ev-raid-giratina-o" (ギラティナオリジン・メガヤミラミ: 10/28〜)
- "ev-dmax-machop-week" (ダイマックスワンリキー週間: 11/2〜11/8)
- "ev-gopass-nov" (GOパス11月・グラードン: 11/3〜)
- "ev-wildweek-2026" (ワイルドウィーク・剣の王ザシアン/盾の王ザマゼンタ・銀の王冠: 11/9〜11/13)
- "ev-wildarea-2026" (GOワイルドエリア2026グローバル: 11/14〜11/15)
- "ev-big-footprints" (大きな足跡イベント・クレセリア/ダークライ: 11/16〜11/24)
- "ev-cd-pawniard" (コマタナのコミュニティデイ: 11/21)
- "ev-tusk-wish-deoxys" (黄昏時の願い・デオキシス・メガメタグロス: 11/24〜)

【フィールドリサーチ抽出の最重要ルール】
- `field_research_updates` には、**具体的な達成条件（例：「カーブボールを3回投げる」「ゴーストタイプのポケモンを5匹捕まえる」「ポケモンを5匹進化させる」など）が記事内で判明しているタスクのみ**を入れてください。
- まだイベント開始前で「タスク条件が未判明（報酬ポケモンのみ予告されている状態）」の場合は、そのイベントの `field_research_updates` は出力しないでください（空にしておくことでフロントエンド側の待機表示が維持されます）。

【特殊フォルム図鑑番号（`dex` / `rewardDex`）】
- ザシアン(けんのおう): 10188 / ザマゼンタ(たてのおう): 10189
- ネクロズマ(たそがれ): 10155 / ネクロズマ(あかつき): 10156
- ブラックキュレム: 10022 / ホワイトキュレム: 10023
- ディアルガ(オリジン): 10245 / パルキア(オリジン): 10246 / ギラティナ(オリジン): 10007
- ランドロス(れいじゅう): 10021 / ガラルヒヒダルマ: 10177 / アローラライチュウ: 10100 / アローラキュウコン: 10104
- メガリザードンX: 10034 / メガリザードンY: 10035 / メガゲンガー: 10038 / メガギャラドス: 10041
- メガバンギラス: 10049 / メガサーナイト: 10051 / メガジュペッタ: 10056 / メガルカリオ: 10059
- メガラグラージ: 10064 / メガヤミラミ: 10066 / メガメタグロス: 10076 / ゲンシカイオーガ: 10077 / ゲンシグラードン: 10078 / メガレックウザ: 10079
- キョダイカイリキー: 10201 / キョダイゲンガー: 10202 / キョダイオーロンゲ: 10222 / キョダイジュラルドン: 10225

出力JSONスキーマ（純粋なJSONのみ）：
{{
  "new_news": [
    {{
      "id": "news-一意の英数字スラッグ",
      "date": "YYYY-MM-DD",
      "date_label": "M/D",
      "title": "ニュース件名",
      "details": "詳細要約（2〜3文）",
      "targetId": "連動するイベントID"
    }}
  ],
  "field_research_updates": {{
    "ev-halloween-p1": [
      {{
        "task": "具体的なタスク条件（例：カーブボールを3回投げる）",
        "rewardDex": 25,
        "rewardName": "ピカチュウ (ハット&ケープ)",
        "shiny": true,
        "note": "CP範囲や補足情報"
      }}
    ]
  }},
  "dynamic_events": []
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
    new_fr_updates = ai_result.get("field_research_updates", {})
    new_extracted_events = ai_result.get("dynamic_events", [])

    # 1. ニュースの統合と重複排除
    all_news_pool = new_extracted_news + existing_news
    seen_ids = set()
    seen_titles = set()
    unique_news = []
    today_dt = now.date()
    banned_keywords = ["UMA", "ユクシー", "モルペコ", "オリオン座"]

    for item in all_news_pool:
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
    valid_news = valid_news[:8]

    # 2. イベント別フィールドリサーチの更新統合（未判明・プレースホルダー文字列は弾く安全装置付き）
    merged_fr_updates = dict(existing_fr_updates) if isinstance(existing_fr_updates, dict) else {}
    placeholder_words = ["未判明", "調査中", "イベント限定フィールドリサーチ", "不明", "判明次第"]

    if isinstance(new_fr_updates, dict):
        for ev_id, task_list in new_fr_updates.items():
            if isinstance(task_list, list) and len(task_list) > 0:
                valid_tasks = []
                for t in task_list:
                    task_text = str(t.get("task", "")).strip()
                    reward_name = str(t.get("rewardName", "")).strip()
                    if not task_text or not reward_name:
                        continue
                    # プレースホルダー（条件未判明）ならスキップし、具体的なタスク条件のみ採用
                    if any(pw in task_text for pw in placeholder_words):
                        continue
                    valid_tasks.append(t)
                if len(valid_tasks) > 0:
                    merged_fr_updates[ev_id] = valid_tasks

    # 3. 動的イベントの統合
    event_map = {}
    for ev in existing_events:
        if ev.get("id"):
            event_map[ev["id"]] = ev
    for ev in new_extracted_events:
        if ev.get("id") and ev.get("title") and ev.get("month") in [10, 11, 12]:
            event_map[ev["id"]] = ev

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news,
        "field_research_updates": merged_fr_updates,
        "dynamic_events": list(event_map.values())
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 更新完了: ニュース {len(valid_news)} 件 / リサーチ更新 {len(merged_fr_updates)} イベント / 動的イベント {len(event_map)} 件")

except Exception as e:
    print(f"解析エラー: {e}")
    existing_data["updated_at"] = now_str
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)
