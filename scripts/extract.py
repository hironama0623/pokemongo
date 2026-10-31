"""HTML → 本文テキスト / 記事更新日 / 記事リンク。ネットワークには触れない（テストしやすくするため）。"""
import datetime as dt
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from . import config

_DATE_RE = r"(20\d\d)[/年.\-](\d{1,2})[/月.\-](\d{1,2})日?(?:[\sT]*(\d{1,2}):(\d{2}))?"
_UPDATE_RE = re.compile(r"(?:最終更新|更新日時?|更新)[:：\s]*" + _DATE_RE)
_STAMP_RE = re.compile(_DATE_RE)


def _to_dt(y, m, d, hh=None, mm=None):
    try:
        return dt.datetime(int(y), int(m), int(d), int(hh or 0), int(mm or 0), tzinfo=config.JST)
    except ValueError:
        return None


def _parse_iso(s):
    try:
        d = dt.datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=config.JST)
    except Exception:
        return None


def extract_date(soup, text):
    """(datetime|None, kind) を返す。更新日 > 公開日 の優先順。kind は modified/published/text/None。"""
    for key in ("article:modified_time", "og:updated_time", "dateModified"):
        m = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"itemprop": key})
        if m and m.get("content") and _parse_iso(m["content"]):
            return _parse_iso(m["content"]), "modified"
    for sc in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(sc.string or "")
        except Exception:
            continue
        for node in (data if isinstance(data, list) else [data]):
            if isinstance(node, dict):
                v = node.get("dateModified") or node.get("datePublished")
                if v and _parse_iso(str(v)):
                    return _parse_iso(str(v)), ("modified" if node.get("dateModified") else "published")
    t = soup.find("time", attrs={"datetime": True})
    if t and _parse_iso(t["datetime"]):
        return _parse_iso(t["datetime"]), "modified"
    m = _UPDATE_RE.search(text)
    if m:
        d = _to_dt(*m.groups())
        if d:
            return d, "text"
    m = soup.find("meta", attrs={"property": "article:published_time"})
    if m and m.get("content") and _parse_iso(m["content"]):
        return _parse_iso(m["content"]), "published"
    return None, None


_BLOCK = ["li", "p", "tr", "table", "dl"]


def html_to_text(html):
    """本文テキストと(soup, 生テキスト)を返す。表は「セル | セル」の行にし、画像は alt を残す。"""
    soup = BeautifulSoup(html, "html.parser")
    raw_text = soup.get_text(" ", strip=True)
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe", "form"]):
        tag.decompose()
    for img in soup.find_all("img"):
        alt = (img.get("alt") or "").strip()
        img.replace_with(f" {alt} " if alt else " ")
    container = None
    for sel in ("#the-content", "article", ".entry-content", "#main", "main", "#contents", "#content"):
        c = soup.select_one(sel)
        if c and len(c.get_text(strip=True)) >= 300:
            container = c
            break
    container = container or soup.body or soup
    lines, last, h1_idx = [], None, set()
    for el in container.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "dt", "dd"]):
        if el.name in ("p", "li", "dt", "dd"):
            if el.find_parent("tr") or el.find(["li", "p", "tr", "table"]):
                continue
        if el.name == "tr":
            if el.find("table"):
                continue
            cells = [c.get_text(" ", strip=True) for c in el.find_all(["th", "td"])]
            txt = " | ".join(c for c in cells if c)
        else:
            txt = el.get_text(" ", strip=True)
        txt = re.sub(r"\s+", " ", txt).strip()
        if len(txt) < 2 or txt == last:
            continue
        last = txt
        if el.name in ("h1", "h2", "h3", "h4"):
            if el.name == "h1":
                h1_idx.add(len(lines))
            lines.append(f"\n### {txt}")
        elif el.name == "li":
            lines.append(f"- {txt}")
        else:
            lines.append(txt)
    # GameWith等はサイト共通メニュー(ホーム/ゲーム検索/ログイン…)が <nav> ではなく <ul> で本文の前に付く。
    # 記事タイトル(h1)より前に長い行の並びがあれば、メニューとみなして捨てる
    h1 = next((i for i, l in enumerate(lines) if l.startswith("\n### ") and i in h1_idx), None)
    if h1 is not None and h1 >= 8:
        lines = lines[h1:]
    structured = "\n".join(lines).strip()
    # <div>+<br> だけで書かれた本文は上のタグ巡回で拾えないため、短すぎる場合は全文テキストで補う
    full, prev = [], None
    for l in container.get_text("\n").split("\n"):
        l = re.sub(r"\s+", " ", l).strip()
        if len(l) >= 2 and l != prev:
            full.append(l)
            prev = l
    full_text = "\n".join(full)
    if len(structured) < 600 and len(full_text) > len(structured) * 1.5:
        structured = full_text
    return structured, soup, raw_text


def content_hash(text):
    """更新日時など毎回変わる表記を除いてハッシュ化（無駄なAI再解析を防ぐ）。"""
    t = _STAMP_RE.sub("", text)
    t = re.sub(r"(?m)^.*(?:最終更新|更新日時?).*$", "", t)
    t = re.sub(r"\s+", "", t)
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def normalize_url(url):
    p = urlsplit(url)
    path = p.path
    m = re.match(r"^(.*?/board/\d+/?)", path)  # ポケマピの &gsessionid= 等の混入対策
    if m:
        path = m.group(1)
    return urlunsplit((p.scheme, p.netloc, path, "", ""))


def extract_links(html, base_url, link_re):
    """[(key, url, anchor_text)] を出現順・重複なしで返す。"""
    soup = BeautifulSoup(html, "html.parser")
    rx = re.compile(link_re)
    seen, out = set(), []
    for a in soup.find_all("a", href=True):
        url = normalize_url(urljoin(base_url, a["href"]))
        m = rx.match(url)
        if m and url not in seen:
            seen.add(url)
            out.append((m.group(1), url, a.get_text(" ", strip=True)[:80]))
    return out


def page_header(soup):
    """<title> と og:description（イベント名・期間が入っていることが多い）。本文とは別に保持してAIに渡す。"""
    t = soup.find("title")
    d = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
    parts = []
    if t and t.get_text(strip=True):
        parts.append("タイトル: " + re.sub(r"\s+", " ", t.get_text(strip=True)))
    if d and d.get("content"):
        parts.append("概要: " + re.sub(r"\s+", " ", d["content"]).strip()[:600])
    return "\n".join(parts)
