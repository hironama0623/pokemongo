/* 画面の描画。データは data.js が用意した変数（ALL_EVENTS 等）だけを読む。
 * ポケモン名は必ず mon() / MON.monChips() を通す（イラスト付きの共通表示）。 */

// ---- 開催状態（日時はすべて data.js が作った _s/_e を使う）----
const isEventPast = ev => ev._e < Date.now();
const isEventActive = ev => ev._s <= Date.now() && ev._e >= Date.now();
const isEventFuture = ev => ev._s > Date.now();

const CAT_LABEL = { main: "メイン", cd: "コミュニティ・デイ", raid: "レイド", dmax: "マックスバトル", collab: "コラボ・GOパス" };

function sourceChips(sources) {
  if (!sources || !sources.length) {
    return `<span class="text-[10px] bg-slate-100 text-slate-500 border border-slate-300 px-1.5 py-0.5 rounded font-bold" title="旧index.htmlに手書きで入っていた内容で、出典が確認できていません">旧データ・出典未確認</span>`;
  }
  return sources.map(s => `<a href="${esc(s.url)}" target="_blank" rel="noopener" class="text-[10px] bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 px-1.5 py-0.5 rounded font-bold">${esc(SITE_LABEL[s.site] || s.site)}${s.article_updated ? " " + esc(String(s.article_updated).slice(5, 10).replace("-", "/")) : ""} ↗</a>`).join(" ");
}

function monTile(m, size) {
  return `<div class="bg-slate-50 border border-slate-200 p-1.5 rounded-lg overflow-hidden">${mon(m.name, { dex: m.dex, shiny: m.shiny, size: size || 32 })}${m.note ? `<div class="text-[10px] text-slate-500 truncate">${esc(m.note)}</div>` : ""}</div>`;
}

function rewardChips(t) {
  const rs = Array.isArray(t.rewards) ? t.rewards : (t.rewardName ? [{ name: t.rewardName, dex: t.rewardDex, shiny: t.shiny }] : []);
  return rs.map(r => `<span class="inline-flex bg-amber-50/70 px-2 py-1 rounded border border-amber-200 text-[11px] font-extrabold text-amber-800">${mon(r.name, { dex: r.dex, shiny: r.shiny, size: 26 })}</span>`).join(" ");
}

function eventIconDex(ev) {
  if (ev.barIconDex) return { dex: ev.barIconDex, name: ev.title };
  for (const m of [...(ev.raids || []), ...(ev.wilds || [])]) {
    const d = MON.dexOf(m.name, m.dex);
    if (d != null) return { dex: d, name: m.name };
  }
  return null;
}

