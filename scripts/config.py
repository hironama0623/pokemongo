"""設定。取得先・期間・上限はここだけで管理する（SPEC.md 5章）。"""
import datetime as dt
import os
from pathlib import Path

JST = dt.timezone(dt.timedelta(hours=9))
ROOT = Path(os.environ.get("POGO_ROOT", Path(__file__).resolve().parent.parent))
DATA = ROOT / "data"
LOGS = ROOT / "logs"

WINDOW_DAYS = 31            # 直近この日数以内に更新された記事だけ解析対象
MAX_ARTICLES_PER_SOURCE = int(os.environ.get("MAX_ARTICLES_PER_SOURCE", "40"))
REQUEST_INTERVAL = float(os.environ.get("REQUEST_INTERVAL", "1.0"))  # 秒
TIMEOUT = 20
RETRIES = 2
MIN_BODY_CHARS = 500        # これ未満は「本文が取れていない疑い」とログに残す
MAX_AI_CHARS = 60000        # AIに渡す上限。切り詰めた場合は chars_sent に反映される
NEWS_RETENTION_DAYS = 45
LOG_RETENTION_DAYS = 30

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

GEMINI_MODELS = [os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), "gemini-2.5-pro"]

# link_re: 記事URLの正規表現（group(1)=記事キー）。min_id: これ未満の数値IDは古い記事として無視。
# 数値IDでないサイト（公式）は一覧の並び順（新しい順）で上位 MAX_ARTICLES_PER_SOURCE 件を見る。
SOURCES = {
    "pokemapi": {
        "label": "ポケマピ",
        "indexes": ["https://pokemongo-get.com/pokego02416/", "https://pokemongo-get.com/"],
        "hubs": ["https://pokemongo-get.com/research_fi/"],
        "link_re": r"^https://pokemongo-get\.com/board/(\d+)/?$",
        "min_id": 10450,
    },
    "gamewith": {
        "label": "GameWith",
        "indexes": ["https://pokemongo.gamewith.jp/"],
        "hubs": [],
        "link_re": r"^https://pokemongo\.gamewith\.jp/article/show/(\d+)$",
        "min_id": 565000,
    },
    "9db": {
        "label": "9DB",
        "indexes": ["https://9db.jp/pokemongo/"],
        "hubs": [],
        "link_re": r"^https://9db\.jp/pokemongo/data/(\d+)$",
        "min_id": 26100,
    },
    "official": {
        "label": "公式",
        "indexes": ["https://pokemongo.com/ja/news"],
        "hubs": [],
        "link_re": r"^https://pokemongo\.com/ja/news/([A-Za-z0-9\-_]+)/?$",
        "min_id": None,
    },
}
