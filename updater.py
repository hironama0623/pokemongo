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

print(f"[{now_str}] 4大サイト深掘りクローラー＆クロスチェック解析（レイド/DMax自動対策生成付）を開始します...")

try:
    with open("data.json", "r", encoding="utf-8") as f:
        existing_data = json.load(f)
except Exception:
    existing_data = {}

existing_news = existing_data.get("latest_news", [])
existing_fr_updates = existing_data.get("field_research_updates", {})
existing_events = existing_data.get("dynamic_events", [])
existing_dyn_raids = existing_data.get("dynamic_raids", {})
existing_dyn_dmax = existing_data.get("dynamic_dmax", {})

scrape_log = {
    "executed_at": now_str,
    "status": "running",
    "model_used": "",
    "crawled_pages": [],
    "verified_field_researches": {},
    "updated_events": [],
    "added_or_updated_raids": [],
    "added_or_updated_dmax": [],
    "errors": []
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
}

def extract_clean_content(html_text: str, max_chars: int = 11000) -> tuple[str, str, str]:
    """
    9DBやGameWith、ポケマピのテーブル内で画像アイコン(<img alt="ポケモン名">)だけで
    表現されている報酬ポケモン名を確実にテキスト化して抽出する
    """
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

    # ★重要: <img>タグのaltやtitleやdata-originalにポケモン名が入っている場合、テキストとして展開する
    for img in soup.find_all("img"):
        alt_txt = img.get("alt", "") or img.get("title", "") or img.get("data-name", "")
        alt_txt = alt_txt.strip()
        if alt_txt and len(alt_txt) <= 25 and not any(w in alt_txt.lower() for w in ["logo", "icon", "banner", "button", "アイコン", "バナー"]):
            img.replace_with(f" [{alt_txt}] ")

    # リンクのtitle属性などにもポケモン名があれば補完
    for a_tag in soup.find_all("a"):
        if not a_tag.get_text(strip=True) and a_tag.get("title"):
            a_tag.string = f" [{a_tag.get('title').strip()}] "

    general_lines = []
    priority_research_lines = []
    in_priority_section = False

    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr"]):
        if el.name in ["h1", "h2", "h3", "h4"]:
            txt = el.get_text(" ", strip=True)
            if not txt:
                continue
            header_line = f"\n### 【{txt}】"
            general_lines.append(header_line)
            if any(k in txt for k in ["フィールドリサーチ", "タスク", "リサーチ", "サプライズボックス", "GOパス", "タイムチャレンジ", "野生", "レイド", "マックス"]):
                in_priority_section = True
                priority_research_lines.append(header_line)
            else:
                in_priority_section = False
        elif el.name == "tr":
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["th", "td"]) if c.get_text(strip=True)]
            if cells:
                row_str = " | ".join(cells)
                general_lines.append(row_str)
                if in_priority_section or any(k in row_str for k in ["捕まえる", "投げる", "勝つ", "進化", "強化", "スピン", "ヤバチャ", "ピカチュウ", "ズバット", "ミカルゲ", "ボチ", "バケッチャ", "ゾロア", "ヒトモシ", "ヤミラミ"]):
                    priority_research_lines.append(row_str)
        else:
            if el.find_parent("tr"):
                continue
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) >= 2:
                general_lines.append(txt)
                if in_priority_section:
                    priority_research_lines.append(txt)

    def dedup_list(lst):
        res = []
        for item in lst:
            if not res or res[-1] != item:
                res.append(item)
        return res

    gen_text = "\n".join(dedup_list(general_lines))[:5500]
    prio_text = "\n".join(dedup_list(priority_research_lines))[:6000]

    combined = gen_text
    if prio_text:
        combined += "\n\n--- [重要セクション（フィールドリサーチ・報酬ポケモン名・ギミック抜粋）] ---\n" + prio_text

    return title, date_hint, combined[:max_chars]

scraped_docs = []
visited_urls = set()

