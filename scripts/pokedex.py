"""ポケモン名 → 全国図鑑番号。data/pokemon.json（基本種名→番号）で補完し、解決できない名前は記録する。
フォルム違い（メガ/キョダイ/リージョン等）の画像IDは表示側（第2段階）で解決する。"""
import re

_PAREN = re.compile(r"[（(].*?[）)]")


def base_name(name):
    n = _PAREN.sub("", name)
    n = re.sub(r"^(メガ|ゲンシ|キョダイマックス|キョダイ|ダイマックス|シャドウ|アローラ|ガラル|ヒスイ|パルデア|色違い)\s*", "", n)
    return re.sub(r"[XYＸＹ]$", "", n).strip()


def fill_dex(mon, table, unresolved):
    """dex が無い／辞書と食い違う場合は辞書を優先して埋める。解決不能なら unresolved に追加。"""
    if mon.get("dex") is None or mon["dex"] < 10000:
        d = table.get(base_name(mon["name"])) or table.get(mon["name"])
        if d:
            mon["dex"] = d
        elif mon.get("dex") is None:
            unresolved.add(mon["name"])
    return mon
