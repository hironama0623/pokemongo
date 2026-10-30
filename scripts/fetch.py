"""ネットワーク取得と記事候補の発見。HTTP取得は get() に集約（テストでは差し替える）。"""
import time

import requests

from . import config
from .extract import extract_links

_session = requests.Session()
_session.headers.update({"User-Agent": config.UA, "Accept-Language": "ja,en;q=0.8"})


def get(url):
    """(html|None, http_status|None, error|None)。リトライ付き。失敗しても例外は投げない。"""
    err, status = None, None
    for i in range(config.RETRIES + 1):
        try:
            r = _session.get(url, timeout=config.TIMEOUT)
            status = r.status_code
            if r.status_code == 200:
                if not r.encoding or r.encoding.lower() == "iso-8859-1":
                    r.encoding = r.apparent_encoding or "utf-8"
                return r.text, status, None
            err = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        time.sleep(1.5 * (i + 1))
    return None, status, err


def discover(source_key, cfg, log, getter=get):
    """一覧ページから記事候補 [(key, url, title)] を新しい順に返す。取得失敗はログに残す。"""
    found, seen = [], set()
    for url in cfg["indexes"]:
        html, status, err = getter(url)
        e = log.add(source_key, url, "index", http_status=status)
        if html is None:
            e.update(status="http_error" if status else "fetch_error", error=err, action="index_failed")
            continue
        links = extract_links(html, url, cfg["link_re"])
        e.update(status="ok", chars_fetched=len(html), reason=f"記事リンク {len(links)} 件")
        if not links:
            log.note(f"{source_key}: {url} から記事リンクを1件も抽出できませんでした（URL構造の変更またはJS描画の疑い）")
        for key, u, title in links:
            if u not in seen:
                seen.add(u)
                found.append((key, u, title))
        time.sleep(config.REQUEST_INTERVAL)
    min_id = cfg.get("min_id")
    if min_id is not None:
        found = [f for f in found if f[0].isdigit() and int(f[0]) >= min_id]
        found.sort(key=lambda f: int(f[0]), reverse=True)
    return found
