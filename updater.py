import os
import json
import datetime
import re
import traceback
from typing import List, Optional
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# 日本時間 (JST)
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
today_str = now.strftime("%Y-%m-%d")
now_str = now.strftime("%Y/%m/%d %H:%M JST")
valid_months = [now.month, (now.month % 12) + 1, ((now.month + 1) % 12) + 1]

print(f"[{now_str}] 4大サイト深掘りクローラー＆Gemini構造化解析を開始します...")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {}

existing_news = existing_data.get("latest_news", [])
existing_fr_updates = existing_data.get("field_research_updates", {})
existing_events = existing_data.get("dynamic_events", [])

scrape_log = {
    "executed_at": now_str,
    "status": "running",
    "model_used": "",
    "crawled_pages": [],
    "updated_events": [],
    "added_news": [],
    "errors": []
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

def extract_clean_content(html_text: str, max_chars: int = 8000) -> tuple[str, str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = soup.find("title").get_text(strip=True) if soup.find("title") else "No Title"

    date_hint = ""
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if any(k in prop.lower() for k in ["modified", "published", "date"]):
            date_hint = meta.get("content", "")[:19]
            if date_hint:
                break

    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe", "svg"]):
        tag.decompose()

    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr"]):
        if el.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["th", "td"]) if c.get_text(strip=True)]
            if cells:
                lines.append(" | ".join(cells))
        elif el.name in ["h1", "h2", "h3", "h4"]:
            txt = el.get_text(" ", strip=True)
            if txt:
                lines.append(f"\n### 【{txt}】")
        else:
            if el.find_parent("tr"):
                continue
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) >= 2:
                lines.append(txt)

    dedup = []
    for line in lines:
        if not dedup or dedup[-1] != line:
            dedup.append(line)
    return title, date_hint, "\n".join(dedup)[:max_chars]

scraped_docs = []
visited_urls = set()

def fetch_and_record(source_name: str, url: str, max_chars: int = 8000) -> Optional[BeautifulSoup]:
    if url in visited_urls:
        return None
    visited_urls.add(url)
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return None
        res.encoding = res.apparent_encoding or "utf-8"
        title, date_hint, body = extract_clean_content(res.text, max_chars=max_chars)
        if any(old_y in title for old_y in ["2022", "2023", "2024", "2025"]) and str(now.year) not in title:
            return None
        scraped_docs.append(f"=== [{source_name}] {title} ({url}) ===\n{body}")
        scrape_log["crawled_pages"].append({"source": source_name, "url": url, "title": title, "date_hint": date_hint})
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        scrape_log["errors"].append(f"{source_name} ({url}): {str(e)}")
        return None

# 1. ポケマピ (一覧 + 最新記事8件)
soup_pm = fetch_and_record("ポケマピ一覧", "https://pokemongo-get.com/events/", 7000)
if soup_pm:
    pm_urls = []
    for a in soup_pm.find_all("a", href=re.compile(r"/board/\d+/")):
        u = a["href"]
        if not u.startswith("http"):
            u = "https://pokemongo-get.com" + u
        if u not in visited_urls and u not in pm_urls:
            pm_urls.append(u)
        if len(pm_urls) >= 8:
            break
    for u in pm_urls:
        fetch_and_record("ポケマピ記事", u, 8500)

# 2. GameWith (トップ + イベント/タスク一覧)
for gw_u in ["https://pokemongo.gamewith.jp/", "https://pokemongo.gamewith.jp/article/show/24434", "https://pokemongo.gamewith.jp/article/show/102210"]:
    fetch_and_record("GameWith", gw_u, 7500)

# 3. 9DB みんポケ (トップ + サブ記事4件)
soup_9db = fetch_and_record("9DBトップ", "https://9db.jp/pokemongo/", 7500)
if soup_9db:
    db_urls = []
    for a in soup_9db.find_all("a", href=re.compile(r"/pokemongo/data/\d+")):
        u = a["href"]
        if not u.startswith("http"):
            u = "https://9db.jp" + u
        if u not in visited_urls and u not in db_urls:
            db_urls.append(u)
        if len(db_urls) >= 4:
            break
    for u in db_urls:
        fetch_and_record("9DB記事", u, 8000)