/** イベント1件の詳細カード（<details>）。idPrefix は同じイベントを別タブにも出すときの ID 衝突回避用 */
function buildEventCard(ev, open, idPrefix) {
  const details = document.createElement("details");
  details.className = "bg-white border border-slate-200 rounded-xl overflow-hidden transition group shadow-sm";
  details.id = (idPrefix || "") + ev.id;
  details.open = !!open;
  const hasFree = ev.freeFeatures && ev.freeFeatures.length > 0;
  const hasPaid = ev.paidFeatures && ev.paidFeatures.length > 0;
  const shortTitle = String(ev.title).replace(/[^\w぀-ゟ゠-ヿ一-龯]/g, "").slice(0, 10);
  const freeVsPaid = (hasFree || hasPaid) ? `<div class="grid grid-cols-1 ${hasFree && hasPaid ? "md:grid-cols-2" : ""} gap-2">
      ${hasFree ? `<div class="bg-emerald-50/70 border border-emerald-200 rounded-lg p-2.5"><div class="text-[11px] font-extrabold text-emerald-800 mb-1">🟢 【無料（全トレーナー共通）】でできること</div><ul class="text-[11px] text-slate-700 space-y-0.5 list-disc list-inside">${ev.freeFeatures.map(f => `<li>${f}</li>`).join("")}</ul></div>` : ""}
      ${hasPaid ? `<div class="bg-amber-50/70 border border-amber-300 rounded-lg p-2.5"><div class="text-[11px] font-extrabold text-amber-900 mb-1">💎 【有料チケット・課金】で追加される要素</div><ul class="text-[11px] text-slate-700 space-y-0.5 list-disc list-inside">${ev.paidFeatures.map(p => `<li>${p}</li>`).join("")}</ul></div>` : ""}</div>` : "";
  const wilds = ev.wilds && ev.wilds.length ? `<div><div class="text-[11px] font-bold text-emerald-700 mb-1">🌿 【野生・イベント出現ポケモン一覧】</div><div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5">${ev.wilds.map(w => monTile(w, 32)).join("")}</div></div>` : "";
  const eggs = ev.eggs && ev.eggs.length ? `<div><div class="text-[11px] font-bold text-amber-700 mb-1">🥚 【タマゴから生まれるポケモン】</div><div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5">${ev.eggs.map(w => monTile(w, 32)).join("")}</div></div>` : "";
  const sb = ev.surpriseBox ? `<div class="bg-pink-50/50 border border-pink-200 rounded-lg p-2.5"><div class="text-[11px] font-extrabold text-pink-800 mb-1.5">🎁 【サプライズボックスの中身】</div>
      ${ev.surpriseBox.pokemon.length ? `<div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 mb-1.5">${ev.surpriseBox.pokemon.map(w => monTile(w, 32)).join("")}</div>` : ""}
      ${ev.surpriseBox.items.length ? `<div class="text-[11px] text-slate-700">${ev.surpriseBox.items.map(i => `<span class="inline-block bg-white border border-pink-200 rounded px-1.5 py-0.5 mr-1 mb-1">${esc(i.name)}${i.qty ? " ×" + esc(i.qty) : ""}</span>`).join("")}</div>` : ""}</div>` : "";
  const raids = ev.raids && ev.raids.length ? `<div><div class="text-[11px] font-bold text-rose-700 mb-1">⚔️ 【レイド・マックスバトル出現】(「対策」をタップで対策データへジャンプ / スワイプで戻れます)</div><div class="grid grid-cols-1 sm:grid-cols-3 gap-1.5">
      ${ev.raids.map(r => `<div ${r.targetKey ? `onclick="jumpToCounterTarget('${esc(r.targetKey)}', ${!!r.isDmax}, '${esc(ev.id)}', '${esc(shortTitle)}へ戻る')"` : ""} class="bg-slate-50 border border-slate-200 ${r.targetKey ? "hover:border-sky-500 cursor-pointer" : ""} p-2 rounded-lg flex items-center justify-between transition"><div class="overflow-hidden">${mon(r.name, { dex: r.dex, shiny: r.shiny, size: 36 })}${r.note ? `<div class="text-[10px] text-slate-500 truncate">${esc(r.note)}</div>` : ""}</div>${r.targetKey ? `<span class="text-[10px] bg-sky-600 text-white font-bold px-2 py-0.5 rounded flex-shrink-0">対策 ↗</span>` : ""}</div>`).join("")}</div></div>` : "";
  let fr = "";
  if (ev.fieldResearches && ev.fieldResearches.length) {
    fr = `<div class="bg-teal-50/40 border border-teal-200 rounded-lg p-2.5"><div class="flex flex-wrap items-center justify-between gap-1 mb-1.5"><div class="text-[11px] font-extrabold text-teal-800">🔍 【イベント限定フィールドリサーチ一覧 (ポケストップ入手)】</div><span class="text-[10px] text-teal-700 bg-teal-100/80 px-2 py-0.5 rounded font-bold">判明分は自動で追加されます</span></div>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">${ev.fieldResearches.map(t => `<div class="bg-white border border-teal-200/80 p-2 rounded-lg flex items-center justify-between gap-2 shadow-sm"><div class="min-w-0"><div class="text-[11px] text-slate-800 font-bold">${esc(t.task)}</div>${t.note ? `<div class="text-[10px] text-slate-500">${esc(t.note)}</div>` : ""}</div><div class="flex flex-wrap justify-end gap-1">${rewardChips(t)}</div></div>`).join("")}</div></div>`;
  } else if (ev.hasFieldResearchPending) {
    fr = `<div class="bg-teal-50/30 border border-dashed border-teal-300 rounded-lg p-2 text-[11px] text-teal-800">🔍 <strong>イベント限定フィールドリサーチ：</strong>イベント開始後、攻略サイトでタスク詳細が判明次第、自動でここに一覧表示されます。</div>`;
  }
  const tasks = ev.tasks && ev.tasks.length ? `<div><div class="text-[11px] font-bold text-sky-700 mb-1">⏱️ 【タイムチャレンジ・特別報酬・イベントギミック】</div><div class="grid grid-cols-1 sm:grid-cols-2 gap-1.5">${ev.tasks.map(t => `<div class="bg-slate-50 border border-slate-200 p-2 rounded-lg flex items-center justify-between gap-2"><span class="text-[11px] text-slate-700 font-medium">${esc(t.task)}</span><div class="flex flex-wrap justify-end gap-1">${rewardChips(t)}</div></div>`).join("")}</div></div>` : "";
  const badge = ev.hasPaid ? `<span class="text-[10px] bg-amber-50 text-amber-800 border border-amber-300 px-1.5 py-0.5 rounded font-bold">🟢無料 ＆ 💎有料チケットあり</span>` : `<span class="text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-300 px-1.5 py-0.5 rounded font-bold">🟢完全無料</span>`;
  const icon = eventIconDex(ev);
  details.innerHTML = `
    <summary class="p-3.5 cursor-pointer flex items-center justify-between gap-2 hover:bg-slate-50 transition">
      <div class="flex items-center gap-2.5">
        ${icon ? `<img src="${getPokeImg(icon.dex, icon.name)}" alt="" loading="lazy" class="w-9 h-9 object-contain flex-shrink-0">` : ""}
        <div><div class="flex flex-wrap items-center gap-2"><span class="text-[11px] text-sky-600 font-bold">${ev.dateText}</span>${badge}</div>
        <h3 class="text-sm font-extrabold text-slate-900 mt-0.5">${ev.title}</h3></div>
      </div>
      <div class="flex items-center gap-2 flex-shrink-0">
        <button onclick="hideEvent('${esc(ev.id)}', event)" class="text-[11px] text-slate-500 hover:text-rose-600 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200 font-bold">👁 非表示</button>
        <span class="text-slate-400 group-open:rotate-180 transition-transform text-xs">▼</span>
      </div>
    </summary>
    <div class="p-3.5 pt-0 border-t border-slate-100 space-y-3 mt-1 text-xs">
      ${ev.summary ? `<div class="text-slate-700 leading-relaxed bg-slate-50 p-2.5 rounded-lg border border-slate-200">${ev.summary}</div>` : ""}
      ${freeVsPaid}${wilds}${eggs}${sb}${raids}${fr}${tasks}
      <div class="flex flex-wrap items-center gap-1 pt-1 border-t border-slate-100"><span class="text-[10px] text-slate-400">出典:</span>${sourceChips(ev.sources)}</div>
    </div>`;
  return details;
}

