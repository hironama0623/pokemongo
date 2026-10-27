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

# ==============================================================================
# 1. 日時設定・初期化
# ==============================================================================
jst = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(jst)
today_str = now.strftime("%Y-%m-%d")
now_str = now.strftime("%Y/%m/%d %H:%M JST")
one_month_ago = (now - datetime.timedelta(days=31)).date()

# 現在の月・来月・再来月を動的に計算（年越しにも対応）
valid_months = [
    now.month,
    (now.month % 12) + 1,
    ((now.month + 1) % 12) + 1
]

print(f"[{now_str}] 4大サイト深掘りクローラー＆Gemini構造化解析を開始します...")

# 既存の data.json を読み込む
try:
    with open("data.json", "r", encoding="utf-8") as f:
        master_data = json.load(f)
except Exception as e:
    print(f"data.json 読み込みエラー（新規初期化します）: {e}")
    master_data = {}

master_data.setdefault("latest_news", [])
master_data.setdefault("events", [])
master_data.setdefault("raids", {})
master_data.setdefault("dmax", {})
master_data.setdefault("event_gopass", {})

# 監査ログ用オブジェクト
scrape_log = {
    "executed_at": now_str,
    "status": "running",
    "crawled_pages": [],
    "added_events": [],
    "updated_events": [],
    "added_news": [],
    "updated_raids_dmax": [],
    "errors": []
}

# ==============================================================================
# 2. 直近1ヶ月以内の記事を深掘りするマルチサイトクローラー
# ==============================================================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
}

def extract_clean_content(html_text: str, max_chars: int = 8500) -> tuple[str, str, str]:
    """HTMLからタイトル、更新日らしき文字列、構造化テキスト（見出し・表・箇条書き）を抽出"""
    soup = BeautifulSoup(html_text, "html.parser")
    title = soup.find("title").get_text(strip=True) if soup.find("title") else "No Title"

    # 更新日時メタデータの検出試行
    date_hint = ""
    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        if any(k in prop.lower() for k in ["modified", "published", "date", "time"]):
            date_hint = meta.get("content", "")[:19]
            if date_hint:
                break
    if not date_hint:
        time_tag = soup.find("time")
        if time_tag:
            date_hint = time_tag.get("datetime", "") or time_tag.get_text(strip=True)

    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe", "svg", "form"]):
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
            # tr内のテキスト重複を避ける
            if el.find_parent("tr"):
                continue
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) >= 2:
                lines.append(txt)

    # 連続する同一行を除去
    dedup_lines = []
    for line in lines:
        if not dedup_lines or dedup_lines[-1] != line:
            dedup_lines.append(line)

    body_text = "\n".join(dedup_lines)[:max_chars]
    return title, date_hint, body_text

def is_recent_or_active_article(title: str, date_hint: str, body: str) -> bool:
    """直近1ヶ月以内に更新された記事、または現在〜今後のイベント・対策記事かを判定"""
    # 明らかな過去年（2024年・2025年以前）の専用記事を除外
    for old_year in ["2022", "2023", "2024", "2025"]:
        if old_year in title and str(now.year) not in title:
            return False

    # メタ日付が取得できた場合は1ヶ月以内か判定
    if date_hint:
        m = re.search(r"(202\d)[-/年](\d{1,2})[-/月](\d{1,2})", date_hint)
        if m:
            try:
                dt = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return dt >= one_month_ago
            except Exception:
                pass
    return True

scraped_docs = []
visited_urls = set()

def fetch_and_record(source_name: str, url: str, max_chars: int = 8500) -> Optional[BeautifulSoup]:
    """URLを取得してテキストを記録し、リンク抽出用のBeautifulSoupを返す"""
    if url in visited_urls:
        return None
    visited_urls.add(url)
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        if res.status_code != 200:
            scrape_log["errors"].append(f"{source_name} HTTP {res.status_code}: {url}")
            return None
        res.encoding = res.apparent_encoding or "utf-8"
        title, date_hint, body = extract_clean_content(res.text, max_chars=max_chars)
        if is_recent_or_active_article(title, date_hint, body):
            scraped_docs.append(f"==============================\n[出典: {source_name}] {title}\nURL: {url} (更新目安: {date_hint or '直近'})\n------------------------------\n{body}")
            scrape_log["crawled_pages"].append({
                "source": source_name,
                "url": url,
                "title": title,
                "date_hint": date_hint,
                "chars": len(body)
            })
        return BeautifulSoup(res.text, "html.parser")
    except Exception as e:
        scrape_log["errors"].append(f"{source_name} 取得失敗 ({url}): {str(e)}")
        return None

