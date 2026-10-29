import os
import json
import time
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

print(f"[{now_str}] 2段階AI解析クローラー（①フィールドリサーチ全件 / ②イベント・対策）を開始します...")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {}

existing_news = existing_data.get("latest_news", [])
existing_fr_updates = existing_data.get("field_research_updates", {})
existing_all_fr = existing_data.get("all_field_researches", [])
existing_events = existing_data.get("dynamic_events", [])
existing_dyn_raids = existing_data.get("dynamic_raids", {})
existing_dyn_dmax = existing_data.get("dynamic_dmax", {})

scrape_log = {
    "executed_at": now_str,
    "status": "running",
    "model_used": "",
    "available_models_detected": [],
    "crawled_pages": [],
    "extracted_research_count": 0,
    "updated_events": [],
    "errors": []
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

def extract_html_text(html_text: str, is_research_only: bool = False, max_chars: int = 10000) -> tuple[str, str]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = soup.find("title").get_text(strip=True) if soup.find("title") else "No Title"

    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe", "svg"]):
        tag.decompose()

    for img in soup.find_all("img"):
        alt_txt = (img.get("alt") or img.get("title") or img.get("data-name") or "").strip()
        src_txt = img.get("data-src") or img.get("src") or ""
        if alt_txt and len(alt_txt) <= 30 and not any(w in alt_txt.lower() for w in ["logo", "banner", "button", "icon"]):
            img.replace_with(f" [{alt_txt}] ")
        elif src_txt:
            m_dex = re.search(r"/(\d{1,4})(?:_\d+)?\.(?:png|jpg|webp)", src_txt)
            if m_dex:
                img.replace_with(f" [図鑑No:{m_dex.group(1)}] ")

    for a_tag in soup.find_all("a"):
        t_attr = (a_tag.get("title") or a_tag.get("data-name") or "").strip()
        if not a_tag.get_text(strip=True) and t_attr:
            a_tag.string = f" [{t_attr}] "

    lines = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr"]):
        if el.name in ["h1", "h2", "h3", "h4"]:
            txt = el.get_text(" ", strip=True)
            if txt:
                lines.append(f"\n### 【{txt}】")
        elif el.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["th", "td"]) if c.get_text(strip=True)]
            if cells:
                lines.append(" | ".join(cells))
        else:
            if el.find_parent("tr"):
                continue
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) >= 2:
                if not is_research_only or any(k in txt for k in ["捕まえる", "投げる", "勝つ", "進化", "強化", "スピン", "孵化", "相棒", "写真", "GOロケット団", "レイド", "CP", "イベント", "タスク"]):
                    lines.append(txt)

    dedup = []
    for line in lines:
        if not dedup or dedup[-1] != line:
            dedup.append(line)
    return title, "\n".join(dedup)[:max_chars]

event_docs = []
research_docs = []
visited_urls = set()

def fetch_page(source_name: str, url: str, target_list: list, is_research_only: bool = False, max_chars: int = 10000) -> Optional[BeautifulSoup]:
    if url in visited_urls:
        return None
    visited_urls.add(url)
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            return None
        res.encoding = res.apparent_encoding or "utf-8"
        title, body = extract_html_text(res.text, is_research_only=is_research_only, max_chars=max_chars)
        if any(old_y in title for old_y in ["2022", "2023", "2024", "2025"]) and str(now.year) not in title:
            return None
        target_list.append(f"=== [出典: {source_name}] {title} ({url}) ===\n{body}")
        scrape_log["crawled_pages"].append({"source": source_name, "url": url, "title": title, "chars": len(body)})
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        scrape_log["errors"].append(f"{source_name} ({url}): {str(e)}")
        return None

# --- A. フィールドリサーチ専用ページ（3サイト）を収集 ---
for src, r_url in [
    ("ポケマピ(リサーチ一覧)", "https://pokemongo-get.com/research_field/"),
    ("GameWith(タスク一覧)", "https://pokemongo.gamewith.jp/article/show/102210"),
    ("9DBみんポケ(リサーチ一覧)", "https://9db.jp/pokemongo/data/1508")
]:
    fetch_page(src, r_url, research_docs, is_research_only=True, max_chars=12000)