function renderEventAccordions() {
  const container = document.getElementById("eventsAccordionContainer");
  const archive = document.getElementById("archivedEventsList");
  container.innerHTML = "";
  if (archive) archive.innerHTML = "";
  const active = [], past = [];
  ALL_EVENTS.forEach(ev => {
    if (hiddenEventIds.has(ev.id)) return;
    if (currentCategoryFilter !== "all" && ev.category !== currentCategoryFilter) return;
    (isEventPast(ev) ? past : active).push(ev);
  });
  // 開催中 → これから開催 の順（終わりが近い順）。長期のものは後ろ
  active.sort((a, b) => (a._long - b._long) || (isEventActive(b) - isEventActive(a)) || (isEventActive(a) ? a._e - b._e : a._s - b._s));
  active.forEach((ev, i) => container.appendChild(buildEventCard(ev, i < 3 || ["ev-halloween-p1", "ev-supermega-chandelure", "ev-halloween-p2", "ev-wildarea-2026"].includes(ev.id))));
  if (!active.length) container.innerHTML = `<div class="text-xs text-slate-500 p-3 bg-white border border-slate-200 rounded-xl">表示できるイベントがありません。</div>`;
  if (archive) {
    past.sort((a, b) => b._e - a._e).forEach(ev => {
      const row = document.createElement("div");
      row.className = "flex flex-wrap items-center justify-between gap-1 border-b border-slate-100 pb-1";
      row.innerHTML = `<span><span class="text-slate-400">${ev.dateText}</span> <strong class="text-slate-700">${ev.title}</strong></span><span>${sourceChips(ev.sources)}</span>`;
      archive.appendChild(row);
    });
  }
}