def fetch_and_record(source_name: str, url: str, max_chars: int = 11000) -> Optional[BeautifulSoup]:
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
        scraped_docs.append(f"=== [サイト名: {source_name}] {title} ({url}) ===\n{body}")
        scrape_log["crawled_pages"].append({"source": source_name, "url": url, "title": title, "date_hint": date_hint})
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        scrape_log["errors"].append(f"{source_name} ({url}): {str(e)}")
        return None

# 1. ポケマピ (イベント一覧 + 個別記事8件)
soup_pm = fetch_and_record("ポケマピ", "https://pokemongo-get.com/events/", 7000)
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
        fetch_and_record("ポケマピ", u, 11000)

# 2. GameWith (トップ + イベントまとめ + タスク一覧 + 個別イベント記事5件)
gw_seeds = [
    "https://pokemongo.gamewith.jp/",
    "https://pokemongo.gamewith.jp/article/show/24434",
    "https://pokemongo.gamewith.jp/article/show/102210"
]
gw_sub_urls = []
for gw_u in gw_seeds:
    soup_gw = fetch_and_record("GameWith", gw_u, 9000)
    if soup_gw:
        for a in soup_gw.find_all("a", href=re.compile(r"article/show/\d+")):
            txt = a.get_text(strip=True)
            href = a["href"]
            if not href.startswith("http"):
                href = "https://pokemongo.gamewith.jp" + href
            if any(k in txt for k in ["ハロウィン", "イベント", "GOパス", "リサーチ", "ワイルド", "シャンデラ", "ヤミラミ", "ダークライ", "クレセリア"]):
                if href not in visited_urls and href not in gw_sub_urls:
                    gw_sub_urls.append(href)
            if len(gw_sub_urls) >= 5:
                break
for u in gw_sub_urls:
    fetch_and_record("GameWith", u, 11000)

# 3. 9DB みんポケ (トップ + 個別イベント・リサーチ記事5件)
soup_9db = fetch_and_record("9DBみんポケ", "https://9db.jp/pokemongo/", 9000)
if soup_9db:
    db_urls = []
    for a in soup_9db.find_all("a", href=re.compile(r"/pokemongo/data/\d+")):
        u = a["href"]
        if not u.startswith("http"):
            u = "https://9db.jp" + u
        if u not in visited_urls and u not in db_urls:
            db_urls.append(u)
        if len(db_urls) >= 5:
            break
    for u in db_urls:
        fetch_and_record("9DBみんポケ", u, 11000)

# 4. 公式サイト
fetch_and_record("公式サイト", "https://pokemongo.com/ja/news", 7500)

combined_text = "\n\n".join(scraped_docs)
print(f"巡回完了: 合計 {len(scrape_log['crawled_pages'])} ページ ({len(combined_text)} 文字) を抽出しました。")

# ==============================================================================
# Pydantic スキーマ定義（野生と固有ギミックの分離・新規レイド/DMax対策自動生成対応）
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
    name: str = Field(description="純粋に『野生』で出現する具体的なポケモン名（サプライズボックス限定等は含めない）")
    shiny: bool
    note: str = Field(description="野生出現の補足（レア枠、初登場衣装など）")

class SpecialGimmickSpawnSchema(BaseModel):
    gimmick_name: str = Field(description="イベント固有ギミック名（例：📦 ハロウィンのサプライズボックス、🔥 おこう限定出現、🏅 コレクションチャレンジ 等）")
    description: str = Field(description="そのギミックの仕様や入手方法の説明")
    spawns_or_rewards: List[WildSpawnSchema] = Field(description="そのギミックから出現・入手できる具体的なポケモンやアイテム一覧")

class EventRaidRefSchema(BaseModel):
    dex: int
    name: str
    shiny: bool
    note: str
    targetKey: str = Field(description="対策タブと連動するボスキー（例: giratina-origin, darkrai, cresselia, mega-banette, deoxys-normal, dmax-sableye 等）")
    isDmax: bool = False