# --- B. イベント・最新記事を収集 ---
soup_pm = fetch_page("ポケマピ(イベント)", "https://pokemongo-get.com/events/", event_docs, False, 6500)
if soup_pm:
    pm_urls = []
    for a in soup_pm.find_all("a", href=re.compile(r"/board/\d+/")):
        u = a["href"] if a["href"].startswith("http") else "https://pokemongo-get.com" + a["href"]
        if u not in visited_urls and u not in pm_urls:
            pm_urls.append(u)
        if len(pm_urls) >= 5:
            break
    for u in pm_urls:
        fetch_page("ポケマピ(記事)", u, event_docs, False, 9000)
        if event_docs:
            research_docs.append(event_docs[-1][:6000])

fetch_page("GameWith(イベント)", "https://pokemongo.gamewith.jp/article/show/24434", event_docs, False, 7500)
fetch_page("9DB(トップ)", "https://9db.jp/pokemongo/", event_docs, False, 7500)
fetch_page("公式サイト", "https://pokemongo.com/ja/news", event_docs, False, 6500)

# ==============================================================================
# Gemini API 利用可能モデル自動検出 ＆ 共通呼び出し関数
# ==============================================================================
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

def get_available_flash_models() -> List[str]:
    primary_3_flash = []
    secondary_flash = []
    try:
        for m in client.models.list():
            m_name = getattr(m, "name", "").replace("models/", "")
            if "gemini" in m_name and "flash" in m_name:
                if any(x in m_name for x in ["tts", "image", "vision", "audio", "thinking"]):
                    continue
                if "3" in m_name or "latest" in m_name:
                    primary_3_flash.append(m_name)
                else:
                    secondary_flash.append(m_name)
    except Exception as e:
        print(f"モデル一覧取得警告: {e}")

    found_models = primary_3_flash + secondary_flash
    fallbacks = [
        "gemini-3-flash-preview",
        "gemini-3.0-flash-preview",
        "gemini-3.0-flash-001",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite"
    ]
    for fb in fallbacks:
        if fb not in found_models:
            found_models.append(fb)

    scrape_log["available_models_detected"] = found_models
    return found_models

AVAILABLE_MODELS = get_available_flash_models()

def call_gemini_structured(prompt_text: str, schema_cls):
    for m_name in AVAILABLE_MODELS:
        try:
            print(f"モデル [{m_name}] で解析を実行中...")
            resp = client.models.generate_content(
                model=m_name,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_cls,
                    temperature=0.0
                )
            )
            if resp and resp.text:
                scrape_log["model_used"] = m_name
                print(f"成功: [{m_name}] で構造化データを取得しました！")
                time.sleep(5)  # 無料枠のレート制限回避ウェイト
                return schema_cls.model_validate_json(resp.text)
        except Exception as err:
            print(f"[{m_name}] スキップ: {err}")
    raise RuntimeError("すべてのモデル候補からの構造化レスポンス取得に失敗しました。")

# ==============================================================================
# Step 1: フィールドリサーチ全件（イベント限定 ＋ 常設）の専門解析
# ==============================================================================
class FullResearchItemSchema(BaseModel):
    category: str = Field(description="'event' (イベント限定), 'catch' (捕獲・スロー系), 'battle' (レイド・バトル系), 'explore' (探索・強化・進化・孵化系), 'mega' (メガエナジー・アイテム報酬) のいずれか")
    event_id: str = Field(default="", description="categoryが'event'の場合、対応するイベントID（例: 'ev-halloween-p1', 'ev-halloween-p2' 等。常設なら空文字）")
    EventName: str = Field(default="", description="イベント限定ならイベント名（例: '🎃 ハロウィン2026 限定'）、常設なら '🌿 シーズン常設'")
    task: str = Field(description="ポケストップから入手する正確なタスク条件文")
    rewardDex: int = Field(description="メイン報酬ポケモンの全国図鑑番号")
    rewardName: str = Field(description="【省略絶対禁止】出現する具体的なポケモン名すべて（複数候補は ' / ' 区切り。『ゴーストタイプポケモン』『イベント対象ポケモン』『〇〇等』は厳禁）")
    shiny: bool = Field(description="色違いチャンスの有無")
    cp_info: str = Field(default="", description="100%CPやCP範囲（例: 'CP451〜488'）")
    verified_sites: List[str] = Field(description="確認したサイト名（ポケマピ, GameWith, 9DB）")

class Step1ResearchOutput(BaseModel):
    all_researches: List[FullResearchItemSchema]

