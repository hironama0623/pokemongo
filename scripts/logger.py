"""取得ログ。1回の実行で logs/run-YYYYmmdd-HHMM.json と logs/latest.{json,md} を出力する。"""
import datetime as dt
import json
from . import config

# status 一覧: ok / http_error / fetch_error / suspect_empty / date_unknown(取得は成功) /
# action 一覧: analyzed / skipped_unchanged / skipped_out_of_window / skipped_budget / analyze_failed / validation_failed / fetch_only


class RunLog:
    def __init__(self, now):
        self.now = now
        self.entries = []
        self.notes = []

    def add(self, source, url, role, **kw):
        e = {"source": source, "url": url, "role": role,  # role: index / hub / article
             "status": None, "http_status": None, "article_updated": None, "date_kind": None,
             "chars_fetched": 0, "chars_sent": 0, "action": None, "reason": None, "error": None, "preview": None, "model": None, "ai_calls": None, "ai_seconds": None}
        e.update(kw)
        self.entries.append(e)
        return e

    def note(self, msg):
        self.notes.append(msg)
        print("NOTE:", msg)

    def summary(self):
        s = {"fetched_ok": 0, "fetch_failed": 0, "analyzed": 0, "skipped": 0, "failed": 0}
        for e in self.entries:
            if e["status"] in ("ok", "suspect_empty", "date_unknown"):
                s["fetched_ok"] += 1
            elif e["status"] in ("http_error", "fetch_error"):
                s["fetch_failed"] += 1
            a = e.get("action") or ""
            if a == "analyzed":
                s["analyzed"] += 1
            elif a.startswith("skipped"):
                s["skipped"] += 1
            elif a in ("analyze_failed", "validation_failed"):
                s["failed"] += 1
        return s

    def save(self, run_status):
        config.LOGS.mkdir(parents=True, exist_ok=True)
        stamp = self.now.strftime("%Y%m%d-%H%M")
        payload = {"run_at": self.now.isoformat(), "run_status": run_status,
                   "summary": self.summary(), "notes": self.notes, "entries": self.entries}
        txt = json.dumps(payload, ensure_ascii=False, indent=1)
        (config.LOGS / f"run-{stamp}.json").write_text(txt, encoding="utf-8")
        (config.LOGS / "latest.json").write_text(txt, encoding="utf-8")
        (config.LOGS / "latest.md").write_text(self._md(payload), encoding="utf-8")
        self._prune()

    def _md(self, p):
        s = p["summary"]
        lines = [f"# 取得ログ {p['run_at']}  ({p['run_status']})", "",
                 f"取得成功 {s['fetched_ok']} / 取得失敗 {s['fetch_failed']} / AI解析 {s['analyzed']} / スキップ {s['skipped']} / 解析失敗 {s['failed']}", ""]
        for n in p["notes"]:
            lines.append(f"- NOTE: {n}")
        lines += ["", "| サイト | 種別 | URL | 状態 | HTTP | 記事更新日 | 取得文字数 | AI送信文字数 | 処理 | 理由/エラー | 冒頭80字 | モデル | AI呼出回数 | AI秒 |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for e in p["entries"]:
            lines.append("| {source} | {role} | {url} | {status} | {http_status} | {article_updated} | {chars_fetched} | {chars_sent} | {action} | {why} | {pv} | {model} | {ai_calls} | {ai_seconds} |".format(pv=(e.get("preview") or "").replace("|", "/"), 
                why=(e.get("reason") or e.get("error") or ""), **{k: ("" if v is None else v) for k, v in e.items() if k not in ("reason", "error", "preview")}))
        return "\n".join(lines) + "\n"

    def _prune(self):
        limit = self.now - dt.timedelta(days=config.LOG_RETENTION_DAYS)
        for f in config.LOGS.glob("run-*.json"):
            try:
                t = dt.datetime.strptime(f.stem[4:], "%Y%m%d-%H%M").replace(tzinfo=config.JST)
                if t < limit:
                    f.unlink()
            except ValueError:
                pass