# --- ① ポケマピ (イベントカレンダー + 個別記事最大8件) ---
soup_pm = fetch_and_record("ポケマピ(一覧)", "https://pokemongo-get.com/events/", 7000)
if soup_pm:
    pm_links = []
    for a in soup_pm.find_all("a", href=re.compile(r"/board/\d+/")):
        u = a["href"]
        if not u.startswith("http"):
            u = "https://pokemongo-get.com" + u
        if u not in visited_urls and u not in pm_links:
            pm_links.append(u)
        if len(pm_links) >= 8:
            break
    for u in pm_links:
        fetch_and_record("ポケマピ(個別記事)", u, 9000)

# --- ② GameWith (トップ + イベント/タスク/レイド常設ページ + 最新個別記事最大5件) ---
gw_seed_urls = [
    "https://pokemongo.gamewith.jp/",
    "https://pokemongo.gamewith.jp/article/show/24434",  # イベント最新まとめ
    "https://pokemongo.gamewith.jp/article/show/102210", # フィールドリサーチ一覧
    "https://pokemongo.gamewith.jp/article/show/35286"   # レイドボス対策一覧
]
gw_sub_links = []
for gw_u in gw_seed_urls:
    soup_gw = fetch_and_record("GameWith(主要)", gw_u, 7500)
    if soup_gw and gw_u == "https://pokemongo.gamewith.jp/":
        # トップページからイベント・GOパス・ハロウィン・ダイマックス関連の個別記事を抽出
        for a in soup_gw.find_all("a", href=re.compile(r"article/show/\d+")):
            txt = a.get_text(strip=True)
            href = a["href"]
            if not href.startswith("http"):
                href = "https://pokemongo.gamewith.jp" + href
            if any(k in txt for k in ["イベント", "ハロウィン", "GOパス", "ダイマックス", "キョダイ", "レイド", "リサーチ", "ワイルド", "コミュデイ", "ヤミラミ", "シャンデラ"]):
                if href not in visited_urls and href not in gw_sub_links:
                    gw_sub_links.append(href)
            if len(gw_sub_links) >= 5:
                break

for u in gw_sub_links:
    fetch_and_record("GameWith(個別記事)", u, 8500)

# --- ③ 9DB みんポケ (トップ + 最新イベント・対策サブ記事最大5件) ---
soup_9db = fetch_and_record("9DBみんポケ(トップ)", "https://9db.jp/pokemongo/", 8000)
if soup_9db:
    db_links = []
    for a in soup_9db.find_all("a", href=re.compile(r"/pokemongo/data/\d+")):
        txt = a.get_text(strip=True)
        href = a["href"]
        if not href.startswith("http"):
            href = "https://9db.jp" + href
        if any(k in txt for k in ["イベント", "ハロウィン", "パス", "マックス", "レイド", "タスク", "リサーチ", "ヤミラミ", "シャンデラ", "ワイルド"]):
            if href not in visited_urls and href not in db_links:
                db_links.append(href)
        if len(db_links) >= 5:
            break
    for u in db_links:
        fetch_and_record("9DBみんポケ(個別記事)", u, 8500)

# --- ④ Pokémon GO 公式サイト (日本語ニュース一覧 + 最新個別ニュース3件) ---
soup_off = fetch_and_record("公式サイト(ニュース一覧)", "https://pokemongo.com/ja/news", 6000)
if soup_off:
    off_links = []
    for a in soup_off.find_all("a", href=re.compile(r"^/ja/post/|pokemongo\.com/ja/post/")):
        href = a["href"]
        if not href.startswith("http"):
            href = "https://pokemongo.com" + href
        if href not in visited_urls and href not in off_links:
            off_links.append(href)
        if len(off_links) >= 3:
            break
    for u in off_links:
        fetch_and_record("公式サイト(個別発表)", u, 7500)

