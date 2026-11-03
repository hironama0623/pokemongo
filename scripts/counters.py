"""対策データ（data/counters.json）の統合。サイトごとの結果を別々に保存し、ランキングへの統合は画面側で行う。"""
import re

from . import pokedex

_BAD_NAME = re.compile(r"[0-9*＊]|^(?:通\s*常|シ\s*ャ\s*ド\s*ウ|メ\s*ガ)$")   # 見出し語そのものだけを弾く（シャドウバンギラス等は残す）

_PAREN = str.maketrans({"（": "(", "）": ")"})


def boss_key(name, kind):
    n = re.sub(r"[\s　・]", "", str(name)).translate(_PAREN)
    gmax = "キョダイ" in n
    n = re.sub(r"キョダイマックス|ダイマックス|キョダイ", "", n).replace("()", "")
    return f"{kind}:{'g' if gmax else ''}{n}"


def valid_counter(c, names):
    """表の中身が画像で、AIが技名・順位・数値を名前として拾ったものを捨てる。名前が実在のポケモン（図鑑にある種）に解決できるものだけ残す。"""
    n = str(c.get("name") or "")
    if not n or len(n) > 24 or (_BAD_NAME.search(n) and not re.fullmatch(r"ポリゴン2", n.split("(")[0])):
        return False
    d = pokedex.base_name(n)
    return bool(names.get(d) or names.get(n) or pokedex.contained_species(n, names))


def valid_boss(name, names):
    """ボス名が実在のポケモンに解決できること（「あくタイプ」のような分類名を除く）。"""
    return valid_counter({"name": name}, names) and not str(name).endswith("タイプ")


def sanitize(store, names):
    """保存済みの対策データから、無効な項目（ポケモン名として成り立たないもの）を取り除く。空になったサイト/ボスは消す。戻り値: 取り除いた件数。"""
    removed = 0
    for key in list(store["bosses"]):
        b = store["bosses"][key]
        if not valid_boss(b["name"], names):
            removed += sum(len(s["counters"]) for s in b["by_site"].values())
            del store["bosses"][key]
            continue
        for site in list(b["by_site"]):
            cs = b["by_site"][site]["counters"]
            good = [c for c in cs if valid_counter(c, names)]
            removed += len(cs) - len(good)
            if good:
                b["by_site"][site]["counters"] = good
            else:
                del b["by_site"][site]
        if not b["by_site"]:
            del store["bosses"][key]
    return removed


def merge_counters(store, facts, src, names, unresolved, now):
    """facts（normalize済み）を store["bosses"] に入れる。同じサイト・同じボスは、より新しい記事で置き換える。戻り値: 更新したボス名のリスト。"""
    touched = []
    for b in facts.get("bosses", []):
        if not valid_boss(b["name"], names):
            continue
        key = boss_key(b["name"], b["kind"])
        b["counters"] = [c for c in b["counters"] if valid_counter(c, names)]
        if not b["counters"]:
            # このサイトのこのボスは取り直した結果が無効だった。以前の無効な保存分があれば消す
            old_entry = store["bosses"].get(key)
            if old_entry and src["site"] in old_entry["by_site"]:
                del old_entry["by_site"][src["site"]]
                if not old_entry["by_site"]:
                    del store["bosses"][key]
            continue
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
