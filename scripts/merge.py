"""AIが返した1記事分の事実を data に統合し、「何が増えたか」を機械的に検出する（ニュース生成の根拠）。
ニュース用の差分判定はAIに任せず、ここで決定的に行う。"""
import datetime as dt
import hashlib
import re

from . import config

LABEL = {"wilds": "野生", "raids": "レイド", "eggs": "タマゴ", "surprise_box": "サプライズボックス",
         "field_research": "フィールドリサーチ", "time_challenge": "タイムチャレンジ"}


def _k(s):
    return re.sub(r"[\s　・、。,()（）\[\]【】「」『』!！?？~〜-]", "", s or "").lower()


def _src_add(item, src):
    for s in item["sources"]:
        if s["site"] == src["site"] and s["url"] == src["url"]:
            s.update({k: v for k, v in src.items() if v})
            return False
    item["sources"].append(dict(src))
    return True


def _merge_items(existing, incoming, keyfn, src, label):
    added = []
    idx = {keyfn(x): x for x in existing}
    for it in incoming:
        k = keyfn(it)
        if k in idx:
            cur = idx[k]
            _src_add(cur, src)
            if "rewards" in it:
                have = {_k(r["name"]) for r in cur["rewards"]}
                for r in it["rewards"]:
                    if _k(r["name"]) not in have:
                        cur["rewards"].append(r)
                        added.append(f"{it['task']}→{r['name']}")
            else:
                for f in ("dex", "shiny", "note"):
                    if cur.get(f) in (None, "") and it.get(f) not in (None, ""):
                        cur[f] = it[f]
        else:
            new = dict(it, sources=[dict(src)])
            existing.append(new)
            idx[k] = new
            added.append(label(it))
    return added


def _task_label(t):
    return f"{t['task']}→" + "・".join(r["name"] for r in t["rewards"])


def merge_article(details, events, facts, src, index, now):
    """details/events を直接更新し、changes=[{event_id, section, added:[..], kind, src}] と警告を返す。"""
    changes, warns = [], []
    eid = (facts.get("event_id") or "").strip()
    known = {e["id"]: e for e in index}
    known.update({k: v for k, v in events.items()})
    info = facts.get("event_info") or {}
    if eid.startswith("NEW:"):
        title = info.get("title")
        same = next((k for k, v in known.items() if title and _k(v["title"]) == _k(title)), None)
        if same:
            eid = same
        elif not (title and info.get("start") and info.get("end") and info.get("category")):
            warns.append(f"NEW イベント '{eid}' は title/category/start/end が揃わないため保存しません")
            return changes, warns
        else:
            slug = re.sub(r"[^a-z0-9\-]", "", eid[4:].lower().replace("_", "-")) or hashlib.sha1(title.encode()).hexdigest()[:8]
            eid = f"ev-auto-{slug}"
            events[eid] = {"id": eid, "title": title, "category": info["category"], "start": info["start"], "end": info["end"],
                           "dateText": info.get("dateText"), "summary": info.get("summary"), "hasPaid": info.get("hasPaid"),
                           "freeFeatures": info.get("freeFeatures", []), "paidFeatures": info.get("paidFeatures", []),
                           "created_at": now.isoformat(), "sources": [dict(src)]}
            known[eid] = events[eid]  # 以降の日程比較などで参照するため（KeyError防止）
            changes.append({"event_id": eid, "section": "new_event", "added": [title], "kind": "new_event", "src": src})
    elif eid in known and eid in events:
        _src_add(events[eid], src)
    if not eid or eid not in known and eid not in events:
        if eid:
            warns.append(f"未知のイベントID '{eid}' を無視しました")
        return changes, warns

    d = details["events"].setdefault(eid, {})
    # 日程変更（既知イベントの開始/終了が記事と食い違う場合）
    base = known[eid]
    if info.get("start") and info.get("end") and (info["start"][:10] != base["start"][:10] or info["end"][:10] != base["end"][:10]):
        sch = d.get("schedule")
        if not sch or (sch["start"], sch["end"]) != (info["start"], info["end"]):
            d["schedule"] = {"start": info["start"], "end": info["end"], "sources": [dict(src)]}
            changes.append({"event_id": eid, "section": "schedule", "kind": "schedule_changed", "src": src,
                            "added": [f"{base['start'][:10]}〜{base['end'][:10]} → {info['start'][:10]}〜{info['end'][:10]}"]})
        else:
            _src_add(sch, src)

    def run(section, items, keyfn, label):
        if not items:
            return
        added = _merge_items(d.setdefault(section, []), items, keyfn, src, label)
        if added:
            changes.append({"event_id": eid, "section": section, "added": added, "kind": "event_update", "src": src})

    run("wilds", facts.get("wilds", []), lambda x: _k(x["name"]), lambda x: x["name"])
    run("raids", facts.get("raids", []), lambda x: _k(x["name"]) + _k(x.get("tier") or ""), lambda x: x["name"])
    run("eggs", facts.get("eggs", []), lambda x: _k(x["name"]) + _k(x.get("distance") or ""),
        lambda x: f"{x['name']}({x['distance']})" if x.get("distance") else x["name"])
    run("field_research", facts.get("field_research", []), lambda x: _k(x["task"]), _task_label)
    run("time_challenge", facts.get("time_challenge", []), lambda x: _k(x["task"]), _task_label)
    sb = facts.get("surprise_box") or {}
    if sb.get("pokemon") or sb.get("items"):
        box = d.setdefault("surprise_box", {})
        added = _merge_items(box.setdefault("pokemon", []), sb.get("pokemon", []), lambda x: _k(x["name"]), src, lambda x: x["name"])
        added += _merge_items(box.setdefault("items", []), sb.get("items", []), lambda x: _k(x["name"]), src,
                              lambda x: x["name"] + (f"×{x['qty']}" if x.get("qty") else ""))
        if added:
            changes.append({"event_id": eid, "section": "surprise_box", "added": added, "kind": "event_update", "src": src})
    if changes:
        d["updated_at"] = now.isoformat()
    return changes, warns