combined_scraped_text = "\n\n".join(scraped_docs)
print(f"巡回完了: 合計 {len(scrape_log['crawled_pages'])} ページから {len(combined_scraped_text)} 文字を抽出しました。")

# ==============================================================================
# 3. Gemini 構造化出力用 Pydantic スキーマ定義 (JSON破損を100%防止)
# ==============================================================================
class NewsItemSchema(BaseModel):
    id: str = Field(description="一意の英数字スラッグ (例: news-halloween-box-detail)")
    date: str = Field(description="YYYY-MM-DD形式の日付")
    date_label: str = Field(description="M/D形式の日付ラベル (例: 10/27)")
    title: str = Field(description="ニュースのタイトル。既存イベントへの詳細追加の場合は【更新】を先頭につける")
    details: str = Field(description="ニュースや更新内容の具体的な要約（2〜3文）")
    targetId: str = Field(description="連動するイベントID (例: ev-halloween-p1)")
    is_update_notice: bool = Field(default=False, description="既存イベントの詳細判明・追記ニュースならTrue、完全新規発表ならFalse")

class WildSpawnSchema(BaseModel):
    dex: int = Field(description="ポケモンの全国図鑑番号または特殊フォルムID")
    name: str = Field(description="ポケモン名（衣装やフォルム名含む）")
    shiny: bool = Field(description="色違い出現の有無")
    note: str = Field(description="出現方法や補足（野生、レア、サプライズボックス等）")

class EventRaidRefSchema(BaseModel):
    dex: int
    name: str
    shiny: bool
    note: str = Field(description="★5伝説、★1レイド、マックスバトル等")
    targetKey: str = Field(default="", description="対策タブと連動するキー（例: dmax-sableye, giratina-origin 等。なければ空文字）")
    isDmax: bool = Field(default=False, description="ダイマックス・キョダイマックスならTrue")

class FieldResearchItemSchema(BaseModel):
    task: str = Field(description="具体的なタスク条件（例：ゴーストタイプのポケモンを5匹捕まえる）")
    rewardDex: int = Field(description="報酬ポケモンの図鑑番号")
    rewardName: str = Field(description="報酬ポケモン名（複数候補やアイテム付記も可）")
    shiny: bool = Field(description="色違いチャンスの有無")
    note: str = Field(default="", description="CP範囲や補足")

class SpecialTaskItemSchema(BaseModel):
    task: str = Field(description="サプライズボックス、タイムチャレンジ、コレクションチャレンジ等の名称や条件")
    rewardDex: int = Field(description="代表的な報酬ポケモンの図鑑番号（アイテムのみの場合は25など関連ポケモンの番号）")
    rewardName: str = Field(description="判明した具体的な報酬ポケモンや中身の詳細")
    shiny: bool = Field(default=True)

class EventItemSchema(BaseModel):
    id: str = Field(description="既存イベントなら既存のIDを維持、新規イベントなら 'ev-' から始まる一意の英数字ID")
    month: int = Field(description="開催月 (1〜12)")
    title: str = Field(description="イベント名")
    barClass: str = Field(description="bar-main, bar-cd, bar-raid, bar-dmax, bar-collab, bar-shadow-daily のいずれか")
    category: str = Field(description="main, cd, raid, dmax, collab のいずれか")
    barIconDex: int = Field(description="ガントチャートに表示する代表ポケモンの図鑑番号")
    startDay: int = Field(description="その月における開始日 (1〜31)")
    endDay: int = Field(description="その月における終了日 (1〜31)")
    hasPaid: bool = Field(description="有料チケットや有料GOパスデラックスが存在するか")
    hasFieldResearchPending: bool = Field(default=False, description="フィールドリサーチが未判明ならTrue、判明済みならFalse")
    dateText: str = Field(description="開催期間のわかりやすい文字列")
    summary: str = Field(description="イベントの全体概要（サプライズボックス等の新判明仕様も反映）")
    freeFeatures: List[str] = Field(description="無料で全トレーナーができること・ボーナス・サプライズボックス詳細など")
    paidFeatures: List[str] = Field(description="有料チケットやデラックスパスで追加される要素")
    wilds: List[WildSpawnSchema] = Field(description="野生やサプライズボックス等で手に入る注目ポケモン一覧")
    raids: List[EventRaidRefSchema] = Field(description="イベント中に出現するレイド・マックスバトル一覧")
    fieldResearches: List[FieldResearchItemSchema] = Field(description="ポケストップから入手できるイベント限定フィールドリサーチ一覧")
    tasks: List[SpecialTaskItemSchema] = Field(description="タイムチャレンジ・サプライズボックスの中身・特別報酬一覧")

