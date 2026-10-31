"""1記事 = 1回のAI解析。入力が小さいので精度が落ちにくい。出力はスキーマ検証を通ったものだけ採用する。"""
import json
import os
import re
import time

from . import config, schemas


class AnalyzeError(Exception):
    pass


class QuotaExhausted(AnalyzeError):
    """APIの1日あたりの上限に達した。待っても回復しないので、その回の解析を打ち切る。"""


PROMPT = """あなたはポケモンGO攻略記事から事実だけを抜き出す抽出器です。以下の【記事本文】だけを根拠にJSONを1つ返してください。

【厳守ルール】
1. 記事本文に書かれている事実だけを書く。あなたの記憶・推測・過去イベントの知識は絶対に混ぜない。
2. 記事に無い項目は空配列 [] にする（埋めようとしない）。表が「別記事参照」「画像のみ」で中身が無い場合も [] 。
3. event_id は【既知イベント】から最も合致するものを選ぶ。どれにも当たらない新しいイベントなら "NEW:英数字ハイフンのslug" 、
   イベント・レイド・マックスバトル等に関係しない記事なら relevant=false, event_id="" 。
   NEW のときは event_info に title / category / start / end を必ず入れる。
4. 日付は {year} 年として ISO 形式（例 2026-10-27T10:00 / 時刻不明なら 2026-10-27）。
5. field_research は「タスク条件」と「報酬ポケモン」の対応。報酬が複数ならすべて rewards に入れる。CP が書いてあれば cp に文字列で。
6. surprise_box は中身（ポケモン名・アイテム名）が本文に明記されているときだけ。
7. ポケモン名は記事の表記のまま、フォルム違いは「ズバット(トップハット)」のように括弧で。dex は通常種で確実に分かる全国図鑑番号のみ。フォルム違い・不明は null 。
8. category: main=季節/大型イベント, cd=コミュニティ・デイ, raid=レイド系, dmax=マックスバトル系, collab=コラボ/GOパス/その他。

【出力JSONの形】
{{"relevant": true, "event_id": "...",
 "event_info": {{"title": "", "category": "main", "start": "", "end": "", "dateText": "", "summary": "", "hasPaid": false, "freeFeatures": [], "paidFeatures": []}} または null,
 "wilds": [{{"name": "", "dex": null, "shiny": true, "note": "", "rarity": "通常|レア|null"}}],
 "raids": [{{"name": "", "dex": null, "shiny": true, "tier": "★1"}}],
 "eggs": [{{"name": "", "dex": null, "distance": "10km"}}],
 "surprise_box": {{"pokemon": [], "items": [{{"name": "", "qty": "×6"}}]}} または null,
 "field_research": [{{"task": "", "rewards": [{{"name": "", "dex": null, "cp": "", "shiny": true}}]}}],
 "time_challenge": [{{"task": "", "rewards": [{{"name": ""}}]}}]}}

【既知イベント】
{known}

【記事】サイト={site} URL={url} 記事更新日={updated}
【記事本文】
{body}
"""


def build_prompt(article, known_events, year):
    known = "\n".join(f"- {e['id']}: {e['title']} ({e['start'][:10]}〜{e['end'][:10]})" for e in known_events)
    return PROMPT.format(year=year, known=known, site=article["site"], url=article["url"],
                         updated=article.get("updated") or "不明", body=article["text"])


_client = None
_last_call = 0.0
last_info = {}  # 直近の analyze() の実績: {"model","attempts","seconds"}（ログに残す）
_dead = set()   # 1日の上限に達したモデル（上限はモデルごとなので、そのモデルだけ以後スキップして次のモデルを使う）


def gemini_call(model, prompt):
    global _client, _last_call
    wait = config.AI_MIN_INTERVAL - (time.monotonic() - _last_call)  # 無料枠のレート制限(429)を避ける間隔
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()
    from google import genai  # 遅延import（テスト・診断モードでは不要）
    from google.genai import types
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"],
                               http_options=types.HttpOptions(timeout=config.AI_TIMEOUT_SEC * 1000))  # 応答が来ない呼び出しで時間を使い切らない
    r = _client.models.generate_content(model=model, contents=prompt,
                                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.0))
    return r.text


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    return json.loads(text)


def _retry_delay(msg, attempt):
    m = re.search(r"retry(?:Delay)?\D{0,12}(\d+(?:\.\d+)?)s", msg or "")
    return min(float(m.group(1)) + 2, 60) if m else min(15 * attempt, 45)


def _transient(msg):
    return any(k in msg for k in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "500", "DEADLINE"))


def normalize(facts):
    """AIの軽微な形のズレを直す（文字列だけで返されたポケモン名を {"name":..} にする等）。値は変えない。"""
    if not isinstance(facts, dict):
        return facts

    def fix(lst):
        return [{"name": x.strip()} if isinstance(x, str) and x.strip() else x for x in lst] if isinstance(lst, list) else lst
    for k in ("wilds", "raids", "eggs"):
        if k in facts:
            facts[k] = fix(facts[k])
    sb = facts.get("surprise_box")
    if isinstance(sb, dict):
        for k in ("pokemon", "items"):
            if k in sb:
                sb[k] = fix(sb[k])
    for k in ("field_research", "time_challenge"):
        for t in facts.get(k) or []:
            if isinstance(t, dict) and "rewards" in t:
                t["rewards"] = fix(t["rewards"])
    return facts


def analyze(article, known_events, models, call=gemini_call, year=2026, sleep=time.sleep, tries=3):
    prompt = build_prompt(article, known_events, year)
    errors, calls, t0 = [], 0, time.monotonic()
    for m in models:
        if m in _dead:
            continue
        for attempt in range(1, tries + 1):
            calls += 1
            try:
                facts = normalize(parse_json(call(m, prompt)))
            except Exception as e:  # noqa: BLE001
                msg = f"{type(e).__name__}: {str(e)}"
                if re.search(r"PerDay|per day|daily", msg, re.I) and "429" in msg:
                    _dead.add(m)
                    errors.append(f"{m}: 1日の利用上限に到達")
                    break
                if _transient(msg) and attempt < tries:  # 429/503 は待って同じモデルで再試行
                    sleep(_retry_delay(msg, attempt))
                    continue
                errors.append(f"{m}: {msg[:150]}")
                break
            err = schemas.validate("article", facts)
            if err is None:
                last_info.clear()
                last_info.update(model=m, attempts=calls, seconds=round(time.monotonic() - t0, 1))
                return facts
            errors.append(f"{m}: {err}")
            break
    last_info.clear()
    last_info.update(model=None, attempts=calls, seconds=round(time.monotonic() - t0, 1))
    if all(m in _dead for m in models):
        raise QuotaExhausted(" / ".join(errors) or "全モデルが1日の利用上限に到達")
    raise AnalyzeError(" / ".join(errors))
