/* データの読み込みと、画面用の形への変換。画面(app.js)はここで作られた変数だけを見る。
 * 読むファイル: data/events.json / event_details.json / news.json / meta.json / pokemon.json（自動更新）
 *               data/manual/*.json（旧データ・出典未確認）  data/gopass.json（任意・第2段階で追加）
 * どれかが読めなくても画面は動く（読めなかったファイル名は DATA_ERRORS に残し、画面上部に表示する）。 */
let ALL_EVENTS = [], RAID_DATA = {}, DMAX_9DB_DATA = {}, SEASON_EGGS = [], SEASON_BIOMES = [], NEWS_ITEMS = [];
let GOPASS = null, META = null;
const DATA_ERRORS = [];
const EVENT_ALIAS = {};   // 統合で消えたイベントID -> 残ったイベントID（ニュースのジャンプ先に使う）
const SITE_LABEL = { pokemapi: "ポケマピ", gamewith: "GameWith", "9db": "9DB", official: "公式" };
const DOW = ["日", "月", "火", "水", "木", "金", "土"];

async function loadJSON(path, fallback) {
  try {
    const r = await fetch(path + "?t=" + Date.now());
    if (!r.ok) throw new Error(r.status);
    return await r.json();
  } catch (e) {
    DATA_ERRORS.push(path);
    return fallback;
  }
}

// ---- 日時（データはすべて日本時間の文字列。端末の時差に左右されないよう +09:00 を付けて解釈する）----
function parseJst(iso, endOfDay) {
  if (!iso) return null;
  const s = iso.includes("T") ? iso + ":00+09:00" : iso + (endOfDay ? "T23:59:59+09:00" : "T00:00:00+09:00");
  const d = new Date(s);
  return isNaN(d) ? null : d;
}
function isoParts(iso) {
  const m = /^(\d{4})-(\d\d)-(\d\d)(?:T(\d\d):(\d\d))?$/.exec(iso || "");
  return m ? { y: +m[1], mo: +m[2], d: +m[3], hh: m[4], mm: m[5] } : null;
}
function fmtIso(iso) {
  const p = isoParts(iso);
  if (!p) return iso || "";
  const dow = DOW[new Date(Date.UTC(p.y, p.mo - 1, p.d)).getUTCDay()];
  return `${p.mo}/${p.d}(${dow})` + (p.hh ? ` ${+p.hh}:${p.mm}` : "");
}
function fmtRange(ev) {
  if (ev._long) return `${fmtIso(ev.start)} 〜 終了日未定（長期）`;
  return `${fmtIso(ev.start)} 〜 ${fmtIso(ev.end)}`;
}

// ---- 並び替え・重複除去の補助 ----
// 比較用に、記号・絵文字・「2026年」「11月」などの年月表記を除いた形にする（表記ゆれで別イベント扱いになるのを防ぐ）
const normTitle = t => String(t || "").replace(/[\p{Extended_Pictographic}\uFE0F]/gu, "")
  .replace(/[0-9０-９]+\s*(?:年|月|日)?/g, "").replace(/[\s\u3000・、。：:()（）「」『』【】～〜~!！?？&＆\-ー]/g, "").toLowerCase();
const normName = n => String(n || "").replace(/[\s\u3000]/g, "");
const isPassTitle = t => /^(?:[\p{Extended_Pictographic}\uFE0F\s]*)GOパス/u.test(String(t || ""));
function sameTitle(a, b) {
  if (isPassTitle(a) !== isPassTitle(b)) return false;   // GOパスは本体イベントとは別のものとして扱う
  const x = normTitle(a), y = normTitle(b);
  if (!x || !y) return false;
  if (x === y) return true;
  const [s, l] = x.length <= y.length ? [x, y] : [y, x];
  return s.length >= 6 && l.includes(s);
}
function overlaps(a, b) {
  const slack = 3 * 864e5;
  return a._s - slack <= b._e && b._s - slack <= a._e;
}
function uniqBy(list, keyfn) {
  const seen = new Set(), out = [];
  (list || []).forEach(x => { const k = keyfn(x); if (!seen.has(k)) { seen.add(k); out.push(x); } });
  return out;
}
function mergeSources(a, b) {
  return uniqBy([...(a || []), ...(b || [])], s => s.url);
}

// ---- レイド/DMaxの対策データとの紐づけ（名前の一致のみ。一致しなければリンクを出さない）----
function findTarget(name) {
  const n = normName(name);
  if (n.length < 3) return {};
  for (const [k, d] of Object.entries(DMAX_9DB_DATA)) {
    const dn = normName(d.name);
    if (dn.includes(n) || n.includes(dn)) return { targetKey: k, isDmax: true };
  }
  for (const [k, r] of Object.entries(RAID_DATA)) {
    const rn = normName(r.name);
    if (rn.includes(n) || n.includes(rn)) return { targetKey: k, isDmax: false };
  }
  return {};
}