class GoPassRowSchema(BaseModel):
    rank: str = Field(description="ランク表記（例: 'Rank 1', 'Rank 10', 'Rank 1〜100主要' など）")
    free_reward: str = Field(description="無料パスの報酬・ポケモン・ボーナス")
    free_dex: int = Field(default=0, description="無料報酬にポケモンが含まれる場合の図鑑番号（なければ0）")
    deluxe_reward: str = Field(description="有料デラックス版の追加報酬・ポケモン・ボーナス")
    deluxe_dex: int = Field(default=0, description="有料報酬にポケモンが含まれる場合の図鑑番号（なければ0）")

class EventGoPassUpdateSchema(BaseModel):
    title: str = Field(description="イベント連動GOパス名（例：GOパス：ハロウィン2026）")
    period: str = Field(description="開催期間と受取期限")
    price_info: str = Field(description="料金情報（例：無料版あり / デラックス: 1,120円）")
    free_summary: List[str] = Field(description="無料版の主要メリット箇条書き")
    deluxe_summary: List[str] = Field(description="有料デラックス版の主要メリット箇条書き")
    reward_rows: List[GoPassRowSchema] = Field(description="判明しているランク別の報酬・出現ポケモン一覧表")

class DmaxMoveUnitSchema(BaseModel):
    rank: int
    name: str
    dex: int
    fast: str
    charge: str

class DmaxBossUpdateSchema(BaseModel):
    key: str = Field(description="dmax-sableye 等のボスキー")
    attackers: List[DmaxMoveUnitSchema] = Field(description="4サイトを総合した対策アタッカーTOP5（DMaxヤミラミにはサーナイト等を必ず含める）")
    tanks: List[DmaxMoveUnitSchema] = Field(description="対策タンクTOP5")
    tankNote: str = Field(description="4サイト統合の実戦対策ノート")

class AIExtractionOutput(BaseModel):
    new_or_updated_news: List[NewsItemSchema]
    updated_or_new_events: List[EventItemSchema]
    event_gopass_update: Optional[EventGoPassUpdateSchema] = None
    dmax_updates: List[DmaxBossUpdateSchema] = Field(default_factory=list)

# ==============================================================================
# 4. Gemini API 実行 & マスターデータ統合
# ==============================================================================
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("エラー: GEMINI_API_KEY が未設定です。")
    exit(1)

client = genai.Client(api_key=api_key)

# 現在のイベント一覧のサマリーをAIに渡す（固定リストではなく、動的に現在のdata.jsonから生成）
current_events_summary = []
for ev in master_data.get("events", []):
    fr_count = len(ev.get("fieldResearches", []))
    current_events_summary.append(
        f"- ID: '{ev.get('id')}' | 月: {ev.get('month')}月({ev.get('startDay')}〜{ev.get('endDay')}日) | タイトル: {ev.get('title')} | 現在の登録リサーチ数: {fr_count}件"
    )
current_events_context = "\n".join(current_events_summary)