def changes_to_news(changes, titles, now):
    """changes → ニュース項目。同一イベント・同一内容は同じIDになり重複しない。"""
    out = {}
    today = now.strftime("%Y-%m-%d")
    for c in changes:
        et = titles.get(c["event_id"], c["event_id"])
        names = c["added"]
        shown = "、".join(names[:6]) + (f" ほか{len(names) - 6}件" if len(names) > 6 else "")
        if c["kind"] == "new_event":
            title, details = f"【新イベント】{et}", f"新しいイベントを検出しました。"
        elif c["kind"] == "schedule_changed":
            title, details = f"【日程変更】{et}", f"日程が更新されています：{shown}"
        else:
            sec = LABEL.get(c["section"], c["section"])
            title = f"【情報追加】{et}：{sec}が判明・追加（{len(names)}件）"
            details = f"{sec}：{shown}"
        nid = "news-" + hashlib.sha1(f"{c['event_id']}|{c['kind']}|{c['section']}|{sorted(names)}".encode()).hexdigest()[:10]
        out[nid] = {"id": nid, "date": today, "date_label": f"{now.month}/{now.day}", "kind": c["kind"], "title": title,
                    "details": details, "targetId": c["event_id"], "sources": [c["src"]]}
    return list(out.values())


def merge_news(existing, new, now):
    cutoff = (now - dt.timedelta(days=config.NEWS_RETENTION_DAYS)).strftime("%Y-%m-%d")
    by_id = {n["id"]: n for n in existing}
    for n in new:
        if n["id"] in by_id:
            for s in n["sources"]:
                if s not in by_id[n["id"]]["sources"]:
                    by_id[n["id"]]["sources"].append(s)
        else:
            by_id[n["id"]] = n
    items = [n for n in by_id.values() if n["date"][:10] >= cutoff]
    items.sort(key=lambda n: n["date"], reverse=True)
    return items
