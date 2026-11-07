"""9DBの「対策ポケモン検索ツール」(記事2734)から、レイド/メガレイドのボスごとの対策ランキングを取る。

流れ: レイド日程ページ(2308)にある 2734?id=<ボスID>&lv=<レベル> のリンクを集める
 → 各ボスのページを描画し、状態ボタン（通常/シャドウ/メガ）を順に押して検索 → 表を読む
 → ポケモンは <a href="data/<ID>"> のIDを、9DBの図鑑データ(pokemon_list)で名前に直す。
表の列: 順位 / ポケモン・技 / 討伐時間(秒) / 必要数(匹) / ゲージ技発動回数 / DPS（TDOは無い）。
シャドウ状態の結果は「通常＋シャドウ」、メガ状態は「通常＋メガ」を混ぜたDPS順なので、状態をまたいで重複を除いて1つのリストにする。
"""
import html as _html
import re
from urllib.parse import parse_qs

from bs4 import BeautifulSoup

SITE = "9db-tool"
BASE = "https://9db.jp/pokemongo/data/2734"
_LINK = re.compile(r"""2734\?([^"'#\s<>]*id=\d[^"'#\s<>]*)""")
_ID = re.compile(r"data/(\d+)")
_NUM = re.compile(r"[\d.]+")


def harvest_links(html):
    """日程ページのHTMLから 2734 へのリンクを集める。[{id, lv, boss_shadow, url}]（出現順・重複なし）。"""
    out, seen = [], set()
    for m in _LINK.finditer(html or ""):
        q = parse_qs(_html.unescape(m.group(1)))
        pid, lv = (q.get("id") or [""])[0], (q.get("lv") or ["5"])[0]
        sh = (q.get("boss_shadow") or ["0"])[0] == "1"
        if not pid.isdigit() or not re.fullmatch(r"[1-6]m?|[1-6]", lv):
            continue
        k = (pid, lv, sh)
        if k in seen:
            continue
        seen.add(k)
        out.append({"id": pid, "lv": lv, "boss_shadow": sh,
                    "url": f"{BASE}?id={pid}&lv={lv}&o=1&pl=40" + ("&boss_shadow=1" if sh else "")})
    return out


def tier_of(lv):
    return "メガ" if str(lv).endswith("m") else f"★{lv}"


def _num(td):
    m = _NUM.search(td.get_text(" ", strip=True)) if td is not None else None
    try:
        return float(m.group(0)) if m else None
    except ValueError:
        return None


def parse_rows(html, id_names):
    """表の各行を読む。名前はIDから。戻り値: (rows, unresolved_ids)。row = {id,name,tag,fast,charged,time,count,gauge,dps}。"""
    soup = BeautifulSoup(html or "", "html.parser")
    rows, bad = [], set()
    for tr in soup.find_all("tr"):
        if tr.select_one(".wiki_rank") is None:
            continue
        a = tr.select_one('a[href*="data/"]')
        m = _ID.search(a.get("href", "")) if a else None
        tds = tr.find_all("td")
        if not m or len(tds) < 6:
            continue
        pid = m.group(1)
        name = id_names.get(pid)
        if not name:
            bad.add(pid)
            continue
        moves = [x.get_text(strip=True) for x in tr.select("a.view_breakpoint_modal")]
        shadow = tr.select_one(".pgo_shadow") is not None or any(x.get("data-shadow") == "1" for x in tr.select("a.view_breakpoint_modal"))
        if shadow and not name.startswith("シャドウ"):
            name = "シャドウ" + name
        dps = _num(tds[5])
        if dps is None:
            continue
        rows.append({"id": pid, "name": name, "tag": "shadow" if shadow else ("mega" if re.match(r"^(スーパーメガ|メガ)", name) else "normal"),
                     "fast": moves[0] if moves else None, "charged": moves[1] if len(moves) > 1 else None,
                     "time": _num(tds[2]), "count": _num(tds[3]), "gauge": _num(tds[4]), "dps": dps})
    return rows, bad


def combine(rows_by_state, limit=60):
    """状態ごとの行を1つのリストにする（同じポケモン・同じ通常/シャドウは最初のものを採用）。DPS順に並べ、順位を振る。"""
    seen, out = set(), []
    for st in ("normal", "shadow", "mega"):
        for r in rows_by_state.get(st) or []:
            k = (r["id"], r["tag"] == "shadow")
            if k in seen:
                continue
            seen.add(k)
            out.append(dict(r))
    out.sort(key=lambda r: -r["dps"])
    res = []
    for i, r in enumerate(out[:limit], 1):
        c = {"name": r["name"], "rank": i, "role": "attacker", "tag": r["tag"], "dps": r["dps"]}
        if r["fast"]:
            c["fast"] = r["fast"]
        if r["charged"]:
            c["charged"] = r["charged"]
        extra = [f"{int(r['time'])}秒" if r["time"] else "", f"必要{r['count']}匹" if r["count"] else ""]
        note = " / ".join(x for x in extra if x)
        if note:
            c["note"] = note
        res.append(c)
    return res


def build_boss(link, id_names, rows_by_state):
    """1ボスぶんの facts（counters.merge_counters に渡せる形）。ボス名が分からない／対策が空なら None。"""
    name = id_names.get(link["id"])
    counters = combine(rows_by_state)
    if not name or not counters:
        return None
    if link["boss_shadow"] and not name.startswith("シャドウ"):
        name = "シャドウ" + name
    return {"name": name, "kind": "raid", "tier": tier_of(link["lv"]), "types": [], "counters": counters}