prompt = f"""
あなたはポケモンGOの4大攻略サイト（ポケマピ、GameWith、9DBみんポケ、公式サイト）の情報を統合・照合するマスターデータベース管理AIです。
現在の日本時間: {now_str} (今日の日付: {today_str} / 対象月: {valid_months})

【現在 `data.json` に登録されているイベント一覧】
{current_events_context}

【あなたのミッション（重要度順）】
1. **未登録の「新規イベント」の自動追加 & 既存イベントの「詳細アップデート」 (`updated_or_new_events`)**
   - スクレイピングテキスト内に、上記一覧にまだ無い新しいイベント（11月〜12月の新イベント、レイドデイ、マックスマンデー等）があれば、新規ID（`ev-` + 英数字）を振って出力してください。
   - **既に一覧にあるイベント（特に現在開催中の `ev-halloween-p1` ハロウィンパート1や `ev-halloween-p2` 等）について、以下の詳細が判明していれば、必ず最新情報で充実させて出力してください：**
     - **イベント限定フィールドリサーチ (`fieldResearches`)**: 「ゴーストタイプのポケモンを〇匹捕まえる」「ポケモンを〇匹捕まえる」等の具体的なタスク条件と、報酬ポケモン（ピカチュウ(ハット&ケープ)、ズバット(トップハット)、ヤバチャ(リボン)、ミカルゲ、ボチ等）の完全なリスト。
     - **ポケモンが手に入るギミック詳細 (`freeFeatures`, `wilds`, `tasks`)**: ハロウィンイベントの「サプライズボックス（マップ上のプレゼント箱タップでお菓子やハロウィン衣装ポケモン・ヤバチャ・ゾロア等が出現する仕様）」や、無料配布タイムチャレンジ、野生出現ポケモンの詳細。

2. **新着ニュース ＆「既存イベントの更新告知」の生成 (`new_or_updated_news`)**
   - 新しいイベントが発表された場合はもちろん、**「すでに発表済みのイベントについて、開始後にフィールドリサーチのタスク条件やサプライズボックスの中身、GOパス報酬詳細が新しく判明した」場合も、必ず `【更新】〇〇イベントの限定フィールドリサーチ＆サプライズボックス詳細が判明！` のようなニュース項目を作成して出力してください。**

3. **GOパス：ハロウィン2026 等のイベント連動パス詳細の抽出 (`event_gopass_update`)**
   - GOパス：ハロウィン2026（または直近のイベント連動GOパス）について、無料枠・有料デラックス枠で手に入る具体的なポケモン（ロコン、ヤミラミ、ミカルゲ、衣装ポケモン等）やランク別報酬（Rank1〜Rank100の節目報酬）が記事内にあれば、`event_gopass_update` に抽出してください。

4. **ダイマックス対策の4サイト照合アップデート (`dmax_updates`)**
   - 特に `dmax-sableye`（ダイマックスヤミラミ）は弱点がフェアリーのみ（1.6倍）です。4サイト（ポケマピ・GameWith・9DB）を照らし合わせ、アタッカーTOP5には必ず **「サーナイト（あまえる / マジカルシャイン・ダイフェアリー、dex: 282）」** や「ザシアン(けんのおう)(dex: 10188)」「キョダイオーロンゲ(dex: 10222)」「ブリムオン(dex: 858)」「アシレーヌ(dex: 730) / トゲキッス(dex: 468)」など、フェアリー弱点を突ける正確な対策ポケモンをまとめてください。

【図鑑番号（`dex` / `rewardDex`）の指定ルール】
基本は全国図鑑番号（例：ピカチュウ=25, ズバット=41, ゲンガー=94, サーナイト=282, ヤミラミ=302, ミカルゲ=442, ゾロア=570, ヒトモシ=607, シャンデラ=609, コマタナ=624, モクロー=722, ヤバチャ=854, ブリムオン=858, ボチ=971, ドドゲザン=983）を指定し、特殊フォルムは以下を使用してください：
- ザシアン(けんのおう): 10188 / ザマゼンタ(たてのおう): 10189 / ギラティナ(オリジン): 10007
- ブラックキュレム: 10022 / ホワイトキュレム: 10023 / ディアルガ(オリジン): 10245 / パルキア(オリジン): 10246
- メガサーナイト: 10051 / メガヤミラミ: 10066 / キョダイオーロンゲ: 10222 / キョダイジュラルドン: 10225

【スクレイピング取得テキスト（直近巡回データ）】:
{combined_scraped_text}
"""