function renderTodaySection() {
  const label = document.getElementById("todayHeaderDateLabel");
  if (label) label.textContent = `${todayMonth}月${todayDate}日(${todayDow})`;
  const list = document.getElementById("todayEventsList");
  if (!list) return;
  const active = ALL_EVENTS.filter(ev => !hiddenEventIds.has(ev.id) && isEventActive(ev))
    .sort((a, b) => (a._long - b._long) || (a._e - b._e));
  list.innerHTML = active.length ? "" : `<li class="p-2 text-slate-500">本日開催中の特別イベントはありません</li>`;
  active.slice(0, 6).forEach(ev => {
    const endsToday = new Date(ev._e).toDateString() === new Date().toDateString();
    const when = endsToday ? "本日終了" : (ev._long ? "長期開催中" : `〜${ev._e.getMonth() + 1}/${ev._e.getDate()}まで`);
    const li = document.createElement("li");
    li.className = "flex items-start gap-2 p-2 rounded-lg border " + (endsToday ? "bg-rose-50/50 border-rose-100" : "bg-slate-50 border-slate-200");
    li.innerHTML = `<span class="${endsToday ? "text-amber-600" : "text-emerald-600"} font-bold flex-shrink-0 text-[11px]">${when}</span>
      <div><strong class="text-sky-700 cursor-pointer hover:underline text-xs" onclick="scrollToEventCard('${esc(ev.id)}')">${ev.title}</strong>
      <p class="text-[11px] text-slate-500 line-clamp-2">${ev.summary || ""}</p></div>`;
    list.appendChild(li);
  });
}

function renderNewsSection() {
  const box = document.getElementById("newsItemsContainer");
  box.innerHTML = "";
  if (!NEWS_ITEMS.length) { box.innerHTML = `<div class="text-slate-400 py-2">ニュースはまだありません（新しい情報が見つかると自動で追加されます）。</div>`; return; }
  const visible = NEWS_ITEMS.filter(n => !readNewsIds.has(n.id));
  if (!visible.length) { box.innerHTML = `<div class="text-slate-400 py-2">すべてのニュースを既読にしました。</div>`; return; }
  const KIND = { new_event: ["新", "bg-rose-100 text-rose-700 border-rose-200"], event_update: ["追加", "bg-emerald-100 text-emerald-700 border-emerald-200"], schedule_changed: ["日程", "bg-amber-100 text-amber-800 border-amber-200"] };
  visible.forEach(n => {
    const detailId = `news-detail-${n.id}`;
    const dateLabel = n.date_label || (n.date ? n.date.slice(5).replace("-", "/") : "");
    const k = KIND[n.kind];
    const item = document.createElement("div");
    item.className = "bg-slate-50 border border-slate-200 rounded-lg overflow-hidden transition";
    item.innerHTML = `<div class="flex items-center justify-between gap-2 p-2">
      <div class="cursor-pointer hover:text-sky-700 transition flex items-center gap-1.5 flex-1 min-w-0" onclick="handleNewsClick('${esc(n.targetId || "")}', '${detailId}')">
        <span class="text-[11px] font-bold text-sky-700 bg-sky-100 border border-sky-200 px-1.5 py-0.5 rounded flex-shrink-0">[${esc(dateLabel)}]</span>
        ${k ? `<span class="text-[10px] font-bold border px-1 py-0.5 rounded flex-shrink-0 ${k[1]}">${k[0]}</span>` : ""}
        <span class="font-bold text-slate-800 truncate" title="${n.title}">${n.title}</span></div>
      <button onclick="markNewsRead('${esc(n.id)}')" class="text-[11px] text-slate-400 hover:text-emerald-600 font-bold px-1" title="既読にして非表示">✓</button></div>
      <div id="${detailId}" class="hidden px-2.5 pb-2 text-[11px] text-slate-600 leading-relaxed">${n.details}<div class="mt-1 flex flex-wrap gap-1">${sourceChips(n.sources)}</div></div>`;
    box.appendChild(item);
  });
}

