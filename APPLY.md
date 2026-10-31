# 適用手順（第1段階）

1. このzipの中身を、リポジトリのルートに**上書きコピー**する（`updater.py` は削除してOK。`index.html` はまだ触らない。`data.json` は残す：新パイプラインが旧 index.html 向けに自動出力するので、**今のサイトのままフィールドリサーチ反映と新情報ニュースが動く**）。
   - 追加されるもの：`SPEC.md` `requirements.txt` `scripts/` `data/` `tests/` `logs/` `.github/workflows/update.yml`
2. GitHub の Settings → Secrets に `GEMINI_API_KEY` が入っていることを確認。
3. GitHub の Actions → 「Scheduled Pokemon GO Data Update」→ **Run workflow** → mode=`diagnose`（AI解析なし）。
4. 終わったら `logs/latest.md` を開く。全ページの取得可否・更新日・文字数が分かる。
   - 取得失敗(HTTP 403等)のサイトがあれば、そのログ（URLとエラー）を共有してください。対応します。
   - ポケマピの `/board/…` で「frlist」警告が出ていれば、フィールドリサーチ表は本文に無いので `/research_fi/` 側で取得します。
5. 問題なければ mode=`bootstrap`（初回取り込み。ニュースは作らない）→ 以降は自動実行（1日4回）。
6. `logs/unresolved_names.json` に名前が出たら `data/pokemon.json` に図鑑番号を追記。
7. 第2段階：表示側(index.html)を data/*.json 読み込みに作り替える。

---
# 適用手順（第2段階の前半：画面の作り直し）

1. **先に**、今の `index.html` を `index.old.html` に名前変更しておく（GitHubで index.html を開く → 鉛筆アイコン(Edit) → ファイル名を `index.old.html` に変えて Commit）。画面がおかしくなったら、このファイル名を `index.html` に戻すだけで元に戻せる。
2. zip の中身を**リポジトリのルートに上書きアップロード**する：`index.html` / `js/`（4ファイル）/ `data/manual/`（4ファイル）/ `data/pokemon.json` / `scripts/pokedex.py` / `tests/test_pipeline.py` / `SPEC.md` / `APPLY.md`。
   - GitHubの画面では、フォルダごとドラッグしてアップロードできる。
3. 少し待って（1〜2分）サイトを開く。画面上部の「最終自動更新」の時刻と、イベント・ニュースが出ていることを確認。
4. 気になる点は、画面のスクリーンショットを添えて伝える。
