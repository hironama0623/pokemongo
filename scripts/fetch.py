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
_launch_error = None


def get_rendered(url):
    """ヘッドレスChromiumで描画後のHTMLを返す。(html|None, http_status|None, error|None)"""
    global _pw, _browser, _sel_timeouts, _launch_error
    if _launch_error:  # 起動に失敗済みなら、全ページで同じ失敗を繰り返さず即座に返す
        return None, None, _launch_error
    try:
        if _browser is None:
            from playwright.sync_api import sync_playwright  # 遅延import（通常サイトでは不要）
            _pw = sync_playwright().start()
            try:
                _browser = _pw.chromium.launch()
            except Exception as e:  # noqa: BLE001  起動失敗: 後始末して以後は即失敗
                _pw.stop()
                _pw = None
                _launch_error = ("Chromiumを起動できません。ワークフローの『ブラウザ(Chromium)の準備』"
                                 f"ステップ（playwright install --with-deps chromium）を確認してください: {str(e)[:120]}")
                return None, None, _launch_error
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
    global _pw, _browser, _launch_error
    _launch_error = None
    try:
        if _browser:
            _browser.close()
        if _pw:
            _pw.stop()
    except Exception:  # noqa: BLE001
        pass
    _pw = _browser = None


_MARK_JS = """() => {
  // 「未実装」の文字を持つ要素から上にたどり、兄弟が3つ以上ある階層を探す。その末尾3つが 左=シャドウ / 中=メガ / 右=未実装(通常)
  const leaf = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.textContent.trim() === '未実装');
  let info = 'no-unimpl';
  if (leaf) {
    let el = leaf;
    while (el.parentElement && el.parentElement.children.length < 3 && el.parentElement !== document.body) el = el.parentElement;
    const sib = el.parentElement ? [...el.parentElement.children] : [];
    const last3 = sib.slice(-3);
    last3.forEach((ch, i) => ch.setAttribute('data-probe-state', String(i)));
    info = last3.length + '/' + sib.length;
    window.__probeSection = el.parentElement ? el.parentElement.parentElement.outerHTML.slice(0, 3000) : '';
  }
  const btn = [...document.querySelectorAll('button, input[type=button], input[type=submit], a, div, span')].find(e => e.children.length === 0 && (e.textContent || e.value || '').trim() === '検索');
  if (btn) btn.setAttribute('data-probe-search', '1');
  return info + '/' + (btn ? 'search' : 'no-search');
}"""


def _safe_click(page, selector):
    """普通のクリック → だめなら（広告などが上に重なっている場合）スクロールして強制クリック → 最後にJSで直接クリック。"""
    loc = page.locator(selector).first
    try:
        loc.click(timeout=2500)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        loc.scroll_into_view_if_needed(timeout=2000)
        loc.click(timeout=2500, force=True)
        return
    except Exception:  # noqa: BLE001
        pass
    loc.evaluate("el => el.click()", timeout=3000)


def render_states(url, states=("normal", "shadow", "mega")):
    """9DBの対策検索ツール用。ページを描画し、「状態」の3つのボタン（左=シャドウ / 中=メガ / 右=未実装=通常）を順に押して「検索」を押し、
    状態ごとの描画後HTMLを返す。{state: html|None}, error|None。ボタンが見つからない場合は、押さずに最初の表だけ返す。"""
    global _pw, _browser, _launch_error
    out = {}
    if _launch_error:
        return out, _launch_error
    try:
        if _browser is None:
            from playwright.sync_api import sync_playwright
            _pw = sync_playwright().start()
            try:
                _browser = _pw.chromium.launch()
            except Exception as e:  # noqa: BLE001
                _pw.stop(); _pw = None
                _launch_error = f"Chromiumを起動できません: {str(e)[:120]}"
                return out, _launch_error
        ctx = _browser.new_context(user_agent=config.UA, locale="ja-JP")
        ctx.route("**/*", lambda r: r.abort() if r.request.resource_type in ("media", "font") else r.continue_())   # 画像は止めない（名前の手がかりが画像のため）
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:  # noqa: BLE001
                pass
            mark = page.evaluate(_MARK_JS)
            out["_mark"] = mark
            try:
                out["_section"] = page.evaluate("() => window.__probeSection || ''")
            except Exception:  # noqa: BLE001
                out["_section"] = ""
            idx = {"shadow": 0, "mega": 1, "normal": 2}
            for n_st, st in enumerate(states):
                try:
                    if n_st > 0:   # 状態ボタンは押すと選択が重なるので、ページを読み込み直して、その状態のボタンだけを押す
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=8000)
                        except Exception:  # noqa: BLE001
                            pass
                        page.evaluate(_MARK_JS)
                    _safe_click(page, f'[data-probe-state="{idx[st]}"]')
                    _safe_click(page, '[data-probe-search="1"]')
                    page.wait_for_timeout(2500)
                    try:
                        page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:  # noqa: BLE001
                        pass
                except Exception as e:  # noqa: BLE001
                    out[st] = None
                    out[f"_err_{st}"] = f"{type(e).__name__}: {str(e)[:100]}"
                    continue
                out[st] = page.content()
        finally:
            ctx.close()
        return out, None
    except Exception as e:  # noqa: BLE001
        return out, f"{type(e).__name__}: {str(e)[:150]}"