class FieldResearchItemSchema(BaseModel):
    task: str = Field(description="ポケストップから入手する正確なタスク条件文")
    rewardDex: int = Field(description="代表的な報酬ポケモンの図鑑番号")
    rewardName: str = Field(description="【重要】『ゴーストタイプポケモン』『〇〇等』『イベント対象ポケモン』といった省略表現は絶対禁止！必ず出現する全ての具体的なポケモン名を ' / ' 区切りで明記すること（例：'ヤミラミ / ヒトモシ / ゾロア' や 'バケッチャ(ちいさい) / バケッチャ(ふつう) / バケッチャ(おおきい) / バケッチャ(とくだい)'）")
    shiny: bool
    note: str = Field(default="", description="CP範囲や補足")
    verified_sources: List[str] = Field(description="確認できた出典サイト名リスト")

class SpecialTaskItemSchema(BaseModel):
    task: str = Field(description="タイムチャレンジやスペシャルリサーチの名称・条件")
    rewardDex: int
    rewardName: str = Field(description="具体的な報酬ポケモン名とアイテム名（省略禁止）")
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
    wilds: List[WildSpawnSchema] = Field(description="純粋な野生出現ポケモン一覧（最低5〜8種は具体的に抽出すること）")
    specialGimmicks: List[SpecialGimmickSpawnSchema] = Field(default_factory=list, description="サプライズボックス等のイベント固有ギミックがある場合のみ出力（無いイベントは空配列）")
    raids: List[EventRaidRefSchema]
    fieldResearches: List[FieldResearchItemSchema]
    tasks: List[SpecialTaskItemSchema]

# --- 新規レイドボス＆ダイマックスボス対策の自動生成スキーマ ---
class MegaRecUnitSchema(BaseModel):
    dex: int
    name: str
    move: str = ""
    type: str = ""
    desc: str

class MegaRecPairSchema(BaseModel):
    attack: List[MegaRecUnitSchema]
    candy: List[MegaRecUnitSchema]

class RaidCounterUnitSchema(BaseModel):
    name: str
    dex: int
    tag: str = Field(description="'normal', 'mega', 'shadow' のいずれか")
    dps: float
    tdo: int
    fast: str
    charge: str

class RaidBossDataSchema(BaseModel):
    key: str = Field(description="イベントの targetKey と一致する一意のキー（例: 'darkrai', 'cresselia', 'mega-banette', 'deoxys-normal', 'mega-metagross'）")
    month: int
    startDay: int
    endDay: int
    name: str
    status: str
    tier: str
    dex: int
    types: List[str]
    shiny: bool
    shinyText: str
    cpNormal: str
    cpBoost: str
    minPlayers: str
    tactics: str
    megaRecs: MegaRecPairSchema
    counters: List[RaidCounterUnitSchema] = Field(description="通常ポケモン・メガ・シャドウを含む対策ランキング（10〜14体）")

class DmaxMoveColorSchema(BaseModel):
    name: str
    color: str = Field(description="Tailwind背景色クラス（例: bg-purple-700, bg-indigo-600, bg-red-600）")

class DmaxUnitSchema(BaseModel):
    rank: int
    name: str
    dex: int
    fast: str
    charge: str

class DmaxRoutineStepSchema(BaseModel):
    step: int
    title: str
    details: List[str]

class DmaxBossDataSchema(BaseModel):
    key: str = Field(description="イベントの targetKey と一致する一意のキー（例: 'dmax-latios', 'dmax-cryogonal'）")
    month: int
    startDay: int
    endDay: int
    name: str
    tier: str
    dateInfo: str
    status: str
    dex: int
    types: List[str]
    shiny: bool
    shinyText: str
    cpPL20: str
    moves: List[DmaxMoveColorSchema]
    attackers: List[DmaxUnitSchema] = Field(description="4サイト基準のアタッカーTOP5")
    tanks: List[DmaxUnitSchema] = Field(description="耐久・0.5秒技タンクTOP5")
    tankNote: str
    routine: List[DmaxRoutineStepSchema]

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
    new_or_updated_raids: List[RaidBossDataSchema] = Field(default_factory=list, description="新しく判明・登場する★5伝説・メガ・スーパーメガ・シャドウレイドボスの対策データ")
    new_or_updated_dmax: List[DmaxBossDataSchema] = Field(default_factory=list, description="新しく判明・登場するダイマックス・キョダイマックスボスの対策データ")
    event_gopass: Optional[EventGoPassUpdateSchema] = None

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

