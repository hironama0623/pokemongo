"""スキーマ検証。AIの出力も保存直前のデータも、ここを通ったものだけが data/ に書かれる（SPEC.md 4章）。"""
import jsonschema

_STR = {"type": "string", "minLength": 1}
_NSTR = {"type": ["string", "null"]}
_DATE = {"type": "string", "pattern": r"^20\d\d-\d\d-\d\d(T\d\d:\d\d)?$"}
_SRC = {"type": "object", "required": ["site", "url"],
        "properties": {"site": {"enum": ["pokemapi", "gamewith", "9db", "official"]}, "url": _STR,
                       "fetched_at": _NSTR, "article_updated": _NSTR}}
_SRCS = {"type": "array", "minItems": 1, "items": _SRC}          # 出典なしの値は保存しない
_DEX = {"type": ["integer", "null"], "minimum": 1, "maximum": 20000}

_MON = {"type": "object", "required": ["name"],
        "properties": {"name": _STR, "dex": _DEX, "shiny": {"type": ["boolean", "null"]}, "note": _NSTR,
                       "rarity": _NSTR, "tier": _NSTR, "distance": _NSTR}}
_REWARD = {"type": "object", "required": ["name"],
           "properties": {"name": _STR, "dex": _DEX, "cp": _NSTR, "shiny": {"type": ["boolean", "null"]}}}
_TASK = {"type": "object", "required": ["task", "rewards"],
         "properties": {"task": _STR, "rewards": {"type": "array", "minItems": 1, "items": _REWARD}}}

# --- AIが1記事から返す形 ---
ARTICLE = {
    "type": "object", "required": ["relevant", "event_id"],
    "properties": {
        "relevant": {"type": "boolean"},
        "event_id": {"type": "string"},   # 既知ID / "NEW:<slug>" / ""（該当イベントなし）
        "event_info": {"type": ["object", "null"], "properties": {
            "title": _STR, "category": {"enum": ["main", "cd", "raid", "dmax", "collab"]},
            "start": _DATE, "end": _DATE, "dateText": _NSTR, "summary": _NSTR, "hasPaid": {"type": ["boolean", "null"]},
            "freeFeatures": {"type": "array", "items": _STR}, "paidFeatures": {"type": "array", "items": _STR}}},
        "wilds": {"type": "array", "items": _MON},
        "raids": {"type": "array", "items": _MON},
        "eggs": {"type": "array", "items": _MON},
        "surprise_box": {"type": ["object", "null"], "properties": {
            "pokemon": {"type": "array", "items": _MON},
            "items": {"type": "array", "items": {"type": "object", "required": ["name"], "properties": {"name": _STR, "qty": _NSTR}}}}},
        "field_research": {"type": "array", "items": _TASK},
        "time_challenge": {"type": "array", "items": _TASK},
    },
}

# --- 保存するファイルの形 ---
_with_src = lambda base: {**base, "required": base.get("required", []) + ["sources"],  # noqa: E731
                          "properties": {**base["properties"], "sources": _SRCS}}
DETAILS = {
    "type": "object", "required": ["schema_version", "events"],
    "properties": {"schema_version": {"const": 1}, "events": {"type": "object", "additionalProperties": {
        "type": "object", "properties": {
            "updated_at": _NSTR,
            "schedule": {"type": "object", "required": ["start", "end", "sources"],
                         "properties": {"start": _DATE, "end": _DATE, "sources": _SRCS}},
            "wilds": {"type": "array", "items": _with_src(_MON)},
            "raids": {"type": "array", "items": _with_src(_MON)},
            "eggs": {"type": "array", "items": _with_src(_MON)},
            "surprise_box": {"type": "object", "properties": {
                "pokemon": {"type": "array", "items": _with_src(_MON)},
                "items": {"type": "array", "items": _with_src({"type": "object", "required": ["name"], "properties": {"name": _STR, "qty": _NSTR}})}}},
            "field_research": {"type": "array", "items": _with_src(_TASK)},
            "time_challenge": {"type": "array", "items": _with_src(_TASK)},
        }}}},
}
EVENTS = {
    "type": "object", "required": ["schema_version", "events"],
    "properties": {"schema_version": {"const": 1}, "events": {"type": "object", "additionalProperties": _with_src({
        "type": "object", "required": ["id", "title", "category", "start", "end"],
        "properties": {"id": _STR, "title": _STR, "category": {"enum": ["main", "cd", "raid", "dmax", "collab"]},
                       "start": _DATE, "end": _DATE, "dateText": _NSTR, "summary": _NSTR, "hasPaid": {"type": ["boolean", "null"]},
                       "freeFeatures": {"type": "array", "items": _STR}, "paidFeatures": {"type": "array", "items": _STR},
                       "created_at": _STR}})}},
}
NEWS = {
    "type": "object", "required": ["schema_version", "items"],
    "properties": {"schema_version": {"const": 1}, "items": {"type": "array", "items": _with_src({
        "type": "object", "required": ["id", "date", "kind", "title", "details", "targetId"],
        "properties": {"id": _STR, "date": _DATE, "date_label": _STR,
                       "kind": {"enum": ["new_event", "event_update", "schedule_changed"]},
                       "title": _STR, "details": _STR, "targetId": _STR}})}},
}
META = {"type": "object", "required": ["schema_version", "last_run_at", "last_run_status"],
        "properties": {"schema_version": {"const": 1}, "last_run_at": _STR,
                       "last_run_status": {"enum": ["ok", "partial", "failed"]},
                       "last_success_at": _NSTR, "last_content_change_at": _NSTR, "counts": {"type": "object"}}}

SCHEMAS = {"article": ARTICLE, "details": DETAILS, "events": EVENTS, "news": NEWS, "meta": META}


def validate(kind, obj):
    """OKなら None、NGならエラー文字列を返す。"""
    try:
        jsonschema.validate(obj, SCHEMAS[kind])
        return None
    except jsonschema.ValidationError as e:
        path = "/".join(str(p) for p in e.absolute_path)
        return f"{kind}: {e.message[:200]} (at {path})"
