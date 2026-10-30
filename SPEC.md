# Pokémon GO 総合攻略ハブ 仕様書（SPEC.md）

このファイルが**唯一の基準**。改修を依頼するときは、この SPEC.md と「直したい1ファイル」だけを渡す（AIに全コードを渡し続けると精度が落ちるため）。
仕様を変えるときは、先にこのファイルを直してからコードを直す。

## 1. 目的と画面構成（必ず維持）
- 4タブ：**シーズン24常設 / イベント&日程 / レイド&DMax / GOパス**
- ガントチャート、アコーディオン、「戻る」ナビ（ヘッダー・フローティング・スワイプ）、既読ニュース、イベント非表示。
- コンパクト化・効率化は可。ただし上記の見た目と操作は変えない。

## 2. 要望と対応状況
| # | 要望 | 方針 | 段階 |
|---|---|---|---|
| 1 | フィールドリサーチを開始後の詳細で自動更新 | 各記事から「タスク→報酬」を抽出し `event_details.json` の `field_research` に統合 | 1（取得側）/ 2（表示側） |
| 2 | 入手ポケモン（サプライズボックス等）をイベント内容へ | `surprise_box` / `wilds` / `raids` / `eggs` を同様に統合 | 1 / 2 |
| 3 | レイド&DMax対策を4サイト照合で作り直し | `data/raids.json`・`data/dmax.json`。**各サイトの順位を出典付きで保存し、一致度で並べる**。出典のないDPS/TDO数値は表示しない | 2 |
| 4 | 生息地の出現ポケモンにイラスト／名前は全体でイラスト付き | 共通部品 `mon(name, dex)` を作り全箇所で使用。`data/pokemon.json` で図鑑番号を補完 | 2 |
| 5 | GOパス：イベント連動パスの詳細更新／100ランク表を実データへ | `data/gopass.json`。**記事に載っているランクだけ表示**（未掲載は出さない）。剰余計算の生成は廃止 | 2 |
| 6 | ニュース：新規だけでなく既発表イベントへの新情報追加も告知 | `merge.py` が増分を機械的に検出（AIに判断させない）。種別 `new_event / event_update / schedule_changed` | 1 |
| 7 | 取得ロジック再構築、1か月以内の更新記事は全て取得しログ | `scripts/` 一式。ログは `logs/` | 1 |

## 3. リポジトリ構成
```
index.html              表示専用（第2段階で薄くする）
data/
  event_index.json      既知イベントの基準一覧（id/title/start/end）。AIがイベントを紐づける際の候補
  event_details.json    ★自動更新：イベント別の判明情報（FR/サプライズボックス/野生/レイド/タマゴ…）
  events.json           ★自動更新：記事から見つかった新規イベント（id は ev-auto-…）
  news.json             ★自動更新：ニュース（出典付き、45日保持）
  meta.json             ★実行結果。last_run_status と last_success_at を分けて持つ
  state.json            ★記事ごとの本文ハッシュ（差分スキップ用）
  pokemon.json          ポケモン名→全国図鑑番号（手で追記してよい）
data.json               【第2段階で廃止】旧 index.html 向け互換出力（scripts/compat.py が自動生成）
scripts/
  config.py   取得先・期間・上限（設定はここだけ）
  fetch.py    HTTP取得・記事候補の発見
  extract.py  HTML→本文/更新日/リンク/ハッシュ
  analyze.py  Geminiで1記事=1回の抽出（プロンプトはここ）
  schemas.py  スキーマ（AI出力・保存データ）
  merge.py    統合と増分検出→ニュース生成
  store.py    原子的な読み書き
  pokedex.py  図鑑番号の補完
  logger.py   logs/ 出力
  run.py      全体の流れ
tests/test_pipeline.py  ネットワーク/AIを差し替えた結合テスト
logs/       run-YYYYMMDD-HHMM.json / latest.json / latest.md / unresolved_names.json
.github/workflows/update.yml
```