# 4. 公式サイト
fetch_and_record("公式サイト", "https://pokemongo.com/ja/news", 7000)

combined_text = "\n\n".join(scraped_docs)
print(f"巡回完了: 合計 {len(scrape_log['crawled_pages'])} ページ ({len(combined_text)} 文字) を抽出しました。")

# Pydantic スキーマ定義
class NewsItemSchema(BaseModel):
    id: str
    date: str
    date_label: str
    title: str
    details: str
    targetId: str
    is_update_notice: bool = False

class WildSpawnSchema(BaseModel):
    dex: int
    name: str
    shiny: bool
    note: str

class EventRaidRefSchema(BaseModel):
    dex: int
    name: str
    shiny: bool
    note: str
    targetKey: str = ""
    isDmax: bool = False

class FieldResearchItemSchema(BaseModel):
    task: str
    rewardDex: int
    rewardName: str
    shiny: bool
    note: str = ""

class SpecialTaskItemSchema(BaseModel):
    task: str
    rewardDex: int
    rewardName: str
    shiny: bool = True

class EventItemSchema(BaseModel):
    id: str
    month: int
    title: str
    barClass: str
    category: str
    barIconDex: int
    startDay: int
    endDay: int
    hasPaid: bool
    hasFieldResearchPending: bool = False
    dateText: str
    summary: str
    freeFeatures: List[str]
    paidFeatures: List[str]
    wilds: List[WildSpawnSchema]
    raids: List[EventRaidRefSchema]
    fieldResearches: List[FieldResearchItemSchema]
    tasks: List[SpecialTaskItemSchema]

class GoPassRowSchema(BaseModel):
    rank: str
    free_reward: str
    free_dex: int = 0
    deluxe_reward: str
    deluxe_dex: int = 0

class EventGoPassUpdateSchema(BaseModel):
    title: str
    period: str
    free_summary: List[str]
    deluxe_summary: List[str]
    reward_rows: List[GoPassRowSchema]

class AIOutputSchema(BaseModel):
    new_news: List[NewsItemSchema]
    dynamic_events: List[EventItemSchema]
    event_gopass: Optional[EventGoPassUpdateSchema] = None

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGO攻略サイト（ポケマピ、GameWith、9DB、公式サイト）の情報を統合するAIです。
現在の日本時間: {now_str} (今日の日付: {today_str} / 対象月: {valid_months})

【重要ルール】
1. 既存イベントID一覧（該当イベントの更新時は必ずこのIDを維持してください。一覧にない新規イベントは `ev-` から始まる新IDを付与してください）：
   - "ev-halloween-p1" (ハロウィン2026パート1: 10/27〜11/1)
   - "ev-halloween-p2" (ハロウィン2026パート2: 11/1〜11/5)
   - "ev-supermega-chandelure" (シャンデラのスーパーメガレイドデイ: 10/31)
   - "ev-dmax-sableye-week" (ダイマックスヤミラミ週間: 10/26〜11/1)
   - "ev-raid-giratina-o" (ギラティナオリジン・メガヤミラミ: 10/28〜)
   - "ev-dmax-machop-week" (ダイマックスワンリキー週間: 11/2〜11/8)
   - "ev-gopass-nov" (GOパス11月・グラードン: 11/3〜)
   - "ev-wildweek-2026" (ワイルドウィーク: 11/9〜11/13)
   - "ev-wildarea-2026" (GOワイルドエリア2026グローバル: 11/14〜11/15)
   - "ev-big-footprints" (大きな足跡イベント: 11/16〜11/24)
   - "ev-cd-pawniard" (コマタナのコミュニティデイ: 11/21)
   - "ev-tusk-wish-deoxys" (黄昏時の願い・デオキシス: 11/24〜)

