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


# --- JS描画が必要なサイト（ポケマピの記事本文は Vue が後から描画する）用 -----------------
_pw = _browser = None
_sel_timeouts = 0


def get_rendered(url):
    """ヘッドレスChromiumで描画後のHTMLを返す。(html|None, http_status|None, error|None)"""
    global _pw, _browser, _sel_timeouts
    try:
        if _browser is None:
            from playwright.sync_api import sync_playwright  # 遅延import（通常サイトでは不要）
            _pw = sync_playwright().start()
            _browser = _pw.chromium.launch()
        ctx = _browser.new_context(user_agent=config.UA, locale="ja-JP")
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("image", "media", "font") else r.continue_())
        page = ctx.new_page()
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = resp.status if resp else None
            try:  # Vue が #app を表示するまで待つ。3回連続で出なければ待ち時間を短縮（全件が遅くならないように）
                page.wait_for_selector("#app", state="visible", timeout=1500 if _sel_timeouts >= 3 else 12000)
                _sel_timeouts = 0
            except Exception:  # noqa: BLE001
                _sel_timeouts += 1
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:  # noqa: BLE001
                pass
            html = page.content()
        finally:
            ctx.close()
        if status and status != 200:
            return None, status, f"HTTP {status}"
        return html, status, None
    except Exception as e:  # noqa: BLE001
        return None, None, f"{type(e).__name__}: {str(e)[:150]}"


def close_renderer():
    global _pw, _browser
    try:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:  # noqa: BLE001
        pass
    _pw = _browser = None
