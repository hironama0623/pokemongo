"""対策データ（data/counters.json）の統合。サイトごとの結果を別々に保存し、ランキングへの統合は画面側で行う。"""
import re

from . import pokedex

_PAREN = str.maketrans({"（": "(", "）": ")"})


def boss_key(name, kind):
    n = re.sub(r"[\s　・]", "", str(name)).translate(_PAREN)
    gmax = "キョダイ" in n
    n = re.sub(r"キョダイマックス|ダイマックス|キョダイ", "", n).replace("()", "")
    return f"{kind}:{'g' if gmax else ''}{n}"


def merge_counters(store, facts, src, names, unresolved, now):
    """facts（normalize済み）を store["bosses"] に入れる。同じサイト・同じボスは、より新しい記事で置き換える。戻り値: 更新したボス名のリスト。"""
    touched = []
    for b in facts.get("bosses", []):
        key = boss_key(b["name"], b["kind"])
        for c in b["counters"]:
            pokedex.fill_dex(c, names, unresolved)
        entry = store["bosses"].setdefault(key, {"name": b["name"], "kind": b["kind"], "tier": b.get("tier"), "types": b.get("types") or [], "by_site": {}})
        if b.get("tier") and not entry.get("tier"):
            entry["tier"] = b["tier"]
        if b.get("types") and not entry.get("types"):
            entry["types"] = b["types"]
        old = entry["by_site"].get(src["site"])
        if old and (old.get("article_updated") or "") > (src.get("article_updated") or "") and old["url"] != src["url"]:
            continue   # 同じサイトの、より新しい記事が既にある
        entry["by_site"][src["site"]] = {"url": src["url"], "article_updated": src.get("article_updated"),
                                         "fetched_at": src.get("fetched_at"), "counters": b["counters"]}
        entry["updated_at"] = now.isoformat()
        touched.append(b["name"])
    return touched