// ---- 手書き(旧)データのイベント -> 画面用 ----
function adaptLegacy(ev) {
  const Y = 2026;
  return Object.assign({}, ev, {
    _s: new Date(Y, ev.month - 1, ev.startDay, 0, 0, 0),
    _e: new Date(Y, (ev.endMonth || ev.month) - 1, ev.endDay, 23, 59, 59),
    dateText: String(ev.dateText || "").replace(/\s*\[(?:終了|現在出現中|開催中|開催予定)\]/g, ""),
    sources: [], auto: false, eggs: [], surpriseBox: null,
  });
}

// ---- 手書き(旧)データのレイド/マックスバトル：開催期間(_s/_e)と表示用の期間文字を付ける ----
function withPeriod(b) {
  const Y = 2026;
  b._s = new Date(Y, b.month - 1, b.startDay, 0, 0, 0);
  b._e = new Date(Y, (b.endMonth || b.month) - 1, b.endDay, 23, 59, 59);
  const em = b.endMonth || b.month;
  b.periodText = (b.startDay === b.endDay && em === b.month) ? `${b.month}/${b.startDay}` : `${b.month}/${b.startDay}〜${em}/${b.endDay}`;
  return b;
}

// ---- 自動取得のイベント -> 画面用 ----
const PLACEHOLDER_RE = /詳細不明|内容不明|不明$|ぴったり|を含むイベント|^イベント限定(?:タスク|リサーチ)?$/;
const isPlaceholderTask = t => !t || PLACEHOLDER_RE.test(String(t.task || "")) || !String(t.task || "").trim() ||
  (t.rewards || []).some(r => PLACEHOLDER_RE.test(String(r.name || "")));

function adaptAuto(ev, det) {
  det = det || {};
  const s = parseJst(ev.start, false), e = parseJst(ev.end, true);
  if (!s || !e || e < s) return null;
  const long = (e - s) > 400 * 864e5;
  const mapMon = m => ({ dex: m.dex, name: m.name, shiny: !!m.shiny, note: [m.tier, m.rarity, m.distance, m.note].filter(Boolean).join(" ") });
  const sb = det.surprise_box;
  const ev2 = {
    id: ev.id, title: esc(ev.title), category: ev.category, barClass: "bar-" + ev.category,
    _s: s, _e: e, _long: long, start: ev.start, end: ev.end,
    month: s.getMonth() + 1, startDay: s.getDate(), endDay: e.getDate(),
    hasPaid: !!ev.hasPaid, summary: esc(ev.summary || ""),
    freeFeatures: (ev.freeFeatures || []).map(esc), paidFeatures: (ev.paidFeatures || []).map(esc),
    wilds: (det.wilds || []).map(mapMon),
    raids: (det.raids || []).map(m => Object.assign(mapMon(m), findTarget(m.name))),
    eggs: (det.eggs || []).map(mapMon),
    surpriseBox: sb && ((sb.pokemon || []).length || (sb.items || []).length)
      ? { pokemon: (sb.pokemon || []).map(mapMon), items: sb.items || [] } : null,
    fieldResearches: (det.field_research || []).filter(t => !isPlaceholderTask(t)), tasks: (det.time_challenge || []).filter(t => !isPlaceholderTask(t)),
    sources: mergeSources(ev.sources, [...(det.wilds || []), ...(det.field_research || [])].flatMap(x => x.sources || [])),
    auto: true, updatedAt: det.updated_at || null,
  };
  ev2.dateText = ev.dateText ? esc(ev.dateText) : fmtRange(ev2);
  if (det.schedule && det.schedule.start && det.schedule.end) {   // 日程変更が検出されていれば、新しい日程を使う
    const ns = parseJst(det.schedule.start, false), ne = parseJst(det.schedule.end, true);
    if (ns && ne && ne >= ns) {
      Object.assign(ev2, { _s: ns, _e: ne, start: det.schedule.start, end: det.schedule.end, month: ns.getMonth() + 1, startDay: ns.getDate(), endDay: ne.getDate() });
      ev2.dateText = fmtRange(ev2) + "（日程更新）";
    }
  }
  return ev2;
}

// 同じイベントが別名・別記事から登録されていた場合に1つにまとめる
function mergeInto(base, add) {
  EVENT_ALIAS[add.id] = base.id;
  // 手書き(旧)データと自動取得データが重なる場合は、日程は自動取得（記事由来）を正とする
  if (!base.auto && add.auto) {
    Object.assign(base, { _s: add._s, _e: add._e, _long: add._long, start: add.start, end: add.end, month: add.month, startDay: add.startDay, endDay: add.endDay, dateText: add.dateText });
  }
  base.sources = mergeSources(base.sources, add.sources);
  base.wilds = uniqBy([...(base.wilds || []), ...(add.wilds || [])], m => normName(m.name));
  base.raids = uniqBy([...(base.raids || []), ...(add.raids || [])], m => normName(m.name));
  base.eggs = uniqBy([...(base.eggs || []), ...(add.eggs || [])], m => normName(m.name) + (m.note || ""));
  base.fieldResearches = uniqBy([...(base.fieldResearches || []), ...(add.fieldResearches || [])], t => normName(t.task || t.rewardName));
  base.tasks = uniqBy([...(base.tasks || []), ...(add.tasks || [])], t => normName(t.task));
  if (!base.surpriseBox && add.surpriseBox) base.surpriseBox = add.surpriseBox;
  if (!base.auto && add.auto) base.auto = false;
  if ((!base.summary || base.summary.length < 8) && add.summary) base.summary = add.summary;
}