2. 既存イベント（特に開催中のハロウィンイベント等）について、「フィールドリサーチの具体的なタスク条件と報酬ポケモン」「サプライズボックスの中身・出現ポケモン」「GOパスのランク別報酬」などの詳細が記載されていれば、`dynamic_events` と `event_gopass` に漏れなく出力してください。
3. 新規イベントの発表だけでなく、発表済みイベントに新しい詳細（タスク条件やサプライズボックス詳細など）が判明した場合も、`new_news` に `【更新】〇〇イベントの限定タスク・詳細が判明！`（`is_update_notice: true`）としてニュースを追加してください。

【スクレイピング取得テキスト】:
{combined_text}
"""

try:
    response = None
    candidate_models = [
        "gemini-3.0-flash",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "gemini-2.0-flash"
    ]

    for model_name in candidate_models:
        try:
            print(f"Geminiモデル ({model_name}) で構造化解析を実行中...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AIOutputSchema,
                    temperature=0.1
                )
            )
            if response and response.text:
                scrape_log["model_used"] = model_name
                print(f"成功: {model_name} で応答を取得しました。")
                break
        except Exception as api_err:
            print(f"{model_name} スキップ: {api_err}")

    if not response or not response.text:
        for m in client.models.list():
            m_name = getattr(m, "name", "")
            if "gemini" in m_name and "flash" in m_name:
                try:
                    clean_name = m_name.replace("models/", "")
                    print(f"自動検出モデル ({clean_name}) で再試行中...")
                    response = client.models.generate_content(
                        model=clean_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=AIOutputSchema,
                            temperature=0.1
                        )
                    )
                    if response and response.text:
                        scrape_log["model_used"] = clean_name
                        break
                except Exception:
                    continue

    if not response or not response.text:
        raise RuntimeError("利用可能なGeminiモデルから応答を取得できませんでした。")

    parsed: AIOutputSchema = AIOutputSchema.model_validate_json(response.text)

    # 1. イベントとフィールドリサーチの統合
    event_map = {ev["id"]: ev for ev in existing_events if isinstance(ev, dict) and "id" in ev}
    merged_fr_updates = dict(existing_fr_updates) if isinstance(existing_fr_updates, dict) else {}

    for ev_obj in parsed.dynamic_events:
        ev_dict = ev_obj.model_dump()
        ev_id = ev_dict["id"]
        if ev_dict["month"] in valid_months:
            event_map[ev_id] = ev_dict
            scrape_log["updated_events"].append(ev_id)
            if ev_dict.get("fieldResearches"):
                merged_fr_updates[ev_id] = ev_dict["fieldResearches"]

    # 2. ニュースの統合
    all_news_pool = [n.model_dump() for n in parsed.new_news] + existing_news
    seen_ids = set()
    seen_titles = set()
    unique_news = []
    banned_keywords = ["UMA", "ユクシー", "オリオン座"]

    for item in all_news_pool:
        nid = item.get("id", "")
        ntitle = item.get("title", "")
        ndetails = item.get("details", "")
        if not nid or not ntitle or not ndetails:
            continue
        if any(bk in ntitle or bk in ndetails for bk in banned_keywords):
            continue
        t_key = re.sub(r"\s+", "", ntitle)[:20]
        if nid not in seen_ids and t_key not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(t_key)
            unique_news.append(item)

    valid_news = []
    for item in unique_news:
        d_str = item.get("date", today_str)
        try:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            if (now.date() - dt).days <= 14:
                valid_news.append(item)
        except Exception:
            valid_news.append(item)

    valid_news.sort(key=lambda x: x.get("date", today_str), reverse=True)
    valid_news = valid_news[:10]

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news,
        "field_research_updates": merged_fr_updates,
        "dynamic_events": list(event_map.values()),
        "event_gopass": parsed.event_gopass.model_dump() if parsed.event_gopass else existing_data.get("event_gopass", {})
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    scrape_log["status"] = "success"
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 更新完了: ニュース {len(valid_news)} 件 / イベント {len(event_map)} 件")

except Exception as e:
    err_msg = traceback.format_exc()
    print(f"解析エラー:\n{err_msg}")
    scrape_log["status"] = "error"
    scrape_log["errors"].append(err_msg)
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)
    exit(1)
