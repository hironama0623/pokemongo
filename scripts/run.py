"""オーケストレーター: 発見 → 取得 → 期間/差分判定 → AI解析 → 検証 → 統合 → 保存。

使い方:
  python -m scripts.run              通常実行
  python -m scripts.run --diagnose   取得とログだけ（AI解析・data書き込みなし）。サイトが取れているかの確認用
  python -m scripts.run --no-news    ニュースを作らない（初回の取り込み用）
終了コード: 0=ok/partial, 1=failed（1ページも取得できない / 保存前検証NG / APIキー無し）。失敗時も data/ は前回のまま。
"""
import copy
import shutil
import datetime as dt
import json
import os
import sys
import time

from . import analyze as an
from . import compat, config, extract, fetch, merge, pokedex, schemas, store
from .logger import RunLog


def _fetch_page(source, url, role, log, getter, min_chars, dump=None):
    e = log.add(source, url, role)
    html, status, err = getter(url)
    e["http_status"] = status
    if html is None:
        e.update(status="http_error" if status else "fetch_error", error=err, action="fetch_failed")
        return e, None
    text, soup, raw = extract.html_to_text(html)
    date, kind = extract.extract_date(soup, raw)
    e.update(chars_fetched=len(text), article_updated=date.isoformat() if date else None, date_kind=kind, status="ok")
    if "[frlist" in raw or "[eventimage" in raw:
        e["reason"] = "未展開ショートコード(frlist等)あり: 表が本文HTMLに無い可能性"
    e["preview"] = text[:80].replace("\n", " ")
    dkey = source if role == "article" else f"{source}-{role}"
    if dump is not None and dump.get(dkey, 0) < 2:  # 診断モードのみ: 原因調査用に生HTMLを各サイト2件まで保存
        dump[dkey] = dump.get(dkey, 0) + 1
        config.LOGS.joinpath("debug").mkdir(parents=True, exist_ok=True)
        (config.LOGS / "debug" / f"{dkey}-{url.rstrip('/').split('/')[-1]}.html").write_text(html[:400000], encoding="utf-8")
    if len(text) < min_chars:
        e["status"] = "suspect_empty"
    elif date is None:
        e["status"] = "date_unknown"
    return e, {"site": source, "url": url, "text": text, "updated": e["article_updated"], "date": date, "hash": extract.content_hash(text)}


