"""設定。取得先・期間・上限はここだけで管理する（SPEC.md 5章）。"""
import datetime as dt
import os
from pathlib import Path

JST = dt.timezone(dt.timedelta(hours=9))
ROOT = Path(os.environ.get("POGO_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
LOGS = ROOT / "logs"

WINDOW_DAYS = 31            # 直近この日数以内に更新された記事だけ解析対象
REQUEST_INTERVAL = float(os.environ.get("REQUEST_INTERVAL", "1.0"))  # 秒
TIMEOUT = 20
RETRIES = 2
ANALYZE_BUDGET_SEC = int(os.environ.get("ANALYZE_BUDGET_SEC", "1320"))  # AI解析に使う最大秒数(22分)。超過分は次回の実行に回す
AI_MIN_INTERVAL = float(os.environ.get("AI_MIN_INTERVAL", "6.0"))  # AI呼び出し間隔(秒)。429対策
AI_TIMEOUT_SEC = int(os.environ.get("AI_TIMEOUT_SEC", "90"))  # 1回のAI呼び出しの待ち時間上限
MAX_AI_CHARS = 60000        # AIに渡す上限。切り詰めた場合は chars_sent に反映される
NEWS_RETENTION_DAYS = 45
LOG_RETENTION_DAYS = 30

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# 先頭から順に試す。モデルの提供終了(404)時は次へ。名前は https://ai.google.dev/gemini-api/docs/models で確認
GEMINI_MODELS = [m for m in dict.fromkeys([os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"), "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]) if m]

# max_articles: 1回に見る記事の上限 / min_chars: これ未満は「本文が取れていない疑い」(suspect_empty)
# link_re: 記事URLの正規表現（group(1)=記事キー）。min_id: これ未満の数値IDは古い記事として無視。
# 数値IDでないサイト（公式）は一覧の並び順（新しい順）で上位 max_articles 件を見る。
# 解析の中身（プロンプト・抽出方法）を変えたら上げる。全記事が一度だけ解析し直される
ANALYSIS_VERSION = "2"

SITE_PRIORITY = {"official": 0, "pokemapi": 1, "9db": 2, "gamewith": 3}   # 解析の優先順（上限に達したとき後ろは次回へ回る）

SOURCES = {
    "pokemapi": {
        "label": "ポケマピ",
        "indexes": ["https://pokemongo-get.com/pokego02416/", "https://pokemongo-get.com/"],
        "hubs": ["https://pokemongo-get.com/research_fi/"],
        "link_re": r"^https://pokemongo-get\.com/board/(\d+)/?$",
        "min_id": 10450, "max_articles": 60, "min_chars": 300,
        "render": True,   # 記事本文が Vue(JS)描画のためヘッドレスブラウザで取得
    },
    "gamewith": {
        "label": "GameWith",
        "indexes": ["https://pokemongo.gamewith.jp/"],
        "hubs": [],
        "link_re": r"^https://pokemongo\.gamewith\.jp/article/show/(\d+)$",
        "min_id": 565000, "max_articles": 80, "min_chars": 500,
    },
    "9db": {
        "label": "9DB",
        "indexes": ["https://9db.jp/pokemongo/"],
        "hubs": [],
        "link_re": r"^https://9db\.jp/pokemongo/data/(\d+)$",
        "min_id": 26100, "max_articles": 60, "min_chars": 150,
    },
    "official": {
        "label": "公式",
        "indexes": ["https://pokemongo.com/ja/news"],
        "hubs": [],
        "link_re": r"^https://pokemongo\.com/ja/news/([A-Za-z0-9\-_]+)/?$",
        "min_id": None, "max_articles": 20, "min_chars": 300,
    },
}