## 4. ルール（変更禁止の基準）
1. **出典のない値は保存も表示もしない。** 保存する各項目は `sources`（サイト名＋URL）を必ず持つ（スキーマで強制）。
2. **スキーマ検証を通ったものだけ保存。** AI出力は記事ごとに検証し、NGなら**その記事の結果だけ捨てて**ログに残す。保存直前に全ファイルを再検証し、NGなら何も書かない。
3. **失敗時は前回データを維持。** `updated_at` だけ更新して成功に見せない。`meta.json` は `last_run_at`（試行）と `last_success_at`（成功）を分ける。1ページも取れない／保存前検証NG／APIキー無しは終了コード1（Actionsが赤くなる）。`|| exit 0` は使わない。
4. **記事本文は切り詰めない**（AIへの上限は `MAX_AI_CHARS`=60,000字。切った場合は `chars_sent` で分かる）。表は「セル | セル」の行、画像は alt を本文に残す。
5. **対象は直近 `WINDOW_DAYS`=31日以内に更新された記事のみ。** 記事の更新日は meta / JSON-LD / `<time>` / 本文の「更新」表記の順で取る。取れない記事は取得し `date_unknown` としてログに残す（落とさない）。ハブページ（`hubs`）は期間判定なし。
6. **本文ハッシュが前回と同じならAI解析をスキップ。** ハッシュは更新日時などの毎回変わる表記を除いて計算する。解析に失敗した記事はハッシュを保存しない（次回リトライ）。
7. **ニュースの差分判定はコード（merge.py）で行う。** 新イベント／既存イベントへの追加（FR・サプライズボックス・野生・レイド・タマゴ・タイムチャレンジ）／日程変更。件数上限で捨てない（表示側で絞る）。ニュースIDは内容のハッシュで、同じ内容は二重に出ない。
8. **ログ**：全ページについて URL・種別・状態・HTTP・記事更新日・取得文字数・AI送信文字数・処理（analyzed / skipped_unchanged / skipped_out_of_window / skipped_empty / fetch_failed / analyze_failed / validation_failed）・理由を `logs/` に保存（30日保持）。スキップ理由も必ず残す。
9. 実行頻度：日本時間 7:00 / 12:00 / 18:00 / 22:00。手動実行は `diagnose`（取得とログのみ）/ `bootstrap`（初回、ニュースを作らない）/ `run`。

## 5. 取得先（config.py）
| サイト | 一覧 | 記事 | 備考 |
|---|---|---|---|
| ポケマピ | `/pokego02416/`（イベント一覧）, トップ | `/board/番号/` | 旧 `/events/` は廃止。FR表は `[frlist]` 埋め込みで本文HTMLに無い場合あり→ログに警告、`/research_fi/` をハブとして取得 |
| GameWith | トップ | `/article/show/番号` | 番号が `min_id` 未満は古い記事として除外 |
| 9DB | トップ | `/pokemongo/data/番号` | トップに記事ごとの更新日時あり |
| 公式 | `/ja/news` | `/ja/news/slug` | 一覧に日付なし→記事ページで確認。先頭 `MAX_ARTICLES_PER_SOURCE` 件 |

## 6. 既知の要確認事項（2026/10/30 時点の調査）
- 現行の `index.html` は「大きな足跡」を クレセリア／ダークライ としているが、公式（10/29）は **ムゲンダイナ再来**。第2段階で `data/` へ移す際に実記事と照合して修正する。
- サプライズボックスの中身は **サイトにより記載が違う**（GameWith：ズバット/フワライド/ゲンガー/ロコン＋アメ類、公式：ピカチュウ/ズバット/ヤバチャのアメ等）。各項目に `sources` を持たせ、表示側で出典を併記する。
- 10/25 以降ニュースが増えなかった原因：①旧 updater が Gemini 例外時に `updated_at` だけ更新して成功を装う ②ポケマピ `/events/` が取得失敗 ③各ページ6,000〜7,500字で打ち切り ④12日以内・8件・除外語で絞込 ⑤`|| exit 0` で失敗が隠れる。
- この作業環境から4サイトの生HTMLは取得できなかったため、**実サイトでの取得確認は GitHub Actions の `diagnose` 実行で行う**（手順は APPLY.md）。

## 7. データ形式
正本は `scripts/schemas.py`。要点：
- `event_details.json`: `{schema_version, events: {<event_id>: {updated_at, schedule?, wilds[], raids[], eggs[], surprise_box{pokemon[],items[]}, field_research[{task, rewards[{name,dex,cp,shiny}], sources[]}], time_challenge[]}}}`
- `news.json`: `{schema_version, items:[{id,date,date_label,kind,title,details,targetId,sources[]}]}`
- ポケモン画像は `dex` から。フォルム違い（メガ/キョダイ/リージョン等）の画像ID解決は表示側の `resolveSpecialFormId` を維持。`dex` が null のときはプレースホルダー。

## 8. 第2段階（予定）
index.html を表示専用に分離：共通部品 `mon()`、`data/*.json` の読み込み、4サイト照合レイド/DMax、GOパス実データ、生息地イラスト化。既存データ（イベント・タマゴ・生息地・GOパス）は実記事と照合しながら `data/` に移す。

## 9. AIに改修を頼むときのコツ
- 毎回「SPEC.md ＋ 対象1ファイル ＋ やりたいこと1つ」だけ渡す。長い会話を引き継がず、新しい会話で始める。
- 変更後は `python -m unittest discover -s tests -v` を実行して緑になることを確認する。
