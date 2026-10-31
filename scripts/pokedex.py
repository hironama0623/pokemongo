"""ポケモン名 → 全国図鑑番号。data/pokemon.json（基本種名→番号）で補完し、解決できない名前は記録する。
フォルム違い（メガ/キョダイ/リージョン等）の画像IDは表示側（第2段階）で解決する。"""
import re

_PAREN = re.compile(r"[（(].*?[）)]")


def base_name(name):
    n = _PAREN.sub("", name)
    n = re.sub(r"^(メガ|ゲンシ|キョダイマックス|キョダイ|ダイマックス|シャドウ|アローラ|ガラル|ヒスイ|パルデア|色違い)\s*", "", n)
    return re.sub(r"[XYＸＹ]$", "", n).strip()


def contained_species(name, table):
    """名前に含まれる種名を探す（例:「リボンをつけた ヤバチャ」→ヤバチャ）。入れ子の短い名前は除き、
    1種類に定まるときだけ返す（「ヒトモシ / ヤミラミ」のように複数あるときは None）。"""
    hits = [k for k in table if len(k) >= 3 and k in name]
    hits = [k for k in hits if not any(k != o and k in o for o in hits)]
    return table[hits[0]] if len(hits) == 1 else None


def fill_dex(mon, table, unresolved):
    """dex が無い／辞書と食い違う場合は辞書を優先して埋める。解決不能なら unresolved に追加。"""
    if mon.get("dex") is None or mon["dex"] < 10000:
        d = table.get(base_name(mon["name"])) or table.get(mon["name"]) or contained_species(mon["name"], table)
        if d:
            mon["dex"] = d
        elif mon.get("dex") is None:
            unresolved.add(mon["name"])
    return mon
