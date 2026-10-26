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

# 1. ポケマピ
pokemapi_urls = []
try:
    res = requests.get("https://pokemongo-get.com/events/", headers=headers, timeout=12)
    if res.status_code == 200:
        title, body = extract_structured_text(res.text, 8000)
        scraped_sections.append(f"=== [ポケマピ イベント一覧] ===\n{body}")
        soup = BeautifulSoup(res.text, "html.parser")
        for link in soup.find_all("a", href=re.compile(r"/board/\d+/")):
            url = link["href"]
            if not url.startswith("http"): url = "https://pokemongo-get.com" + url
            if url not in pokemapi_urls: pokemapi_urls.append(url)
            if len(pokemapi_urls) >= 8: break
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

# 2. GameWith
for gw_url in ["https://pokemongo.gamewith.jp/", "https://pokemongo.gamewith.jp/article/show/24434", "https://pokemongo.gamewith.jp/article/show/102551"]:
    try:
        gw_res = requests.get(gw_url, headers=headers, timeout=10)
        if gw_res.status_code == 200:
            title, body = extract_structured_text(gw_res.text, 6500)
            scraped_sections.append(f"=== [GameWith: {title}] ===\n{body}")
    except Exception as e:
        pass

# 3. 9DB みんポケ
for db_url in ["https://9db.jp/pokemongo/", "https://9db.jp/pokemongo/data/4314"]:
    try:
        db_res = requests.get(db_url, headers=headers, timeout=10)
        if db_res.status_code == 200:
            title, body = extract_structured_text(db_res.text, 6500)
            scraped_sections.append(f"=== [9DB みんポケ: {title}] ===\n{body}")
    except Exception as e:
        pass

# 4. 公式サイト
try:
    off_res = requests.get("https://pokemongo.com/ja/news", headers=headers, timeout=10)
    if off_res.status_code == 200:
        title, body = extract_structured_text(off_res.text, 6000)
        scraped_sections.append(f"=== [公式サイト 最新ニュース] ===\n{body}")
except Exception as e:
    pass

combined_text = "\n\n".join(scraped_sections)

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGO攻略サイト（ポケマピ、GameWith、9DB、公式サイト）の情報を統合・検証するAIです。
現在の基準日時（日本時間）: {now_str} (今日: {today_date_str})

【スクレイピング取得テキスト】のみを根拠として以下のデータをJSON出力してください：
1. `new_news`: 最新ニュース速報
2. `field_research_updates`: イベント開始後に判明した限定フィールドリサーチ一覧（具体的なタスク条件が判明しているもののみ）
3. `dynamic_events`: 新規発表のイベント詳細（※「特別な技（レガシー技）」の習得がある場合は、必ず freeFeatures 等の概要欄に含めてください！）

【既存イベントID（targetIdやキーに使用）】
- "ev-halloween-p1" / "ev-halloween-p2" / "ev-supermega-chandelure" / "ev-dmax-sableye-week" / "ev-raid-giratina-o" / "ev-dmax-machop-week" / "ev-gopass-nov" / "ev-wildweek-2026" / "ev-wildarea-2026" / "ev-big-footprints" / "ev-cd-pawniard" / "ev-tusk-wish-deoxys"

【特殊フォルム専用ID（必ず以下を使用）】
- ザシアン(けんのおう): 10188 / ザマゼンタ(たてのおう): 10189 / ネクロズマ(たそがれ): 10155 / ネクロズマ(あかつき): 10156
- ブラックキュレム: 10022 / ホワイトキュレム: 10023 / ディアルガ(オリジン): 10245 / パルキア(オリジン): 10246 / ギラティナ(オリジン): 10007
- メガリザードンX: 10034 / メガリザードンY: 10035 / メガゲンガー: 10038 / メガギャラドス: 10041 / メガバンギラス: 10049 / メガサーナイト: 10051 / メガメタグロス: 10076 / ゲンシカイオーガ: 10077 / ゲンシグラードン: 10078 / メガレックウザ: 10079
- キョダイカイリキー: 10201 / キョダイゲンガー: 10202 / キョダイオーロンゲ: 10222 / キョダイジュラルドン: 10225

出力JSONスキーマ：
{{
  "new_news": [ {{ "id": "news-xxx", "date": "YYYY-MM-DD", "date_label": "M/D", "title": "件名", "details": "要約", "targetId": "連動ID" }} ],
  "field_research_updates": {{ "ev-halloween-p1": [ {{ "task": "カーブを3回投げる等", "rewardDex": 25, "rewardName": "ピカチュウ", "shiny": true, "note": "補足" }} ] }},
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
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )
    except Exception:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        )

    ai_result = json.loads(response.text)
    new_extracted_news = ai_result.get("new_news", [])
    new_fr_updates = ai_result.get("field_research_updates", {})
    new_extracted_events = ai_result.get("dynamic_events", [])

    all_news_pool = new_extracted_news + existing_news
    seen_ids, seen_titles, unique_news = set(), set(), []
    banned_keywords = ["UMA", "ユクシー", "モルペコ", "オリオン座"]

    for item in all_news_pool:
        nid, ntitle, ndetails = item.get("id", ""), item.get("title", ""), item.get("details", "")
        if not nid or not ntitle or not ndetails or any(bk in ntitle or bk in ndetails for bk in banned_keywords):
            continue
        if nid not in seen_ids and ntitle not in seen_titles:
            seen_ids.add(nid); seen_titles.add(ntitle); unique_news.append(item)

    valid_news = []
    today_dt = now.date()
    for item in unique_news:
        try:
            if (today_dt - datetime.datetime.strptime(item.get("date", today_date_str), "%Y-%m-%d").date()).days <= 12:
                valid_news.append(item)
        except: valid_news.append(item)

    valid_news.sort(key=lambda x: x.get("date", today_date_str), reverse=True)
    valid_news = valid_news[:8]

    merged_fr_updates = dict(existing_fr_updates) if isinstance(existing_fr_updates, dict) else {}
    placeholder_words = ["未判明", "調査中", "イベント限定フィールドリサーチ", "不明", "判明次第"]
    if isinstance(new_fr_updates, dict):
        for ev_id, task_list in new_fr_updates.items():
            if isinstance(task_list, list) and len(task_list) > 0:
                valid_tasks = [t for t in task_list if t.get("task") and t.get("rewardName") and not any(pw in str(t.get("task")) for pw in placeholder_words)]
                if valid_tasks: merged_fr_updates[ev_id] = valid_tasks

    event_map = {ev["id"]: ev for ev in existing_events if ev.get("id")}
    for ev in new_extracted_events:
        if ev.get("id") and ev.get("title") and ev.get("month") in [10, 11, 12]:
            event_map[ev["id"]] = ev

    final_data = {"updated_at": now_str, "latest_news": valid_news, "field_research_updates": merged_fr_updates, "dynamic_events": list(event_map.values())}

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)
    print(f"[{now_str}] 更新完了: ニュース {len(valid_news)} 件 / リサーチ {len(merged_fr_updates)} / イベント {len(event_map)}")

except Exception as e:
    print(f"解析エラー: {e}")