try:
    response = None
    for model_name in ["gemini-2.5-pro", "gemini-2.5-flash"]:
        try:
            print(f"Geminiモデル ({model_name}) で構造化解析を実行中...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=AIExtractionOutput,
                    temperature=0.1
                )
            )
            if response and response.text:
                break
        except Exception as api_err:
            print(f"{model_name} 呼び出し警告: {api_err}")

    if not response or not response.text:
        raise RuntimeError("すべてのGeminiモデルから有効な応答を得られませんでした。")

    parsed: AIExtractionOutput = AIExtractionOutput.model_validate_json(response.text)

    # --------------------------------------------------------------------------
    # A. イベントの統合（新規追加 ＆ 既存イベントの全フィールド賢いマージ）
    # --------------------------------------------------------------------------
    existing_events_ById = {ev["id"]: ev for ev in master_data.get("events", []) if "id" in ev}
    auto_generated_update_news = []

    for new_ev in parsed.updated_or_new_events:
        ev_dict = new_ev.model_dump()
        ev_id = ev_dict["id"]

        if ev_id not in existing_events_ById:
            # タイトル類似チェック（同じイベントに別IDが振られた場合の吸収）
            matched_id = None
            for ex_id, ex_ev in existing_events_ById.items():
                if ex_ev.get("month") == ev_dict["month"] and ex_ev.get("startDay") == ev_dict["startDay"]:
                    if ex_ev.get("title", "")[:6] == ev_dict["title"][:6]:
                        matched_id = ex_id
                        break
            if matched_id:
                ev_id = matched_id
                ev_dict["id"] = matched_id

        if ev_id not in existing_events_ById:
            # 完全新規イベントの追加
            if ev_dict["month"] in valid_months:
                existing_events_ById[ev_id] = ev_dict
                scrape_log["added_events"].append({"id": ev_id, "title": ev_dict["title"]})
        else:
            # 既存イベントのアップデート（詳細が判明した項目を上書き・拡張）
            ex_ev = existing_events_ById[ev_id]
            updated_fields = []

            # 1. フィールドリサーチの更新判定（具体的なタスク名が入ったか、件数が増えた場合）
            old_frs = ex_ev.get("fieldResearches", [])
            new_frs = ev_dict.get("fieldResearches", [])
            had_generic_fr = any("イベント限定フィールドリサーチ" in f.get("task", "") for f in old_frs)
            has_specific_fr = any("イベント限定フィールドリサーチ" not in f.get("task", "") for f in new_frs)

            if new_frs and (len(new_frs) > len(old_frs) or (had_generic_fr and has_specific_fr)):
                ex_ev["fieldResearches"] = new_frs
                ex_ev["hasFieldResearchPending"] = False
                updated_fields.append("限定フィールドリサーチのタスク条件・報酬")

            # 2. サプライズボックスやタイムチャレンジ (`tasks`) の更新
            old_tasks = ex_ev.get("tasks", [])
            new_tasks = ev_dict.get("tasks", [])
            if new_tasks and len(json.dumps(new_tasks, ensure_ascii=False)) > len(json.dumps(old_tasks, ensure_ascii=False)):
                ex_ev["tasks"] = new_tasks
                updated_fields.append("サプライズボックス・チャレンジ報酬詳細")

            # 3. 野生出現ポケモン (`wilds`) の更新
            old_wilds = ex_ev.get("wilds", [])
            new_wilds = ev_dict.get("wilds", [])
            if new_wilds and len(new_wilds) >= len(old_wilds):
                ex_ev["wilds"] = new_wilds
                if len(new_wilds) > len(old_wilds):
                    updated_fields.append("出現ポケモン一覧")

            # 4. 無料ボーナス・特徴 (`freeFeatures`, `summary`) の更新
            if ev_dict.get("freeFeatures") and len(ev_dict["freeFeatures"]) >= len(ex_ev.get("freeFeatures", [])):
                ex_ev["freeFeatures"] = ev_dict["freeFeatures"]
            if ev_dict.get("summary") and len(ev_dict["summary"]) > len(ex_ev.get("summary", "")):
                ex_ev["summary"] = ev_dict["summary"]

            if updated_fields:
                scrape_log["updated_events"].append({
                    "id": ev_id,
                    "title": ex_ev.get("title"),
                    "updated_fields": updated_fields
                })
                # もしAIが更新ニュースを作っていなかった場合でも、システム側で確実に更新告知ニュースを生成
                auto_generated_update_news.append({
                    "id": f"news-update-{ev_id}-{now.strftime('%m%d')}",
                    "date": today_str,
                    "date_label": f"{now.month}/{now.day}",
                    "title": f"【更新】「{ex_ev.get('title')}」の{'＆'.join(updated_fields)}が判明・反映されました！",
                    "details": f"最新情報に基づき、{ex_ev.get('title')}の{'、'.join(updated_fields)}をイベント詳細欄にアップデートしました。タップして確認できます。",
                    "targetId": ev_id,
                    "is_update_notice": True
                })

    # イベントを開始月・開始日順にソートして格納
    sorted_events = sorted(
        existing_events_ById.values(),
        key=lambda x: (x.get("month", 99) if x.get("month", 99) >= now.month else x.get("month", 99) + 12, x.get("startDay", 1))
    )
    master_data["events"] = sorted_events

    # --------------------------------------------------------------------------
    # B. GOパス（イベント連動パス）の更新反映
    # --------------------------------------------------------------------------
    if parsed.event_gopass_update and parsed.event_gopass_update.reward_rows:
        gp_dict = parsed.event_gopass_update.model_dump()
        master_data["event_gopass"] = gp_dict
        scrape_log["updated_events"].append({"id": "event_gopass", "title": gp_dict.get("title")})

    # --------------------------------------------------------------------------
    # C. ダイマックス対策（サーナイト等の4サイト照合結果）の更新反映
    # --------------------------------------------------------------------------
    for dmax_up in parsed.dmax_updates:
        d_key = dmax_up.key
        if d_key in master_data.get("dmax", {}):
            if dmax_up.attackers:
                master_data["dmax"][d_key]["attackers"] = [a.model_dump() for a in dmax_up.attackers]
            if dmax_up.tanks:
                master_data["dmax"][d_key]["tanks"] = [t.model_dump() for t in dmax_up.tanks]
            if dmax_up.tankNote:
                master_data["dmax"][d_key]["tankNote"] = dmax_up.tankNote
            scrape_log["updated_raids_dmax"].append(d_key)

    # --------------------------------------------------------------------------
    # D. 最新ニュース ＆ 更新速報の統合・重複排除
    # --------------------------------------------------------------------------
    incoming_news = [n.model_dump() for n in parsed.new_or_updated_news] + auto_generated_update_news
    all_news_pool = incoming_news + master_data.get("latest_news", [])

    seen_ids = set()
    seen_titles = set()
    merged_news = []
    banned_words = ["UMA", "ユクシー", "アグノム", "エムリット", "オリオン座"]

    for item in all_news_pool:
        nid = item.get("id", "")
        ntitle = item.get("title", "")
        ndetails = item.get("details", "")
        if not nid or not ntitle or not ndetails:
            continue
        if any(bw in ntitle or bw in ndetails for bw in banned_words):
            continue
        # タイトルの先頭22文字で重複ニュースをブロック
        title_key = re.sub(r"\s+", "", ntitle)[:22]
        if nid not in seen_ids and title_key not in seen_titles:
            seen_ids.add(nid)
            seen_titles.add(title_key)
            merged_news.append(item)
            if item in incoming_news:
                scrape_log["added_news"].append(ntitle)

    # 直近14日以内のニュースを新しい順に最大10件保持
    valid_news = []
    for item in merged_news:
        d_str = item.get("date", today_str)
        try:
            dt = datetime.datetime.strptime(d_str, "%Y-%m-%d").date()
            if (now.date() - dt).days <= 14:
                valid_news.append(item)
        except Exception:
            valid_news.append(item)

    valid_news.sort(key=lambda x: x.get("date", today_str), reverse=True)
    master_data["latest_news"] = valid_news[:10]
    master_data["updated_at"] = now_str

    # --------------------------------------------------------------------------
    # E. data.json と scrape_log.json の保存
    # --------------------------------------------------------------------------
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(master_data, f, ensure_ascii=False, indent=2)

    scrape_log["status"] = "success"
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)

    print(f"[{now_str}] 正常更新完了: ニュース {len(master_data['latest_news'])}件 / イベント総数 {len(master_data['events'])}件")

except Exception as e:
    err_detail = traceback.format_exc()
    print(f"致命的な解析エラー:\n{err_detail}")
    scrape_log["status"] = "error"
    scrape_log["errors"].append(err_detail)
    with open("scrape_log.json", "w", encoding="utf-8") as f:
        json.dump(scrape_log, f, ensure_ascii=False, indent=2)
    # ※エラー時に古いデータで data.json を破壊しないよう、data.json の無理な上書きは行わず終了
    exit(1)
