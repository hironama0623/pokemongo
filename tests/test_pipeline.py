"""ネットワークとAIを差し替えた結合テスト。  実行: python -m unittest discover -s tests -v"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp())
os.environ["POGO_ROOT"] = str(TMP)
os.environ["REQUEST_INTERVAL"] = "0"
os.environ["AI_MIN_INTERVAL"] = "0"
sys.path.insert(0, str(ROOT))

from scripts import config, extract, run as runner  # noqa: E402
from scripts.logger import RunLog  # noqa: E402

NOW = dt.datetime(2026, 10, 30, 22, 0, tzinfo=config.JST)
FILLER = "".join(f"<p>これはテスト用の本文です。段落{i}。ポケモンGOのイベント情報が続きます。</p>" for i in range(30))


def page(updated, inner):
    return f"<html><head><title>t</title></head><body><nav>menu</nav><article>{FILLER}{inner}<p>更新日時: {updated}</p></article></body></html>"


def idx(*hrefs):
    return "<html><body>" + "".join(f'<a href="{h}">記事</a>' for h in hrefs) + "</body></html>"


FR_TABLE = ("<h2>フィールドリサーチ</h2><table><tr><th>タスク</th><th>報酬</th></tr>"
            "<tr><td>ゴーストタイプのポケモンを13匹捕まえる</td><td><img alt='ヨマワル'>ヨマワル</td></tr>"
            "<tr><td>ナイススローを6回投げる</td><td>ズバット(トップハット)</td></tr></table>")
PAGES = {
    "https://pokemongo.gamewith.jp/": idx("/article/show/579894", "/article/show/100", "/article/show/570000"),
    "https://pokemongo.gamewith.jp/article/show/579894": page("2026年10月29日 09:34", "<h2>サプライズボックス</h2><ul><li>ズバット(トップハット)</li><li>ピカチュウのアメ×6</li></ul>"),
    "https://pokemongo.gamewith.jp/article/show/570000": page("2026年08月01日 10:00", "<p>古い記事</p>"),
    "https://9db.jp/pokemongo/": idx("/pokemongo/data/26442", "/pokemongo/data/20859"),
    "https://9db.jp/pokemongo/data/26442": page("2026年10月30日 19:30", FR_TABLE),
    "https://pokemongo-get.com/pokego02416/": idx("/board/10772/&gsessionid=XYZ/", "/board/10765/"),
    "https://pokemongo-get.com/": idx("/board/10772/"),
    "https://pokemongo-get.com/board/10772/": "<html><body><article><p>[frlist id=\"37355\"]</p></article></body></html>",
    "https://pokemongo-get.com/board/10765/": page("2026年10月26日 10:00", "<p>今週のスケジュール</p>"),
    "https://pokemongo.com/ja/news": idx("/ja/news/halloween-part-1-2026"),
    "https://pokemongo.com/ja/news/halloween-part-1-2026": page("2026年10月26日 10:00", "<h2>野生</h2><ul><li>ヨマワル</li></ul>"),
}


def getter(url):
    return (PAGES[url], 200, None) if url in PAGES else (None, 404, "HTTP 404")


def mon(n, **k):
    return {"name": n, "dex": None, "shiny": True, **k}


def fake_llm_factory(calls):
    def llm(model, prompt):
        calls.append(prompt)
        url = prompt.split("URL=")[1].split()[0]
        base = {"relevant": True, "event_id": "ev-halloween-p1", "event_info": None, "wilds": [], "raids": [], "eggs": [],
                "surprise_box": None, "field_research": [], "time_challenge": []}
        if url.endswith("26442"):
            base["field_research"] = [{"task": "ゴーストタイプのポケモンを13匹捕まえる", "rewards": [{"name": "ヨマワル", "cp": "CP460"}]},
                                      {"task": "ナイススローを6回投げる", "rewards": [{"name": "ズバット(トップハット)"}]}]
        elif url.endswith("579894"):
            base["surprise_box"] = {"pokemon": [mon("ズバット(トップハット)")], "items": [{"name": "ピカチュウのアメ", "qty": "×6"}]}
        elif "halloween-part-1" in url:
            base["wilds"] = [mon("ヨマワル")]
        else:
            base["relevant"], base["event_id"] = False, ""
        return json.dumps(base, ensure_ascii=False)
    return llm


def reset():
    shutil.rmtree(TMP / "data", ignore_errors=True)
    shutil.rmtree(TMP / "logs", ignore_errors=True)
    shutil.copytree(ROOT / "data", TMP / "data")


def go(llm, g=getter, **kw):
    log = RunLog(NOW)
    status, _ = runner.run(NOW, log, getter=g, llm=llm, sleep=lambda s: None, render_getter=g, **kw)
    log.save(status)
    return status, log


def read(name):
    return json.loads((TMP / "data" / name).read_text("utf-8"))


def act(log, url_part):
    return next(e for e in log.entries if url_part in e["url"] and e["role"] != "index")


class T(unittest.TestCase):
    def setUp(self):
        reset()

    def test_full_run(self):
        calls = []
        status, log = go(fake_llm_factory(calls))
        self.assertIn(status, ("ok", "partial"))
        d = read("event_details.json")["events"]["ev-halloween-p1"]
        self.assertEqual(len(d["field_research"]), 2)
        self.assertEqual(d["field_research"][0]["rewards"][0]["dex"], 355)  # 辞書で図鑑番号補完（ヨマワルは355）
        self.assertEqual(d["field_research"][0]["sources"][0]["site"], "9db")
        self.assertEqual({p["name"] for p in d["surprise_box"]["pokemon"]}, {"ズバット(トップハット)"})
        self.assertEqual(d["wilds"][0]["sources"][0]["site"], "official")
        titles = " ".join(n["title"] for n in read("news.json")["items"])
        self.assertIn("フィールドリサーチ", titles)
        self.assertIn("サプライズボックス", titles)
        self.assertEqual(act(log, "570000")["action"], "skipped_out_of_window")
        pm = act(log, "board/10772")
        self.assertEqual(pm["action"], "skipped_empty")
        self.assertIn("frlist", pm["reason"])
        self.assertNotIn("gsessionid", pm["url"])
        self.assertTrue(all(e["chars_fetched"] > 0 for e in log.entries if e["status"] == "ok"))
        self.assertEqual(read("meta.json")["last_run_status"], status)
        legacy = json.loads((TMP / "data.json").read_text("utf-8"))  # 旧 index.html 向け互換
        self.assertEqual(len(legacy["field_research_updates"]["ev-halloween-p1"]), 2)
        self.assertTrue(legacy["latest_news"][0]["targetId"] == "ev-halloween-p1")
        self.assertTrue(legacy["updated_at"].endswith("JST"))
        self.assertTrue((TMP / "logs" / "latest.md").exists())

    def test_second_run_skips_unchanged_and_adds_update_news(self):
        go(fake_llm_factory([]))
        n1 = len(read("news.json")["items"])
        calls = []
        _, log = go(fake_llm_factory(calls))
        self.assertEqual(calls, [])  # AI呼び出しゼロ
        self.assertEqual(act(log, "26442")["action"], "skipped_unchanged")
        self.assertEqual(len(read("news.json")["items"]), n1)
        # 既発表イベントに新情報が増えたらニュースになる
        PAGES["https://9db.jp/pokemongo/data/26442"] = page("2026年10月31日 10:00", FR_TABLE + "<p>追加タスク</p>")
        llm = fake_llm_factory([])

        def llm2(m, p):
            f = json.loads(llm(m, p))
            if "26442" in p:
                f["field_research"].append({"task": "レイドバトルで1回勝つ", "rewards": [{"name": "ヤバチャ(リボン)"}]})
            return json.dumps(f, ensure_ascii=False)
        go(llm2)
        titles = [n["title"] for n in read("news.json")["items"]]
        self.assertTrue(any("フィールドリサーチ" in t and "（1件）" in t for t in titles), titles)

    def test_invalid_ai_output_keeps_previous_data(self):
        status, log = go(lambda m, p: '{"relevant": true}')  # event_id 欠落 → スキーマNG
        e = act(log, "26442")
        self.assertEqual(e["action"], "analyze_failed")
        self.assertEqual(read("event_details.json")["events"], {})
        self.assertNotIn("https://9db.jp/pokemongo/data/26442", read("state.json")["articles"])  # 次回リトライされる
        self.assertEqual(status, "partial")

    def test_all_fetch_failed_is_failed_and_untouched(self):
        before = (TMP / "data" / "news.json").read_text("utf-8")
        status, log = go(fake_llm_factory([]), g=lambda u: (None, 403, "HTTP 403"))
        self.assertEqual(status, "failed")
        self.assertEqual((TMP / "data" / "news.json").read_text("utf-8"), before)

    def test_diagnose_mode_writes_no_data(self):
        status, log = go(None, diagnose=True)
        self.assertEqual(status, "ok")
        self.assertEqual(read("event_details.json")["events"], {})
        self.assertTrue(any(e["action"] == "fetch_only" for e in log.entries))

    def test_identical_bodies_are_skipped_as_boilerplate(self):
        same = page("2026年10月30日 10:00", "<p>共通テンプレだけ</p>")
        for i in (1, 2, 3):
            PAGES[f"https://9db.jp/pokemongo/data/2650{i}"] = same
        PAGES["https://9db.jp/pokemongo/"] = idx("/pokemongo/data/26501", "/pokemongo/data/26502", "/pokemongo/data/26503")
        try:
            calls = []
            _, log = go(fake_llm_factory(calls))
            e = act(log, "26501")
            self.assertEqual(e["action"], "skipped_empty")
            self.assertIn("同一本文", e["reason"])
            self.assertFalse(any("26501" in c for c in calls))
        finally:
            PAGES["https://9db.jp/pokemongo/"] = idx("/pokemongo/data/26442", "/pokemongo/data/20859")

    def test_div_br_body_is_recovered(self):
        body = "<div>" + "<br>".join(f"行{i}：[frlist id=\"1\"] ゴーストタイプを{i}匹捕まえる ヨマワル" for i in range(40)) + "</div>"
        text, _, _ = extract.html_to_text(f"<html><body><article><h1>見出し</h1>{body}</article></body></html>")
        self.assertGreater(len(text), 500)
        self.assertIn("ヨマワル", text)

    def test_hash_ignores_timestamps(self):
        a = extract.content_hash("本文\n更新日時: 2026年10月29日 09:34")
        b = extract.content_hash("本文\n更新日時: 2026年10月30日 21:33")
        self.assertEqual(a, b)


try:
    import playwright  # noqa: F401
    HAS_PW = True
except ImportError:
    HAS_PW = False


@unittest.skipUnless(HAS_PW, "playwright 未インストール")
class RenderTest(unittest.TestCase):
    def test_vue_like_page_is_rendered(self):
        import http.server, threading
        from scripts import fetch
        html = ("<html><head><title>T</title></head><body><div id='the-content'><div id='app' style='display:none'></div></div>"
                "<script>setTimeout(function(){var a=document.getElementById('app');a.innerHTML="
                "'<table><tr><td>ゴーストを13匹捕まえる</td><td>ヨマワル</td></tr></table>';a.style.display='block';},300);</script></body></html>")

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_port}/"
            raw = fetch.get_rendered(url)
            self.assertIsNone(raw[2], raw[2])
            text, _, _ = extract.html_to_text(raw[0])
            self.assertIn("ヨマワル", text)
            self.assertIn("ゴーストを13匹捕まえる | ヨマワル", text)
        finally:
            srv.shutdown(); fetch.close_renderer()

    def test_launch_failure_is_reported_once_and_fast(self):
        from scripts import fetch
        fetch.close_renderer()
        old = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(TMP / "no-browsers")  # ブラウザ未インストールを再現
        try:
            a = fetch.get_rendered("http://127.0.0.1:1/")
            b = fetch.get_rendered("http://127.0.0.1:1/")
            self.assertIn("Chromiumを起動できません", a[2])
            self.assertEqual(a[2], b[2])  # asyncio ループのエラーに化けない・2回目も同じ即時失敗
            self.assertNotIn("asyncio", b[2])
        finally:
            if old is None:
                os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
            else:
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = old
            fetch.close_renderer()


class AnalyzeRobust(unittest.TestCase):
    ART = {"site": "9db", "url": "https://x", "text": "本文", "updated": None}

    def test_retry_on_429_then_ok(self):
        from scripts import analyze as an
        n = {"c": 0}

        def llm(m, p):
            n["c"] += 1
            if n["c"] < 3:
                raise RuntimeError("429 RESOURCE_EXHAUSTED retryDelay: 5s")
            return json.dumps({"relevant": False, "event_id": ""})
        waits = []
        r = an.analyze(self.ART, [], ["m1"], call=llm, sleep=waits.append)
        self.assertFalse(r["relevant"])
        self.assertEqual(len(waits), 2)

    def test_string_pokemon_normalized(self):
        from scripts import analyze as an
        out = json.dumps({"relevant": True, "event_id": "", "surprise_box": {"pokemon": ["リボンをつけた ヤバチャ"]}})
        r = an.analyze(self.ART, [], ["m1"], call=lambda m, p: out, sleep=lambda s: None)
        self.assertEqual(r["surprise_box"]["pokemon"][0]["name"], "リボンをつけた ヤバチャ")


class Quota(unittest.TestCase):
    def test_daily_quota_stops_run_but_saves(self):
        calls = []

        def llm(m, p):
            calls.append(1)
            raise RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        from scripts import analyze as an
        an._dead.clear()
        log = RunLog(NOW)
        status, saved = runner.run(NOW, log, getter=getter, llm=llm, sleep=lambda s: None, render_getter=getter)
        an._dead.clear()
        self.assertEqual(len(calls), len(config.GEMINI_MODELS))  # 各モデル1回ずつ試して全滅したら打ち切り
        self.assertTrue(saved)
        self.assertEqual(status, "partial")


class QuotaPerModel(unittest.TestCase):
    def test_exhausted_model_skipped_next_model_used(self):
        from scripts import analyze as an
        an._dead.clear()
        used = []

        def llm(m, p):
            used.append(m)
            if m == "m1":
                raise RuntimeError("429 RESOURCE_EXHAUSTED PerDay")
            return json.dumps({"relevant": False, "event_id": ""})
        art = {"site": "9db", "url": "https://x", "text": "本文", "updated": None}
        an.analyze(art, [], ["m1", "m2"], call=llm, sleep=lambda s: None)
        an.analyze(art, [], ["m1", "m2"], call=llm, sleep=lambda s: None)
        an._dead.clear()
        self.assertEqual(used, ["m1", "m2", "m2"])  # 2回目以降は m1 を試さない


class Pokedex(unittest.TestCase):
    def test_contained_species(self):
        from scripts import pokedex
        table = {"ヤバチャ": 1, "ヒトモシ": 2, "ヤミラミ": 3, "ゴース": 4, "ゴースト": 5, "ピカチュウ": 6}
        un = set()
        m1 = pokedex.fill_dex({"name": "リボンをつけた ヤバチャ", "dex": None}, table, un)
        m2 = pokedex.fill_dex({"name": "ヒトモシ / ヤミラミ", "dex": None}, table, un)
        m3 = pokedex.fill_dex({"name": "ゴースト", "dex": None}, table, un)
        m4 = pokedex.fill_dex({"name": "ハットとケープをつけたピカチュウ", "dex": None}, table, un)
        self.assertEqual((m1["dex"], m2["dex"], m3["dex"], m4["dex"]), (1, None, 5, 6))
        self.assertIn("ヒトモシ / ヤミラミ", un)


class Budget(unittest.TestCase):
    def setUp(self):
        from scripts import analyze as an
        an._dead.clear()

    def test_budget_exceeded_skips_but_saves(self):
        old = config.ANALYZE_BUDGET_SEC
        config.ANALYZE_BUDGET_SEC = -1
        try:
            log = RunLog(NOW)
            status, saved = runner.run(NOW, log, getter=getter, llm=lambda m, p: "{}", sleep=lambda s: None, render_getter=getter)
        finally:
            config.ANALYZE_BUDGET_SEC = old
        self.assertEqual(status, "partial")
        self.assertTrue(saved)
        self.assertTrue(any(e["action"] == "skipped_budget" for e in log.entries))


class MergeNewEvent(unittest.TestCase):
    def test_new_event_with_dates_does_not_keyerror(self):
        from scripts import merge
        details, events = {"events": {}}, {}
        facts = {"event_id": "NEW:ghastly-spotlight-hour-20261029",
                 "event_info": {"title": "ゴースのスポットライトアワー", "category": "spotlight", "start": "2026-10-29T18:00", "end": "2026-10-29T19:00"},
                 "wilds": [{"name": "ゴース", "dex": None, "shiny": None}]}
        src = {"site": "pokemapi", "url": "https://x/board/1/", "fetched_at": NOW.isoformat(), "article_updated": None}
        ch, warns = merge.merge_article(details, events, facts, src, [], NOW)
        self.assertIn("ev-auto-ghastly-spotlight-hour-20261029", events)
        self.assertTrue(any(c["kind"] == "new_event" for c in ch))


if __name__ == "__main__":
    unittest.main()