research_prompt = f"""
あなたはポケモンGOの「フィールドリサーチ（ポケストップのタスク）」専門のデータベースAIです。
現在日時: {now_str}

以下の3大攻略サイト（ポケマピ・GameWith・9DBみんポケ）のリサーチ専用ページから、現在入手可能なフィールドリサーチを「イベント限定 (`category: 'event'`)」と「常設 (`category: 'catch' | 'battle' | 'explore' | 'mega'`)」に分けて抽出し、一覧化してください。

【絶対ルール】
1. **『ゴーストタイプポケモン』『イベント対象ポケモン』『〇〇等』といった省略表記は100%禁止！**
   必ず具体的なポケモン名（例：`ピカチュウ(ハットとケープ)`, `ズバット(トップハット)`, `ヤバチャ(リボン)`, `ミカルゲ`, `ボチ`, `バケッチャ(ちいさい) / バケッチャ(ふつう) / バケッチャ(おおきい) / バケッチャ(とくだい)`, `ヒトモシ`, `ゾロア`, `ヤミラミ`, `パッチール` など）をすべて列挙してください。
2. 表の中でポケモン名が画像になっていてCP数値だけ書かれている場合は、以下のPL15（リサーチ捕獲時100%CP）から逆引きして正確なポケモン名を特定してください：
   - CP285〜286 = ズバット(トップハット)
   - CP402 = ピカチュウ(ハットとケープ)
   - CP431 = ヒトモシ
   - CP460 = ボチ または ポッチャマ(ハロウィン)
   - CP488 = ヤバチャ(リボン)
   - CP503 = ゾロア
   - CP515 / 523 / 533 / 536 = バケッチャ(ちいさい / ふつう / おおきい / とくだい)
   - CP632 = ヤミラミ
   - CP825 = モルペコ または ムウマ
   - CP888 = ミカルゲ
3. ハロウィン2026パート1のイベント限定タスクには `category: "event"`, `event_id: "ev-halloween-p1"` を設定してください（11/1からのパート2なら `ev-halloween-p2`）。

【リサーチ専用スクレイピングテキスト】:
{chr(10).join(research_docs)}
"""

# ==============================================================================
# Step 2: イベント・ニュース・GOパスの専門解析
# ==============================================================================
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

class SpecialGimmickSpawnSchema(BaseModel):
    gimmick_name: str
    description: str
    spawns_or_rewards: List[WildSpawnSchema]

class EventRaidRefSchema(BaseModel):
    dex: int
    name: str
    shiny: bool
    note: str
    targetKey: str
    isDmax: bool = False

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
    dateText: str
    summary: str
    freeFeatures: List[str]
    paidFeatures: List[str]
    wilds: List[WildSpawnSchema]
    specialGimmicks: List[SpecialGimmickSpawnSchema] = Field(default_factory=list)
    raids: List[EventRaidRefSchema]
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

class Step2EventOutput(BaseModel):
    new_news: List[NewsItemSchema]
    dynamic_events: List[EventItemSchema]
    event_gopass: Optional[EventGoPassUpdateSchema] = None

event_prompt = f"""
あなたはポケモンGOのイベント・ニュース統合AIです。現在日時: {now_str} (対象月: {valid_months})
以下のスクレイピングテキストから、最新ニュース(`new_news`)、イベント詳細(`dynamic_events`)、イベント連動GOパス(`event_gopass`)を抽出してください。
※野生出現(`wilds`)と、サプライズボックス等の固有ギミック(`specialGimmicks`)は明確に分け、新規イベントがあれば `ev-` から始まるIDを付与してください。

【イベントスクレイピングテキスト】:
{chr(10).join(event_docs)}
"""