function renderGanttTimeline() {
  const headerRow = document.getElementById("ganttHeaderRow"), bgGrid = document.getElementById("ganttBgGrid"), tracks = document.getElementById("ganttTracksContainer");
  tracks.querySelectorAll(".gantt-event-row").forEach(r => r.remove());
  headerRow.innerHTML = ""; bgGrid.innerHTML = "";
  const Y = todayYear, M = currentGanttMonth;
  const daysInMonth = new Date(Y, M, 0).getDate();
  const startDay = (M === todayMonth) ? todayDate : 1;
  const totalDays = daysInMonth - startDay + 1;
  const tpl = `repeat(${totalDays}, minmax(56px, 1fr))`;
  headerRow.style.gridTemplateColumns = tpl; bgGrid.style.gridTemplateColumns = tpl;
  for (let d = startDay; d <= daysInMonth; d++) {
    const dow = new Date(Y, M - 1, d).getDay();
    const isToday = (M === todayMonth && d === todayDate);
    const col = dow === 6 ? "text-sky-600" : (dow === 0 ? "text-rose-600" : "text-slate-600");
    const cell = document.createElement("div");
    cell.className = `py-1.5 border-r border-slate-200 ${isToday ? "bg-sky-50 text-sky-800 border-b-2 border-b-sky-500 font-black" : ""}`;
    cell.innerHTML = `<div class="text-[10px] ${col}">${DOW[dow]}</div><div class="text-[11px] font-bold">${M}/${d}</div>`;
    headerRow.appendChild(cell);
    const bg = document.createElement("div");
    bg.className = `border-r border-slate-100 ${isToday ? "bg-sky-50/40" : ""}`;
    bgGrid.appendChild(bg);
  }
  const dispStart = new Date(Y, M - 1, startDay, 0, 0, 0), dispEnd = new Date(Y, M - 1, daysInMonth, 23, 59, 59);
  ALL_EVENTS.filter(ev => !hiddenEventIds.has(ev.id) && (currentCategoryFilter === "all" || ev.category === currentCategoryFilter) && ev._e >= dispStart && ev._s <= dispEnd)
    .forEach(ev => {
      const s = ev._s < dispStart ? startDay : ev._s.getDate();
      const e = ev._e > dispEnd ? daysInMonth : ev._e.getDate();
      const row = document.createElement("div");
      row.className = "gantt-event-row relative h-8 flex items-center";
      row.style.display = "grid"; row.style.gridTemplateColumns = tpl;
      const bar = document.createElement("div");
      bar.className = `${ev.barClass} h-7 rounded-md px-1.5 text-[11px] font-bold flex items-center justify-between cursor-pointer shadow-sm hover:brightness-95 transition z-10`;
      bar.style.gridColumn = `${s - startDay + 1} / span ${e - s + 1}`;
      bar.onclick = () => scrollToEventCard(ev.id);
      const icon = eventIconDex(ev);
      bar.innerHTML = `<div class="gantt-sticky-label">${icon ? `<img src="${getPokeImg(icon.dex, icon.name)}" alt="" class="w-5 h-5 object-contain flex-shrink-0 drop-shadow-sm bg-white/70 rounded-full p-0.5">` : ""}<span class="truncate">${ev.title}</span></div>
        <button onclick="hideEvent('${esc(ev.id)}', event)" class="text-[10px] opacity-70 hover:opacity-100 hover:bg-rose-500 hover:text-white bg-white/70 px-1 py-0.5 rounded leading-none flex-shrink-0 ml-1" title="非表示">✕</button>`;
      row.appendChild(bar);
      tracks.appendChild(row);
    });
}

function renderSeason24Tab() {
  const eggs = document.getElementById("seasonEggGrid"), biome = document.getElementById("seasonBiomeGrid");
  eggs.innerHTML = SEASON_EGGS.map(g => `<div class="bg-slate-50 border border-slate-200 rounded-lg p-2"><div class="font-bold text-slate-700 mb-1">${esc(g.title)}</div><div class="flex flex-wrap gap-x-2 gap-y-1">${g.list.map(m => mon(m.n, { dex: m.d, size: 28 })).join("")}</div></div>`).join("");
  biome.innerHTML = SEASON_BIOMES.map(b => `<div class="bg-slate-50 border border-slate-200 rounded-lg p-2.5"><div class="font-bold text-slate-800 mb-1.5">${esc(b.title)}</div><div class="leading-relaxed">${MON.monChips(b.desc, { size: 24 })}</div></div>`).join("");
}

