/* ポケモン名＋イラストの共通部品。画面のすべての「ポケモン名」はここを通す（SPEC.md 画面章）。
 * 図鑑番号の解決順: ①データに dex があればそれ ②名前の完全一致 ③名前に含まれる種名の最長一致。
 * 解決できない名前は画像なし（文字のみ）。画像が読み込めない場合も文字だけが残る。 */
(function () {
  const PREFIX = /^(メガ|ダイマックス|キョダイマックス|キョダイ|ゲンシ|シャドウ|アローラ|ガラル|ヒスイ|パルデア|[GAHP])/;
  const DEX = new Map();    // 正規化した名前 -> 図鑑番号/フォームID
  const BASES = new Map();  // 種名（接頭辞・括弧を除いたもの） -> 図鑑番号
  const norm = s => String(s || "").replace(/[\s　・･]/g, "").replace(/（/g, "(").replace(/）/g, ")");
  const core = n => n.replace(/\(.*?\)/g, "");

  function learn(name, dex) {
    if (!name || !Number.isFinite(dex)) return;
    const n = norm(name);
    if (!DEX.has(n)) DEX.set(n, dex);
    if (dex < 10000) {
      const b = core(n).replace(PREFIX, "");
      if (b.length >= 2 && !BASES.has(b)) BASES.set(b, dex);
    }
  }

  // 任意のデータ構造から {name,dex} / {rewardName,rewardDex} / {n,d} を拾って辞書に学習させる
  function learnFrom(obj, depth = 0) {
    if (!obj || typeof obj !== "object" || depth > 8) return;
    if (Array.isArray(obj)) { obj.forEach(x => learnFrom(x, depth + 1)); return; }
    if (typeof obj.name === "string" && Number.isFinite(obj.dex)) learn(obj.name, obj.dex);
    if (typeof obj.rewardName === "string" && Number.isFinite(obj.rewardDex)) learn(obj.rewardName, obj.rewardDex);
    if (typeof obj.n === "string" && Number.isFinite(obj.d)) learn(obj.n, obj.d);
    for (const k of Object.keys(obj)) learnFrom(obj[k], depth + 1);
  }

  function learnNames(map) { Object.keys(map || {}).forEach(k => learn(k, Number(map[k]))); }

  function lookup(name) {
    const n = norm(name);
    if (!n) return null;
    if (DEX.has(n)) return DEX.get(n);
    const c = core(n);
    if (DEX.has(c)) return DEX.get(c);
    if (BASES.has(c)) return BASES.get(c);
    // 名前に含まれる種名を探す。入れ子の短い名前（ゴース⊂ゴースト）は除き、1種類に定まるときだけ採用
    if (c.length < 3) return null;
    let hits = [];
    for (const [b] of BASES) if (b.length >= 3 && c.includes(b)) hits.push(b);
    hits = hits.filter(h => !hits.some(o => o !== h && o.includes(h)));
    return hits.length === 1 ? BASES.get(hits[0]) : null;
  }

  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /** 図鑑番号（フォーム解決済み）。分からなければ null */
  function dexOf(name, dex) {
    const d = Number.isFinite(dex) ? dex : lookup(name);
    if (d == null) return null;
    return typeof resolveSpecialFormId === "function" ? resolveSpecialFormId(d, name) : d;
  }

  /** ポケモン名 + 小さなイラスト。opts: dex, shiny, note, size(px), cls */
  function mon(name, opts = {}) {
    const size = opts.size || 20;
    const d = dexOf(name, opts.dex);
    const img = d != null
      ? `<img src="${getPokeImg(d, name)}" alt="" loading="lazy" width="${size}" height="${size}" style="width:${size}px;height:${size}px" class="object-contain flex-shrink-0 inline-block align-middle">`
      : "";
    const note = opts.note ? `<span class="text-slate-500 text-[10px] ml-0.5">${esc(opts.note)}</span>` : "";
    return `<span class="mon inline-flex items-center gap-1 ${opts.cls || ""}">${img}<span class="mon-name">${esc(name)}${opts.shiny ? " ✨" : ""}</span>${note}</span>`;
  }

  /** 「A、B、C」形式の文章を、名前チップ（イラスト付き）の並びにする */
  function monChips(text, opts = {}) {
    const parts = String(text || "").split(/[、,，\/／]/).map(t => t.trim()).filter(Boolean);
    return parts.map(t => {
      const label = t.replace(/等$/, "").split(/[：:]/).pop().trim();
      const head = t.includes("：") || t.includes(":") ? t.split(/[：:]/)[0] + "：" : "";
      return (head ? `<span class="text-[10px] text-slate-400">${esc(head)}</span>` : "") +
        `<span class="inline-flex bg-slate-50 border border-slate-200 rounded-full pl-1 pr-2 py-0.5 mr-1 mb-1">${mon(label, { size: opts.size || 22 })}</span>`;
    }).join("");
  }

  // 画像が読み込めなかったときは画像だけ消して、名前の文字は残す
  document.addEventListener("error", e => {
    if (e.target && e.target.tagName === "IMG" && e.target.closest(".mon")) e.target.style.display = "none";
  }, true);

  window.MON = { learn, learnFrom, learnNames, lookup, dexOf, mon, monChips, esc };
  window.mon = mon;
  window.esc = esc;
})();