try:
    # --- Step 1 実行 (フィールドリサーチ専門解析) ---
    print("Step 1: フィールドリサーチ全件を解析中...")
    res_step1: Step1ResearchOutput = call_gemini_structured(research_prompt, Step1ResearchOutput)

    VAGUE_WORDS = ["ゴーストタイプポケモン", "イベント対象ポケモン", "イベントポケモン", "対象ポケモン", "ポケモン遭遇", "ランダム"]
    def is_clean_poke_name(name_str: str) -> bool:
        if not name_str:
            return False
        c = re.sub(r"など$|等$", "", name_str.strip())
        return c not in VAGUE_WORDS

    clean_all_researches = []
    merged_fr_updates = dict(existing_fr_updates) if isinstance(existing_fr_updates, dict) else {}
    ev_fr_bucket = {}

    for r_item in res_step1.all_researches:
        d = r_item.model_dump()
        d["rewardName"] = re.sub(r"など$|等$", "", d["rewardName"].strip())
        if not is_clean_poke_name(d["rewardName"]):
            continue
        sites_str = "・".join(d.get("verified_sites", [])) or "3サイト照合"
        note_str = f"{d.get('cp_info', '')} [確認: {sites_str}]".strip()
        d["note"] = note_str
        clean_all_researches.append(d)

        if d["category"] == "event" and d.get("event_id"):
            ev_id = d["event_id"]
            ev_fr_bucket.setdefault(ev_id, []).append({
                "task": d["task"],
                "rewardDex": d["rewardDex"],
                "rewardName": d["rewardName"],
                "shiny": d["shiny"],
                "note": note_str
            })

    for ev_id, fr_list in ev_fr_bucket.items():
        if len(fr_list) > 0:
            merged_fr_updates[ev_id] = fr_list

    if not clean_all_researches:
        clean_all_researches = existing_all_fr

    scrape_log["extracted_research_count"] = len(clean_all_researches)
    print(f"Step 1 完了: 有効なフィールドリサーチ {len(clean_all_researches)} 件を抽出しました。")

    # --- Step 2 実行 (イベント・ニュース解析) ---
    print("Step 2: イベント・ニュース・GOパスを解析中...")
    res_step2: Step2EventOutput = call_gemini_structured(event_prompt, Step2EventOutput)

    event_map = {ev["id"]: ev for ev in existing_events if isinstance(ev, dict) and "id" in ev}
    for ev_obj in res_step2.dynamic_events:
        ev_dict = ev_obj.model_dump()
        ev_id = ev_dict["id"]
        if ev_dict["month"] in valid_months:
            if ev_id in merged_fr_updates:
                ev_dict["fieldResearches"] = merged_fr_updates[ev_id]
            event_map[ev_id] = ev_dict
            scrape_log["updated_events"].append(ev_id)

    all_news_pool = [n.model_dump() for n in res_step2.new_news] + existing_news
    seen_ids, seen_titles, unique_news = set(), set(), []
    for item in all_news_pool:
        nid, ntitle, ndetails = item.get("id", ""), item.get("title", ""), item.get("details", "")
        if not nid or not ntitle or not ndetails:
            continue
        if any(bk in ntitle or bk in ndetails for bk in ["UMA", "ユクシー", "オリオン座"]):
            continue
        t_key = re.sub(r"\s+", "", ntitle)[:20]
        if nid not in seen_ids and t_key not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(t_key)
            unique_news.append(item)

    # 日付フォーマットの揺れ（2026/10/29 18:00 など）を修正して安全にパース
    valid_news = []
    for item in unique_news:
        date_str = item.get("date", today_str)
        # スラッシュをハイフンに、スペース以降(時刻)を削除して正規化
        safe_date_str = date_str.replace("/", "-").split(" ")[0]
        try:
            dt = datetime.datetime.strptime(safe_date_str, "%Y-%m-%d").date()
            if (now.date() - dt).days <= 14:
                valid_news.append(item)
        except Exception as e:
            # パースできなくてもとりあえず残す（クラッシュ回避）
            print(f"日付パースエラー回避: {item.get('date')} -> {e}")
            valid_news.append(item)

    valid_news.sort(key=lambda x: str(x.get("date", today_str)).replace("/", "-").split(" ")[0], reverse=True)

    final_data = {
        "updated_at": now_str,
        "latest_news": valid_news[:10],
        "all_field_researches": clean_all_researches,
        "field_research_updates": merged_fr_updates,
        "dynamic_events": list(event_map.values()),
        "dynamic_raids": existing_dyn_raids,
        "dynamic_dmax": existing_dyn_dmax,
        "event_gopass": res_step2.event_gopass.model_dump() if res_step2.event_gopass else existing_data.get("event_gopass", {})
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    scrape_log["status"] = "success"
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 全更新完了: リサーチ {len(clean_all_researches)}件 / イベント {len(event_map)}件")

except Exception as e:
    err_msg = traceback.format_exc()
    print(f"解析エラー:\n{err_msg}")
    scrape_log["status"] = "error"
    scrape_log["errors"].append(err_msg)
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)
    exit(1)
