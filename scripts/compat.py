"""【第2段階で削除】現行 index.html（data.json を読む旧形式）向けの互換出力。
新しい data/*.json から旧形式の data.json を作り、index.html を触らなくても
「フィールドリサーチ自動反映」「新情報ニュース」が今のサイトに出るようにする橋渡し。"""
import datetime as dt

from . import config

_BAR = {"main": "bar-main", "cd": "bar-cd", "raid": "bar-raid", "dmax": "bar-dmax", "collab": "bar-collab"}


def _mon(m):
    return {"dex": m.get("dex") or 25, "name": m["name"], "shiny": bool(m.get("shiny")), "note": m.get("note") or ""}


def build_legacy(details, events, news, meta, index):
    fr, dyn = {}, []
    for eid, d in details["events"].items():
        tasks = [{"task": t["task"], "rewardDex": r.get("dex") or 25, "rewardName": r["name"] + (f"（{r['cp']}）" if r.get("cp") else ""),
                  "shiny": bool(r.get("shiny")), "note": "出典: " + "・".join(sorted({s['site'] for s in t['sources']}))}
                 for t in d.get("field_research", []) for r in t["rewards"]]
        if tasks:
            fr[eid] = tasks
        wilds = [_mon(m) for m in d.get("wilds", [])]
        for m in (d.get("surprise_box") or {}).get("pokemon", []):
            x = _mon(m)
            x["note"] = "サプライズボックス" + (f"／{x['note']}" if x["note"] else "")
            wilds.append(x)
        if wilds:
            dyn.append({"id": eid, "title": next((e["title"] for e in index if e["id"] == eid), eid), "wilds": wilds})
    for eid, e in events["events"].items():
        s, en = dt.datetime.fromisoformat(e["start"][:10]), dt.datetime.fromisoformat(e["end"][:10])
        dyn.append({"id": eid, "month": s.month, "title": e["title"], "barClass": _BAR[e["category"]], "category": e["category"],
                    "startDay": s.day, "endDay": en.day if en.month == s.month else 28, "hasPaid": bool(e.get("hasPaid")),
                    "dateText": e.get("dateText") or e["start"][:10], "summary": e.get("summary") or "",
                    "freeFeatures": e.get("freeFeatures", []), "paidFeatures": e.get("paidFeatures", []),
                    "wilds": [], "raids": [], "fieldResearches": [], "tasks": []})
    ts = meta.get("last_success_at")
    upd = dt.datetime.fromisoformat(ts).astimezone(config.JST).strftime("%Y/%m/%d %H:%M JST") if ts else ""
    latest = [{k: n[k] for k in ("id", "date", "date_label", "title", "details", "targetId")} for n in news["items"]]
    return {"updated_at": upd, "latest_news": latest, "field_research_updates": fr, "dynamic_events": dyn}