function renderGoPassTab() {
  const cur = document.getElementById("goPassCurrentList"), fut = document.getElementById("goPassFutureList");
  const isPass = ev => /^GOパス/.test(String(ev.title)) || /go-?pass/i.test(ev.id);
  const passes = ALL_EVENTS.filter(ev => isPass(ev) && !isEventPast(ev) && !hiddenEventIds.has(ev.id));
  const fill = (el, list) => {
    el.innerHTML = "";
    if (!list.length) el.innerHTML = `<div class="text-xs text-slate-500 p-3 bg-white border border-slate-200 rounded-xl">該当するGOパスの情報はまだ見つかっていません（公式発表後に自動で追加されます）。</div>`;
    list.forEach((ev, i) => el.appendChild(buildEventCard(ev, i === 0, "gp-")));
  };
  fill(cur, passes.filter(isEventActive));
  fill(fut, passes.filter(isEventFuture));
  const box = document.getElementById("goPassRankArea");
  if (!GOPASS || !(GOPASS.passes || []).length) {
    box.innerHTML = `<div class="bg-white border border-dashed border-slate-300 rounded-xl p-3 text-xs text-slate-600">📋 <strong>ランク別の報酬表：</strong>出典（攻略サイト・公式）に載っているランクだけを表示する方針です。現在、ランク別の報酬データは取り込み前のため、表は表示していません（以前の100ランク表は、出典のない推測値を含んでいたため廃止しました）。</div>`;
    return;
  }
  box.innerHTML = GOPASS.passes.map(p => `<div class="bg-white border border-slate-200 rounded-xl overflow-hidden"><div class="p-2.5 bg-slate-50 border-b border-slate-200 text-xs font-extrabold">${esc(p.title)}</div>
    <div class="max-h-[480px] overflow-y-auto"><table class="w-full text-xs"><thead class="bg-slate-100 sticky top-0"><tr><th class="p-2 w-14">ランク</th><th class="p-2 text-left">🟢 無料</th><th class="p-2 text-left">💎 デラックス</th><th class="p-2 text-left w-20">出典</th></tr></thead><tbody class="divide-y divide-slate-100">
    ${(p.ranks || []).map(r => `<tr><td class="p-2 text-center font-black text-slate-600">${esc(r.rank)}</td><td class="p-2">${esc(r.free || "")}</td><td class="p-2 text-amber-900">${esc(r.deluxe || "")}</td><td class="p-2">${sourceChips(r.sources)}</td></tr>`).join("")}</tbody></table></div></div>`).join("");
}

function renderStatusBar() {
  const el = document.getElementById("autoUpdateTimestamp");
  const fmt = iso => { const d = new Date(iso); return isNaN(d) ? "" : `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  if (el && META && META.last_success_at) {
    let t = "最終自動更新: " + fmt(META.last_success_at);
    if (META.last_run_status === "failed") t += " ⚠ 直近の更新に失敗（表示は前回のデータ）";
    else if (META.last_run_status === "partial") t += " ※一部の記事は解析待ち";
    el.textContent = t;
  }
  const main = document.querySelector("main");
  let notes = "";
  if (DATA_ERRORS.length) notes += `<div class="text-[11px] bg-rose-50 border border-rose-300 text-rose-800 rounded-lg p-2">⚠ 一部のデータを読み込めませんでした: ${DATA_ERRORS.map(esc).join("、")}</div>`;
  const wrap = document.createElement("div");
  wrap.id = "dataNotes"; wrap.className = "space-y-2 mb-3"; wrap.innerHTML = notes;
  if (notes) main.insertBefore(wrap, main.firstChild);
  const battles = document.getElementById("tabContentBattles");
  if (battles) {
    const n = document.createElement("div");
    n.className = "text-[11px] bg-amber-50 border border-amber-300 text-amber-900 rounded-lg p-2";
    n.innerHTML = "⚠ このタブの対策ポケモン・数値（DPS/TDO等）は旧データで、出典が確認できていません。4サイトで照合した出典付きのデータに置き換え予定です。";
    battles.insertBefore(n, battles.firstChild);
  }
}

window.onload = async function () {
  await loadAll();
  renderStatusBar();
  renderSeason24Tab();
  renderTodaySection();
  renderNewsSection();
  changeGanttMonth(currentGanttMonth);
  renderEventAccordions();
  renderGoPassTab();
};
