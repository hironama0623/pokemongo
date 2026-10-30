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
    status, _ = runner.run(NOW, log, getter=g, llm=llm, sleep=lambda s: None, **kw)
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
        self.assertEqual(d["field_research"][0]["rewards"][0]["dex"], 353)  # 辞書で図鑑番号補完
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


if __name__ == "__main__":
    unittest.main()
