"""data/ の読み書き。書き込みは一時ファイル→置換で行い、途中で落ちても前回データを壊さない。"""
import json
import os
import tempfile

from . import config


def load(name, default):
    p = config.DATA / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{p} が壊れています: {e}") from e  # 黙って空にしない


def save(name, obj):
    config.DATA.mkdir(parents=True, exist_ok=True)
    p = config.DATA / name
    fd, tmp = tempfile.mkstemp(dir=config.DATA, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