def run(now, log, diagnose=False, no_news=False, getter=fetch.get, llm=an.gemini_call, sleep=time.sleep):
    cutoff = now - dt.timedelta(days=config.WINDOW_DAYS)
    state = store.load("state.json", {"articles": {}})
    details = store.load("event_details.json", {"schema_version": 1, "events": {}})
    events = store.load("events.json", {"schema_version": 1, "events": {}})
    news = store.load("news.json", {"schema_version": 1, "items": []})
    meta = store.load("meta.json", {"schema_version": 1})
    index = store.load("event_index.json", {"events": []})["events"]
    names = store.load("pokemon.json", {"names": {}})["names"]

    queue, dump = [], ({} if diagnose else None)
    shutil.rmtree(config.LOGS / "debug", ignore_errors=True)
    for key, cfg in config.SOURCES.items():
        cands = fetch.discover(key, cfg, log, getter)
        pages = [(u, "hub") for u in cfg["hubs"]] + [(u, "article") for _, u, _ in cands[:cfg["max_articles"]]]
        limit = cfg["max_articles"]
        if len(cands) > limit:
            log.note(f"{key}: 候補{len(cands)}件のうち上限{limit}件のみ取得（超過分は古い順）")
        for url, role in pages:
            sleep(config.REQUEST_INTERVAL)
            e, art = _fetch_page(key, url, role, log, getter, cfg["min_chars"], dump)
            if art is None:
                continue
            if role == "article" and art["date"] and art["date"] < cutoff:
                e.update(action="skipped_out_of_window", reason=f"記事更新日が{config.WINDOW_DAYS}日より前")
            elif e["status"] == "suspect_empty":
                e.update(action="skipped_empty", reason=(e.get("reason") or "") + " 本文が短すぎるためAI解析せず（JS描画/ブロックの疑い）")
            elif state["articles"].get(url, {}).get("hash") == art["hash"]:
                e.update(action="skipped_unchanged", reason="本文ハッシュが前回と同じ")
            else:
                art["entry"] = e
                queue.append(art)

        # 同じ本文が3ページ以上ある＝記事固有の中身が取れておらず共通テンプレだけ取れている。AI解析しない
        cnt = {}
        for a in queue:
            if a["site"] == key:
                cnt[a["hash"]] = cnt.get(a["hash"], 0) + 1
        for a in [a for a in queue if a["site"] == key and cnt[a["hash"]] >= 3]:
            a["entry"].update(status="suspect_empty", action="skipped_empty",
                              reason=f"同一本文が{cnt[a['hash']]}ページで一致（記事固有の本文が取れていない/共通部分のみ）")
            queue.remove(a)

    ok = sum(1 for e in log.entries if e["role"] != "index" and e["status"] in ("ok", "date_unknown", "suspect_empty"))
    if diagnose:
        for a in queue:
            a["entry"].update(action="fetch_only", reason="診断モード: AI解析なし")
        return "ok" if ok else "failed", False
    if ok == 0:
        log.note("記事・ハブページを1件も取得できませんでした。data/ は更新しません。")
        return "failed", False
    if queue and llm is an.gemini_call and not os.environ.get("GEMINI_API_KEY"):
        log.note("GEMINI_API_KEY が未設定のためAI解析できません。")
        return "failed", False

    changes, unresolved, analyzed_ok, problems = [], set(), [], 0
    queue.sort(key=lambda a: a["date"] or now, reverse=True)
    for art in queue:
        e = art["entry"]
        art["text"] = art["text"][:config.MAX_AI_CHARS]
        e["chars_sent"] = len(art["text"])
        known = index + [dict(v) for v in events["events"].values()]
        try:
            facts = an.analyze(art, known, config.GEMINI_MODELS, call=llm)
        except an.AnalyzeError as ex:
            e.update(action="analyze_failed", error=str(ex)[:400])
            problems += 1
            continue
        if not facts["relevant"]:
            e.update(action="analyzed", reason="対象外の記事（イベント情報なし）")
            analyzed_ok.append(art)
            continue
        for sec in ("wilds", "raids", "eggs"):
            for m in facts.get(sec, []):
                pokedex.fill_dex(m, names, unresolved)
        for m in (facts.get("surprise_box") or {}).get("pokemon", []):
            pokedex.fill_dex(m, names, unresolved)
        for t in facts.get("field_research", []) + facts.get("time_challenge", []):
            for r in t["rewards"]:
                pokedex.fill_dex(r, names, unresolved)
        trial_d, trial_e = copy.deepcopy(details), copy.deepcopy(events["events"])
        src = {"site": art["site"], "url": art["url"], "fetched_at": now.isoformat(), "article_updated": art["updated"]}
        ch, warns = merge.merge_article(trial_d, trial_e, facts, src, index, now)
        err = schemas.validate("details", trial_d) or schemas.validate("events", {"schema_version": 1, "events": trial_e})
        if err:
            e.update(action="validation_failed", error=err)
            problems += 1
            continue
        details, events["events"] = trial_d, trial_e
        changes += ch
        analyzed_ok.append(art)
        e.update(action="analyzed", reason="; ".join(warns + [f"{c['section']}+{len(c['added'])}" for c in ch]) or "新情報なし")

    titles = {x["id"]: x["title"] for x in index}
    titles.update({k: v["title"] for k, v in events["events"].items()})
    new_items = [] if no_news else merge.changes_to_news(changes, titles, now)
    news["items"] = merge.merge_news(news["items"], new_items, now)
    for a in analyzed_ok:
        state["articles"][a["url"]] = {"hash": a["hash"], "analyzed_at": now.isoformat(), "article_updated": a["updated"]}

    bad = ("http_error", "fetch_error", "suspect_empty")
    status = "ok" if problems == 0 and not any(e["status"] in bad for e in log.entries) else "partial"
    meta.update({"schema_version": 1, "last_run_at": now.isoformat(), "last_run_status": status, "last_success_at": now.isoformat(),
                 "counts": {**log.summary(), "events_auto": len(events["events"]), "news": len(news["items"])}})
    if changes:
        meta["last_content_change_at"] = now.isoformat()
    for kind, obj in (("details", details), ("events", events), ("news", news), ("meta", meta)):
        err = schemas.validate(kind, obj)
        if err:
            log.note(f"保存前検証NG: {err}。data/ は更新しません。")
            return "failed", False
    for name, obj in (("event_details.json", details), ("events.json", events), ("news.json", news), ("state.json", state), ("meta.json", meta)):
        store.save(name, obj)
    try:  # 旧 index.html 向け互換出力（第2段階で削除）。失敗しても本処理は成功扱い、ただしログに残す
        (config.ROOT / "data.json").write_text(json.dumps(compat.build_legacy(details, events, news, meta, index), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as ex:  # noqa: BLE001
        log.note(f"data.json(互換)の出力に失敗: {ex}")
    if unresolved:
        p = config.LOGS / "unresolved_names.json"
        old = json.loads(p.read_text("utf-8")) if p.exists() else []
        config.LOGS.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sorted(set(old) | unresolved), ensure_ascii=False, indent=1), encoding="utf-8")
        log.note(f"図鑑番号を解決できなかった名前: {sorted(unresolved)} → data/pokemon.json に追記してください")
    return status, True


def mark_failed(now, status_note):
    """失敗した事実を meta に残す（last_success_at は据え置き。成功と区別できるようにする）。"""
    meta = store.load("meta.json", {"schema_version": 1})
    meta.update({"schema_version": 1, "last_run_at": now.isoformat(), "last_run_status": "failed"})
    if schemas.validate("meta", meta) is None:
        store.save("meta.json", meta)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    now = dt.datetime.now(config.JST)
    log = RunLog(now)
    try:
        status, _ = run(now, log, diagnose="--diagnose" in argv, no_news="--no-news" in argv)
    except Exception as ex:  # noqa: BLE001  握りつぶさず、ログに残して失敗終了
        log.note(f"想定外のエラー: {type(ex).__name__}: {ex}")
        status = "failed"
    if status == "failed" and "--diagnose" not in argv:
        mark_failed(now, "")
    log.save(status)
    print(f"[{now:%Y/%m/%d %H:%M JST}] status={status} {log.summary()}")
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