function buildEvents(manual, autoEvents, autoDetails) {
  // 手書き(旧)データは、終了日が今日より前のものを表示しない（推測の日付が残りやすいため。自動データは過去分も表示）
  const today0 = new Date(); today0.setHours(0, 0, 0, 0);
  const list = (manual || []).map(adaptLegacy).filter(e => e._e >= today0);
  const autos = Object.values(autoEvents || {})
    .map(ev => adaptAuto(ev, (autoDetails || {})[ev.id]))
    .filter(Boolean)
    .sort((a, b) => a._s - b._s);
  // 「レイドアワー：○○」は独立のイベントにせず、同じボスのレイドの無料欄に書き足す（同じボスのレイドが無ければ単独で残す）
  const bossCore = s => String(s).replace(/[(（].*?[)）]/g, "").replace(/[\s\u3000]/g, "");
  const rest = [];
  autos.forEach(a => {
    const m = /^レイドアワー[:：\s]*(.+)$/.exec(String(a.title).replace(/&amp;/g, "&"));
    if (m) {
      const boss = bossCore(m[1]);
      const host = boss.length >= 3 && list.find(h => h.category === "raid" && Math.abs(h._e - a._s) < 10 * 864e5 && (bossCore(h.title).includes(boss) || (h.raids || []).some(r => bossCore(r.name).includes(boss))));
      if (host) {
        const p = isoParts(a.start), q = isoParts(a.end);
        const when = p ? `${p.mo}/${p.d}(${DOW[new Date(Date.UTC(p.y, p.mo - 1, p.d)).getUTCDay()]}) ${p.hh ? +p.hh + ":" + p.mm : ""}${q && q.hh ? "〜" + (+q.hh) + ":" + q.mm : ""}` : "";
        host.freeFeatures = [...(host.freeFeatures || []), `${when}：${m[1]} レイドアワー`];
        EVENT_ALIAS[a.id] = host.id;
        return;
      }
    }
    rest.push(a);
  });
  rest.forEach(a => {
    const hit = list.find(b => sameTitle(b.title, a.title) && overlaps(b, a));
    if (hit) mergeInto(hit, a); else list.push(a);
  });
  list.sort((a, b) => a._s - b._s || a._e - b._e);
  return list;
}

function buildNews(items) {
  return (items || []).map(n => Object.assign({}, n, {
    title: esc(n.title), details: esc(n.details || ""),
    targetId: EVENT_ALIAS[n.targetId] || n.targetId || "",
  })).sort((a, b) => String(b.date).localeCompare(String(a.date)));
}

async function loadAll() {
  const [mEv, mRaid, mDmax, mSeason, aEv, aDet, aNews, poke, meta, gopass] = await Promise.all([
    loadJSON("data/manual/events.json", { events: [] }),
    loadJSON("data/manual/raids.json", { raids: {} }),
    loadJSON("data/manual/dmax.json", { dmax: {} }),
    loadJSON("data/manual/season.json", { eggs: [], biomes: [] }),
    loadJSON("data/events.json", { events: {} }),
    loadJSON("data/event_details.json", { events: {} }),
    loadJSON("data/news.json", { items: [] }),
    loadJSON("data/pokemon.json", { names: {} }),
    loadJSON("data/meta.json", null),
    loadJSON("data/gopass.json", null),
  ]);
  // gopass.json は任意（まだ無い場合は 404 になるので、エラー表示の対象にしない）
  if (!gopass) { const i = DATA_ERRORS.indexOf("data/gopass.json"); if (i >= 0) DATA_ERRORS.splice(i, 1); }
  RAID_DATA = mRaid.raids || {};
  DMAX_9DB_DATA = mDmax.dmax || {};
  Object.values(RAID_DATA).forEach(withPeriod);
  Object.values(DMAX_9DB_DATA).forEach(withPeriod);
  SEASON_EGGS = mSeason.eggs || [];
  SEASON_BIOMES = mSeason.biomes || [];
  MON.learnNames(poke.names);
  MON.learnFrom([mEv, mRaid, mDmax, mSeason, aDet]);
  ALL_EVENTS = buildEvents(mEv.events, aEv.events, aDet.events);
  NEWS_ITEMS = buildNews(aNews.items);
  GOPASS = gopass;
  META = meta;
}