prompt = f"""
あなたはポケモンGOの4大攻略サイト（ポケマピ、GameWith、9DBみんポケ、公式サイト）のデータを統合・照合するマスターデータベースAIです。
現在の日本時間: {now_str} (今日の日付: {today_str} / 対象月: {valid_months})

【絶対遵守の4大ルール】
1. **フィールドリサーチの省略表記（『〇〇等』『ゴーストタイプポケモン』『イベント対象ポケモン』）の完全禁止！**:
   - スクレイピングテキスト内の `[ポケモン名]` や捕獲CPから、具体的なポケモン名を必ず特定してすべて列挙してください。
   - 例えば「ゴーストタイプのポケモンを13匹捕まえる」なら `ミカルゲ` (CP460) や `ヤミラミ`、「ナイススローを6回投げる」なら `バケッチャ(ちいさい / ふつう / おおきい / とくだい)` のように、**具体的なポケモン名を1匹残らず明記**してください。『ゴーストタイプポケモン』『イベント対象ポケモン』『バケッチャ等』のような曖昧な出力は厳禁です。
2. **「野生出現 (`wilds`)」と「サプライズボックス等のイベント固有ギミック (`specialGimmicks`)」の明確な分離**:
   - `wilds` には純粋に野生で出現するポケモン（ズバット(トップハット)、フワライド(ハロウィン)、ゾロア、ヒトモシ、ヤミラミ、ボチ、カゲボウズ、ボクレー、バケッチャ等）を整理して出力してください。
   - 「ハロウィンのサプライズボックス」や「コレクションチャレンジ」「おこう限定」など、そのイベント特有の仕組みで手に入るポケモン・アイテムは `specialGimmicks` に独立させて詳しく出力してください（ギミックが無いイベントでは `specialGimmicks` は空配列 `[]` にする）。
3. **新規レイドボス・ダイマックスボスの対策ページ自動生成 (`new_or_updated_raids`, `new_or_updated_dmax`)**:
   - イベント内の `raids` に含まれる主要ボス（★5伝説、メガレイド、スーパーメガレイド、★5〜6マックスバトル）には必ず `targetKey`（例: `darkrai`, `cresselia`, `mega-banette`, `deoxys-normal`, `mega-metagross`, `dmax-latios`, `dmax-cryogonal` 等）を設定し、新しいボスが登場していれば `new_or_updated_raids` または `new_or_updated_dmax` に完全な対策データ（DPS/TDOランキング、おすすめメガ2軸、アタッカー/タンクTOP5）を出力してください。
4. **既存イベントID一覧**:
   - "ev-halloween-p1" (ハロウィン2026パート1: 10/27〜11/1)
   - "ev-halloween-p2" (ハロウィン2026パート2: 11/1〜11/5)
   - "ev-supermega-chandelure" (シャンデラのスーパーメガレイドデイ: 10/31)
   - "ev-dmax-sableye-week" (ダイマックスヤミラミ週間: 10/26〜11/1)
   - "ev-raid-giratina-o" (ギラティナオリジン・メガヤミラミ: 10/28〜)
   - "ev-dmax-machop-week" (ダイマックスワンリキー週間: 11/2〜11/8)
   - "ev-gopass-nov" (GOパス11月・グラードン: 11/3〜)
   - "ev-wildweek-2026" (ワイルドウィーク: 11/9〜11/13)
   - "ev-wildarea-2026" (GOワイルドエリア2026グローバル: 11/14〜11/15)
   - "ev-big-footprints" (大きな足跡イベント・クレセリア/ダークライ/メガジュペッタ: 11/16〜11/24)
   - "ev-cd-pawniard" (コマタナのコミュニティデイ: 11/21)
   - "ev-tusk-wish-deoxys" (黄昏時の願い・デオキシス/メガメタグロス: 11/24〜)
   - "ev-dec-new-season" (新シーズン＆DMaxフリージオ: 12/1〜)

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
            print(f"Geminiモデル ({model_name}) でクロスチェック解析を実行中...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AIOutputSchema,
                    temperature=0.0
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
                    response = client.models.generate_content(
                        model=clean_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=AIOutputSchema,
                            temperature=0.0
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

    # 曖昧な報酬名をブロックするフィルタ関数
    VAGUE_REWARD_WORDS = ["ゴーストタイプポケモン", "イベント対象ポケモン", "イベントポケモン", "対象ポケモン", "ポケモン遭遇"]
    def is_specific_reward_name(r_name: str) -> bool:
        if not r_name:
            return False
        for vw in VAGUE_REWARD_WORDS:
            if r_name.strip() == vw or r_name.strip() == vw + "等":
                return False
        return True

    # 1. イベントとフィールドリサーチの整合性フィルタリング＆統合
    event_map = {ev["id"]: ev for ev in existing_events if isinstance(ev, dict) and "id" in ev}
    merged_fr_updates = dict(existing_fr_updates) if isinstance(existing_fr_updates, dict) else {}

    for ev_obj in parsed.dynamic_events:
        ev_dict = ev_obj.model_dump()
        ev_id = ev_dict["id"]
        if ev_dict["month"] in valid_months:
            raw_frs = ev_dict.get("fieldResearches", [])
            verified_frs = []
            for fr in raw_frs:
                sources = fr.get("verified_sources", [])
                task_txt = fr.get("task", "")
                r_name = fr.get("rewardName", "")
                # 「等」で終わっていたら除去し、曖昧な汎用名（「ゴーストタイプポケモン」等）は弾く
                r_name_clean = re.sub(r"など$|等$", "", r_name.strip())
                fr["rewardName"] = r_name_clean
                if task_txt and "イベント限定フィールドリサーチ" not in task_txt and is_specific_reward_name(r_name_clean) and len(sources) >= 1:
                    src_label = "・".join(sources)
                    fr["note"] = f"{fr.get('note', '')} [確認: {src_label}]".strip()
                    verified_frs.append(fr)

            if verified_frs:
                ev_dict["fieldResearches"] = verified_frs
                merged_fr_updates[ev_id] = verified_frs
                scrape_log["verified_field_researches"][ev_id] = verified_frs
            else:
                # もしAIが曖昧な名前しか出せなかった場合は、既存の良質なフィールドリサーチを潰さないよう空にする
                ev_dict["fieldResearches"] = []

            event_map[ev_id] = ev_dict
            scrape_log["updated_events"].append(ev_id)

    # 2. 新規・更新レイドボス対策データの統合
    merged_dyn_raids = dict(existing_dyn_raids) if isinstance(existing_dyn_raids, dict) else {}
    for rb in parsed.new_or_updated_raids:
        rb_dict = rb.model_dump()
        r_key = rb_dict.pop("key", "")
        if r_key and rb_dict.get("counters"):
            merged_dyn_raids[r_key] = rb_dict
            scrape_log["added_or_updated_raids"].append(r_key)

    # 3. 新規・更新ダイマックスボス対策データの統合
    merged_dyn_dmax = dict(existing_dyn_dmax) if isinstance(existing_dyn_dmax, dict) else {}
    for db in parsed.new_or_updated_dmax:
        db_dict = db.model_dump()
        d_key = db_dict.pop("key", "")
        if d_key and db_dict.get("attackers"):
            merged_dyn_dmax[d_key] = db_dict
            scrape_log["added_or_updated_dmax"].append(d_key)

    # 4. ニュースの統合
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
        "dynamic_raids": merged_dyn_raids,
        "dynamic_dmax": merged_dyn_dmax,
        "event_gopass": parsed.event_gopass.model_dump() if parsed.event_gopass else existing_data.get("event_gopass", {})
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    scrape_log["status"] = "success"
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 更新完了: ニュース {len(valid_news)}件 / イベント {len(event_map)}件 / 動的レイド {len(merged_dyn_raids)}件 / 動的DMax {len(merged_dyn_dmax)}件")

except Exception as e:
    err_msg = traceback.format_exc()
    print(f"解析エラー:\n{err_msg}")
    scrape_log["status"] = "error"
    scrape_log["errors"].append(err_msg)
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)
    exit(1)
