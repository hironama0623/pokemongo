/* 旧 index.html から引き継いだ画面ロジック（タブ切替・戻る操作・スワイプ・レイド/DMax表示など）。
 * 描画の中心（イベント・ガント・ニュース・シーズン・GOパス）は render.js に移した。
 * データは data.js が用意する変数（RAID_DATA 等）を読むだけで、ここにデータは持たない。 */
  function resolveSpecialFormId(dexOrFormId, pokeName) {
    const id = Number(dexOrFormId) || 25;
    if (id >= 10000) return id;
    if (!pokeName) return id;
    const n = String(pokeName);
    if (n.includes("キョダイ")) {
      if (n.includes("フシギバナ") || id === 3) return 10195;
      if (n.includes("リザードン") || id === 6) return 10196;
      if (n.includes("カメックス") || id === 9) return 10197;
      if (n.includes("カイリキー") || id === 68) return 10201;
      if (n.includes("ゲンガー") || id === 94) return 10202;
      if (n.includes("ラプラス") || id === 131) return 10204;
      if (n.includes("カビゴン") || id === 143) return 10206;
      if (n.includes("メルメタル") || id === 809) return 10208;
      if (n.includes("ゴリランダー") || id === 812) return 10209;
      if (n.includes("エースバーン") || id === 815) return 10210;
      if (n.includes("インテレオン") || id === 818) return 10211;
      if (n.includes("アーマーガア") || id === 823) return 10212;
      if (n.includes("オーロンゲ") || id === 861) return 10222;
      if (n.includes("ジュラルドン") || id === 884) return 10225;
      if (n.includes("ウーラオス") || id === 892) return 10226;
    }
    if ((n.includes("ザシアン") || id === 888) && (n.includes("けん") || n.includes("王"))) return 10188;
    if ((n.includes("ザマゼンタ") || id === 889) && (n.includes("たて") || n.includes("王"))) return 10189;
    if ((n.includes("ネクロズマ") || id === 800) && (n.includes("たそがれ") || n.includes("日食"))) return 10155;
    if ((n.includes("ネクロズマ") || id === 800) && (n.includes("あかつき") || n.includes("月食"))) return 10156;
    if (n.includes("ブラックキュレム") || (id === 646 && n.includes("ブラック"))) return 10022;
    if (n.includes("ホワイトキュレム") || (id === 646 && n.includes("ホワイト"))) return 10023;
    if ((n.includes("ディアルガ") || id === 483) && n.includes("オリジン")) return 10245;
    if ((n.includes("パルキア") || id === 484) && n.includes("オリジン")) return 10246;
    if ((n.includes("ギラティナ") || id === 487) && n.includes("オリジン")) return 10007;
    if ((n.includes("ランドロス") || id === 645) && n.includes("れいじゅう")) return 10021;
    if ((n.includes("ヒヒダルマ") || id === 555) && n.includes("ガラル")) return 10177;
    if ((n.includes("ライチュウ") || id === 26) && n.includes("アローラ")) return 10100;
    if ((n.includes("キュウコン") || id === 38) && n.includes("アローラ")) return 10104;
    if (n.includes("メガ") || n.includes("ゲンシ")) {
      if (n.includes("リザードンX")) return 10034;
      if (n.includes("リザードン")) return 10035;
      if (n.includes("ゲンガー")) return 10038;
      if (n.includes("ギャラドス")) return 10041;
      if (n.includes("バンギラス")) return 10049;
      if (n.includes("サーナイト")) return 10051;
      if (n.includes("ジュペッタ")) return 10056;
      if (n.includes("ルカリオ")) return 10059;
      if (n.includes("ユキノオー")) return 10060;
      if (n.includes("ラグラージ")) return 10064;
      if (n.includes("ヤミラミ")) return 10066;
      if (n.includes("ディアンシー")) return 10075;
      if (n.includes("メタグロス")) return 10076;
      if (n.includes("カイオーガ")) return 10077;
      if (n.includes("グラードン")) return 10078;
      if (n.includes("レックウザ")) return 10079;
    }
    return id;
  }
  const getPokeImg = (dexOrFormId, pokeName = "") => {
    const resolvedId = resolveSpecialFormId(dexOrFormId, pokeName);
    return `https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/${resolvedId}.png`;
  };
  const TYPE_COLOR_MAP = {
    "ノーマル": "bg-slate-500",
    "ほのお": "bg-red-600",
    "みず": "bg-blue-600",
    "くさ": "bg-emerald-600",
    "でんき": "bg-amber-500",
    "こおり": "bg-sky-500",
    "かくとう": "bg-orange-600",
    "どく": "bg-fuchsia-700",
    "じめん": "bg-amber-700",
    "ひこう": "bg-indigo-400",
    "エスパー": "bg-pink-600",
    "むし": "bg-lime-600",
    "いわ": "bg-stone-600",
    "ゴースト": "bg-purple-700",
    "ドラゴン": "bg-indigo-700",
    "あく": "bg-stone-800",
    "はがね": "bg-slate-600",
    "フェアリー": "bg-pink-500"
  };
  const renderTypeBadges = (types) => (types || []).map(t => `<span class="${TYPE_COLOR_MAP[t] || 'bg-slate-600'} text-white text-[11px] font-bold px-2.5 py-0.5 rounded shadow-sm">${t}</span>`).join(" ");
  const now = new Date();
  const todayYear = now.getFullYear();
  const todayMonth = now.getMonth() + 1;
  const todayDate = now.getDate();
  const todayDow = ["日", "月", "火", "水", "木", "金", "土"][now.getDay()];

  let currentMainTab = "schedule";
  let currentBattleSub = "raids";
  let currentGanttRange = "recent";   // "recent"=今日から10日間 / "m0".."m2"=今月・来月・再来月
  let currentCategoryFilter = "all";
  let hiddenEventIds = new Set();
  let readNewsIds = new Set();
  let activeRaidKey = "palkia-normal";
  let activeDmax9dbKey = "dmax-sableye";
  let filterMega = false;
  let filterShadow = false;
  let raidSortMode = "dps";
  let navHistoryStack = [];

  function pushNavState(fromEventId, labelText) {
    navHistoryStack.push({
      mainTab: currentMainTab,
      battleSub: currentBattleSub,
      scrollY: window.scrollY,
      eventId: fromEventId || "",
      label: labelText || "元の画面に戻る"
    });
    try {
      history.pushState({
        pogoInternalNav: true
      }, "");
    } catch (e) {}
    updateBackButtonsUI();
  }

  function updateBackButtonsUI() {
    const floatBtn = document.getElementById("floatingBackBtn"),
      headerBtn = document.getElementById("headerBackBtn"),
      floatLabel = document.getElementById("floatingBackLabel");
    if (navHistoryStack.length > 0) {
      if (floatLabel) floatLabel.textContent = navHistoryStack[navHistoryStack.length - 1].label;
      floatBtn.classList.remove("hidden");
      headerBtn.classList.remove("hidden");
    } else {
      floatBtn.classList.add("hidden");
      headerBtn.classList.add("hidden");
    }
  }

  function restorePreviousView() {
    if (navHistoryStack.length === 0) return;
    const prev = navHistoryStack.pop();
    updateBackButtonsUI();
    switchMainTab(prev.mainTab, true);
    if (prev.mainTab === "battles") switchBattleSub(prev.battleSub, true);
    setTimeout(() => {
      if (prev.eventId) {
        const card = document.getElementById(prev.eventId);
        if (card) {
          card.open = true;
          card.scrollIntoView({
            behavior: "smooth",
            block: "center"
          });
          card.classList.add("pulse-target");
          setTimeout(() => card.classList.remove("pulse-target"), 2000);
          return;
        }
      }
      window.scrollTo({
        top: prev.scrollY,
        behavior: "smooth"
      });
    }, 60);
  }

  function triggerBackNavigation() {
    if (navHistoryStack.length === 0) return;
    try {
      history.back();
    } catch (e) {
      restorePreviousView();
    }
  }
  window.addEventListener("popstate", () => {
    if (navHistoryStack.length > 0) restorePreviousView();
  });
  let touchStartX = 0,
    touchStartY = 0,
    isInsideHorizontalScroll = false;
  window.addEventListener("touchstart", e => {
    if (navHistoryStack.length === 0 || !e.touches || e.touches.length !== 1) return;
    touchStartX = e.touches[0].clientX;
    touchStartY = e.touches[0].clientY;
    const ganttWrapper = document.getElementById("ganttScrollWrapper");
    isInsideHorizontalScroll = (ganttWrapper && ganttWrapper.contains(e.target) && touchStartX > 40);
  }, {
    passive: true
  });
  window.addEventListener("touchmove", e => {
    if (navHistoryStack.length === 0 || isInsideHorizontalScroll || !e.touches || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - touchStartX,
      dy = Math.abs(e.touches[0].clientY - touchStartY);
    const ind = document.getElementById("swipeBackIndicator");
    if (touchStartX < 100 && dx > 25 && dx > dy * 1.5 && ind) {
      ind.style.opacity = String(Math.min(dx / 100, 1));
      ind.style.transform = `translate(${Math.min(dx - 80, 16)}px, -50%)`;
    }
  }, {
    passive: true
  });
  window.addEventListener("touchend", e => {
    const ind = document.getElementById("swipeBackIndicator");
    if (ind) {
      ind.style.opacity = "0";
      ind.style.transform = "translate(-100%, -50%)";
    }
    if (navHistoryStack.length === 0 || isInsideHorizontalScroll || !e.changedTouches || e.changedTouches.length !== 1) return;
    const dx = e.changedTouches[0].clientX - touchStartX,
      dy = Math.abs(e.changedTouches[0].clientY - touchStartY);
    if (touchStartX < 120 && dx > 85 && dx > dy * 1.6) triggerBackNavigation();
  }, {
    passive: true
  });


  function switchMainTab(tab) {
    currentMainTab = tab;
    const tabs = [{
      id: "season",
      nav: "tabNavSeason",
      content: "tabContentSeason",
      activeColor: "text-orange-700"
    }, {
      id: "schedule",
      nav: "tabNavSchedule",
      content: "tabContentSchedule",
      activeColor: "text-sky-700"
    }, {
      id: "battles",
      nav: "tabNavBattles",
      content: "tabContentBattles",
      activeColor: "text-emerald-700"
    }, {
      id: "gopass",
      nav: "tabNavGoPass",
      content: "tabContentGoPass",
      activeColor: "text-amber-700"
    }];
    tabs.forEach(t => {
      const active = (t.id === tab);
      document.getElementById(t.nav).className = active ? `py-2 px-2 text-xs sm:text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-1 bg-white ${t.activeColor} shadow-sm` : `py-2 px-2 text-xs sm:text-sm font-bold rounded-lg transition-all flex items-center justify-center gap-1 text-slate-600 hover:text-slate-900`;
      document.getElementById(t.content).classList.toggle("hidden", !active);
    });
    if (tab === "battles") renderRaidSection();
  }

  function switchBattleSub(sub) {
    currentBattleSub = sub;
    const isRaid = (sub === "raids");
    document.getElementById("subTabRaids").className = isRaid ? "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition bg-white text-emerald-700 shadow-sm" : "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition text-slate-600 hover:text-slate-900";
    document.getElementById("subTabDmax").className = !isRaid ? "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition bg-white text-purple-700 shadow-sm" : "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition text-slate-600 hover:text-slate-900";
    document.getElementById("secBattleRaids").classList.toggle("hidden", !isRaid);
    document.getElementById("secBattleDmax").classList.toggle("hidden", isRaid);
    if (isRaid) renderRaidSection();
    else renderDmax9dbSection();
  }

  function switchGoPassSub(sub) {
    const isCurr = (sub === "current");
    document.getElementById("goPassSubCurrent").className = isCurr ? "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition bg-white text-amber-700 shadow-sm" : "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition text-slate-600 hover:text-slate-900";
    document.getElementById("goPassSubFuture").className = !isCurr ? "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition bg-white text-teal-700 shadow-sm" : "flex-1 py-2 text-xs sm:text-sm font-bold rounded-lg transition text-slate-600 hover:text-slate-900";
    document.getElementById("secGoPassCurrent").classList.toggle("hidden", !isCurr);
    document.getElementById("secGoPassFuture").classList.toggle("hidden", isCurr);
  }


  function toggleNewsDetail(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("hidden");
  }

  function handleNewsClick(targetId, detailId) {
    if (targetId) {
      const card = document.getElementById(targetId);
      if (card) {
        scrollToEventCard(targetId);
        return;
      }
    }
    if (detailId) toggleNewsDetail(detailId);
  }

  const RANGE_ON = "text-xs px-3 py-1 rounded-md font-bold transition bg-sky-600 text-white shadow-sm";
  const RANGE_OFF = "text-xs px-3 py-1 rounded-md font-bold transition text-slate-600 hover:text-slate-900";
  function ganttRanges() {
    const list = [{ key: "recent", label: "直近10日" }];
    for (let i = 0; i < 3; i++) {
      const d = new Date(todayYear, todayMonth - 1 + i, 1);
      list.push({ key: "m" + i, label: (d.getMonth() + 1) + "月", y: d.getFullYear(), m: d.getMonth() });
    }
    return list;
  }
  function renderGanttButtons() {
    const box = document.getElementById("ganttRangeBtns");
    if (!box) return;
    box.innerHTML = ganttRanges().map(r => `<button onclick="changeGanttRange('${r.key}')" class="${r.key === currentGanttRange ? RANGE_ON : RANGE_OFF}">${r.label}</button>`).join("");
  }
  function changeGanttRange(key) {
    currentGanttRange = key;
    renderGanttButtons();
    renderGanttTimeline();
  }

  function filterTimelineCategory(cat) {
    currentCategoryFilter = cat;
    ["all", "main", "cd", "raid", "dmax", "collab"].forEach(c => {
      const btn = document.getElementById(`catBtn-${c}`);
      if (btn) btn.className = (c === cat) ? "text-[11px] px-2.5 py-0.5 rounded-full font-bold transition bg-sky-600 text-white shadow-sm" : "text-[11px] px-2.5 py-0.5 rounded-full font-bold transition bg-slate-100 text-slate-600 hover:bg-slate-200";
    });
    renderGanttTimeline();
    renderEventAccordions();
  }


  function scrollToEventCard(id) {
    if (currentMainTab !== "schedule") switchMainTab("schedule");
    const card = document.getElementById(id);
    if (card) {
      pushNavState("", "上部の一覧へ戻る");
      card.open = true;
      card.scrollIntoView({
        behavior: "smooth",
        block: "start"
      });
      card.classList.add("pulse-target");
      setTimeout(() => card.classList.remove("pulse-target"), 2400);
    }
  }

  function setRaidSortMode(mode) {
    raidSortMode = mode;
    const isDps = (mode === "dps");
    document.getElementById("btnSortDps").className = isDps ? "text-xs font-extrabold px-2.5 py-1 rounded-md transition bg-sky-600 text-white shadow-sm flex items-center gap-1" : "text-xs font-bold px-2.5 py-1 rounded-md transition text-slate-600 hover:text-slate-900 flex items-center gap-1";
    document.getElementById("btnSortTdo").className = !isDps ? "text-xs font-extrabold px-2.5 py-1 rounded-md transition bg-emerald-600 text-white shadow-sm flex items-center gap-1" : "text-xs font-bold px-2.5 py-1 rounded-md transition text-slate-600 hover:text-slate-900 flex items-center gap-1";
    renderRaidRanking();
  }

  function toggleRaidFilter(type) {
    if (type === "mega") {
      filterMega = !filterMega;
      const btn = document.getElementById("btnToggleMega");
      btn.className = filterMega ? "text-xs font-bold px-2.5 py-1.5 rounded-lg border transition bg-purple-100 text-purple-700 border-purple-300 shadow-sm" : "text-xs font-bold px-2.5 py-1.5 rounded-lg border transition bg-slate-100 text-slate-600 border-slate-200";
      btn.textContent = filterMega ? "✨ メガ含 (ON)" : "✨ メガ含 (OFF)";
    } else if (type === "shadow") {
      filterShadow = !filterShadow;
      const btn = document.getElementById("btnToggleShadow");
      btn.className = filterShadow ? "text-xs font-bold px-2.5 py-1.5 rounded-lg border transition bg-rose-100 text-rose-700 border-rose-300 shadow-sm" : "text-xs font-bold px-2.5 py-1.5 rounded-lg border transition bg-slate-100 text-slate-600 border-slate-200";
      btn.textContent = filterShadow ? "🔥 シャドウ含 (ON)" : "🔥 シャドウ含 (OFF)";
    }
    renderRaidRanking();
  }

  function renderRaidSection() {
    renderRaidPicker();
    renderRaidOverview();
    renderRaidMegaRecommendations();
    renderRaidRanking();
  }

  // レイド/マックスバトルの選択カード：開催中・今後を「終了が早い順」に1列で並べる。期間は小さく添える（カードの高さは変えない）
  function bossPickerCard(b, key, active, ring, onPick, imgCls) {
    const card = document.createElement("button");
    card.className = `p-2 rounded-xl border text-left transition flex items-center gap-2 ${active ? ring : "bg-white border-slate-200 hover:bg-slate-50"}`;
    card.onclick = onPick;
    const live = isEventActive(b);
    card.innerHTML = `<img src="${getPokeImg(b.dex, b.name)}" class="${imgCls} object-contain flex-shrink-0"><div class="overflow-hidden flex-1">
      <div class="text-[10px] leading-[12px] ${live ? "text-emerald-700" : "text-purple-700"} font-bold truncate">${live ? "● " : ""}${b.tier}</div>
      <div class="text-xs leading-[16px] font-extrabold text-slate-900 truncate">${b.name}${b.shiny ? " ✨" : ""}</div>
      <div class="text-[10px] leading-[12px] text-slate-500 truncate">${b.periodText || ""}</div></div>`;
    return card;
  }
  function sortedBosses(data) {
    return Object.keys(data).filter(k => !isEventPast(data[k])).sort((x, y) => data[x]._e - data[y]._e || data[x]._s - data[y]._s);
  }

  function renderRaidPicker() {
    const cur = document.getElementById("raidBossPickerCurrent"), fut = document.getElementById("raidBossPickerFuture");
    cur.innerHTML = ""; fut.innerHTML = "";
    const keys = sortedBosses(RAID_DATA);
    if (!keys.includes(activeRaidKey) && keys.length) activeRaidKey = keys[0];
    keys.forEach(key => {
      const card = bossPickerCard(RAID_DATA[key], key, key === activeRaidKey, "bg-sky-50 border-sky-500 shadow-sm ring-1 ring-sky-500", () => { activeRaidKey = key; renderRaidSection(); }, "w-11 h-11");
      (isEventActive(RAID_DATA[key]) ? cur : fut).appendChild(card);
    });
  }

  function renderRaidOverview() {
    const container = document.getElementById("raidBossOverview");
    const b = RAID_DATA[activeRaidKey];
    if (!b) return;
    const isCurr = isEventActive(b);
    container.innerHTML = ` <div class="flex flex-col sm:flex-row items-center sm:items-start gap-4"> <img src="${getPokeImg(b.dex, b.name)}" class="w-24 h-24 object-contain flex-shrink-0"> <div class="flex-1 text-center sm:text-left space-y-1.5"> <div class="flex flex-wrap items-center justify-center sm:justify-start gap-2"> <span class="text-xs ${isCurr ? 'bg-emerald-100 text-emerald-800 border-emerald-300' : 'bg-purple-100 text-purple-800 border-purple-300'} font-bold px-2 py-0.5 rounded border">${b.tier}</span> <span class="text-xs bg-amber-100 text-amber-800 border border-amber-300 font-extrabold px-2.5 py-0.5 rounded-full">${b.shinyText || '✨ 色違いあり'}</span> <span class="text-xs font-bold ${isCurr ? 'text-emerald-700' : 'text-purple-700'}">${b.status}</span> </div> <h3 class="text-lg font-black text-slate-900">${b.name}</h3> <div class="flex flex-wrap items-center justify-center sm:justify-start gap-1.5 pt-0.5"> <span class="text-xs text-slate-500 font-bold">タイプ:</span> ${renderTypeBadges(b.types)} <span class="text-xs text-slate-400 mx-1">|</span> <span class="text-xs text-slate-600">100%CP: <strong class="text-amber-600 font-bold">${b.cpNormal}</strong> (ブースト: <strong class="text-amber-700 font-bold">${b.cpBoost}</strong>)</span> </div> </div> </div> <div class="mt-3 pt-3 border-t border-slate-100 text-xs text-slate-700 leading-relaxed bg-slate-50 p-2.5 rounded-lg border border-slate-200"> <strong class="text-sky-700 font-bold">💡 実戦攻略ノート:</strong> ${b.tactics} <div class="text-rose-600 font-bold mt-1">討伐推奨人数: ${b.minPlayers}</div> </div> `;
  }

  function renderRaidMegaRecommendations() {
    const box = document.getElementById("raidMegaRecommendBox");
    const b = RAID_DATA[activeRaidKey];
    if (!box || !b || !b.megaRecs) return;
    const isSuperMega = (activeRaidKey === "mega-chandelure");
    box.innerHTML = ` <div class="flex flex-wrap items-center justify-between gap-2 mb-2.5"> <h3 class="text-sm font-black text-purple-900 flex items-center gap-1.5"> <span>✨</span> おすすめメガシンカ・ゲンシカイキ編成（火力重視 ＆ アメXLボーナス重視の2軸） </h3> ${isSuperMega ? `<span class="text-[11px] bg-rose-600 text-white font-extrabold px-2.5 py-0.5 rounded-full shadow-sm">🔥 スーパーメガ仕様：メガシンカ1匹につきボスのシールド1枚破壊！（※ゲンシカイキは破壊不可）</span>` : ''} </div> <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs"> <div class="bg-white/90 border border-purple-200 rounded-xl p-3 space-y-2 shadow-sm"> <div class="font-extrabold text-purple-800 flex items-center gap-1 border-b border-purple-100 pb-1"> <span>🗡️</span> 軸1：討伐火力・味方ブースト${isSuperMega ? '・シールド破壊' : ''}でおすすめ </div> ${(b.megaRecs.attack || []).map(m => ` <div class="flex items-start gap-2.5"> <img src="${getPokeImg(m.dex, m.name)}" class="w-11 h-11 object-contain flex-shrink-0"> <div> <div class="font-black text-slate-900">${m.name}</div> <div class="text-[11px] text-sky-700 font-semibold">${m.move}</div> <p class="text-[11px] text-slate-600 leading-snug mt-0.5">${m.desc}</p> </div> </div> `).join("")} </div> <div class="bg-white/90 border border-amber-200 rounded-xl p-3 space-y-2 shadow-sm"> <div class="font-extrabold text-amber-800 flex items-center gap-1 border-b border-amber-100 pb-1"> <span>🍬</span> 軸2：捕獲時のアメ＋1〜2個 ＆ アメXL確率UPでおすすめ </div> ${(b.megaRecs.candy || []).map(m => ` <div class="flex items-start gap-2.5"> <img src="${getPokeImg(m.dex, m.name)}" class="w-11 h-11 object-contain flex-shrink-0"> <div> <div class="font-black text-slate-900">${m.name} <span class="text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-bold">${m.type}</span></div> <p class="text-[11px] text-slate-600 leading-snug mt-0.5">${m.desc}</p> </div> </div> `).join("")} </div> </div> `;
  }

  function renderRaidRanking() {
    const list = document.getElementById("raidRankingList");
    const title = document.getElementById("raidRankingTitle");
    list.innerHTML = "";
    const b = RAID_DATA[activeRaidKey];
    if (!b) return;
    let filtered = b.counters.filter(c => {
      if (c.tag === "mega" && !filterMega) return false;
      if (c.tag === "shadow" && !filterShadow) return false;
      return true;
    });
    const isDpsMode = (raidSortMode === "dps");
    filtered.sort((x, y) => isDpsMode ? (y.dps - x.dps || y.tdo - x.tdo) : (y.tdo - x.tdo || y.dps - x.dps));
    const top10 = filtered.slice(0, 10);
    const maxVal = top10.length > 0 ? (isDpsMode ? top10[0].dps : top10[0].tdo) : 1;
    const conditions = [];
    if (filterMega) conditions.push("メガ含");
    if (filterShadow) conditions.push("シャドウ含");
    if (!filterMega && !filterShadow) conditions.push("通常ポケモン限定");
    title.textContent = `${isDpsMode ? "⚡ 対策DPSランキング (討伐速度重視)" : "🛡️ 対策TDOランキング (総ダメ・耐久重視)"} TOP 10 (${conditions.join(" / ")})`;
    top10.forEach((c, index) => {
      const tagBadge = c.tag === "mega" ? `<span class="text-[10px] bg-purple-100 text-purple-700 font-bold px-1.5 py-0.5 rounded border border-purple-300">メガ/ゲンシ</span>` : (c.tag === "shadow" ? `<span class="text-[10px] bg-rose-100 text-rose-700 font-bold px-1.5 py-0.5 rounded border border-rose-300">シャドウ</span>` : `<span class="text-[10px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded font-bold">通常</span>`);
      const rankColor = index === 0 ? "text-amber-500 text-base font-black" : (index <= 2 ? "text-slate-700 text-sm font-black" : "text-slate-400");
      const currentVal = isDpsMode ? c.dps : c.tdo;
      const barWidthPct = Math.max(20, Math.round((currentVal / maxVal) * 100));
      const row = document.createElement("div");
      row.className = "bg-slate-50 border border-slate-200 hover:bg-slate-100 p-2.5 rounded-lg flex items-center justify-between gap-3 transition shadow-sm";
      row.innerHTML = ` <div class="flex items-center gap-3 overflow-hidden flex-1"> <span class="w-6 text-center font-bold ${rankColor} flex-shrink-0">#${index + 1}</span> <img src="${getPokeImg(c.dex, c.name)}" class="w-11 h-11 object-contain flex-shrink-0"> <div class="overflow-hidden flex-1"> <div class="text-xs font-bold text-slate-900 flex items-center gap-1.5"> <span class="truncate">${c.name}</span> ${tagBadge} </div> <div class="text-[11px] text-slate-700 flex flex-wrap items-center gap-2 mt-1"> <span><span class="bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded text-[10px] font-bold mr-1">通常</span>${c.fast}</span> <span><span class="bg-sky-100 text-sky-800 px-1.5 py-0.2 rounded text-[10px] font-bold mr-1">SP</span><strong class="text-sky-700">${c.charge}</strong></span> </div> <div class="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden mt-1.5"> <div class="${isDpsMode ? 'bg-sky-500' : 'bg-emerald-500'} h-full rounded-full" style="width: ${barWidthPct}%"></div> </div> </div> </div> <div class="text-right flex-shrink-0 min-w-[76px]"> ${isDpsMode ? `<div class="text-sm font-black text-sky-700 font-mono">${c.dps.toFixed(1)} <span class="text-[10px]">DPS</span></div><div class="text-[10px] text-slate-500 font-mono">TDO: <strong>${c.tdo}</strong></div>` : `<div class="text-sm font-black text-emerald-700 font-mono">${c.tdo} <span class="text-[10px]">TDO</span></div><div class="text-[10px] text-slate-500 font-mono">DPS: <strong>${c.dps.toFixed(1)}</strong></div>` } </div> `;
      list.appendChild(row);
    });
  }

  function renderDmax9dbSection() {
    renderDmax9dbPicker();
    renderDmax9dbCard();
  }

  function renderDmax9dbPicker() {
    const cur = document.getElementById("dmaxBossPickerCurrent"), fut = document.getElementById("dmaxBossPickerFuture");
    cur.innerHTML = ""; fut.innerHTML = "";
    const keys = sortedBosses(DMAX_9DB_DATA);
    if (!keys.includes(activeDmax9dbKey) && keys.length) activeDmax9dbKey = keys[0];
    keys.forEach(key => {
      const card = bossPickerCard(DMAX_9DB_DATA[key], key, key === activeDmax9dbKey, "bg-purple-50 border-purple-500 shadow-sm ring-1 ring-purple-500", () => { activeDmax9dbKey = key; renderDmax9dbSection(); }, "w-10 h-10");
      (isEventActive(DMAX_9DB_DATA[key]) ? cur : fut).appendChild(card);
    });
  }

  function renderDmax9dbCard() {
    const container = document.getElementById("dmax9dbContainer");
    const d = DMAX_9DB_DATA[activeDmax9dbKey];
    if (!d) return;
    container.innerHTML = ` <div class="bg-9db-card border border-purple-500/40 rounded-2xl p-4 shadow-xl space-y-4"> <div class="border-b border-purple-500/20 pb-3 flex flex-col sm:flex-row items-center justify-between gap-3"> <div class="flex items-center gap-3.5"> <img src="${getPokeImg(d.dex, d.name)}" class="w-20 h-20 object-contain flex-shrink-0 drop-shadow-lg"> <div> <div class="flex flex-wrap items-center gap-2 mb-1"> <span class="text-[11px] text-purple-300 font-semibold">📅 ${d.dateInfo}</span> <span class="text-xs bg-amber-400/20 text-amber-300 border border-amber-400/50 font-extrabold px-2.5 py-0.5 rounded-full">${d.shinyText || '✨ 色違いあり'}</span> </div> <h2 class="text-xl sm:text-2xl font-black text-white tracking-wide">${d.name}</h2> <div class="flex flex-wrap items-center gap-2 mt-1"> <span class="text-xs text-purple-200 font-bold">タイプ:</span> ${renderTypeBadges(d.types)} <span class="text-xs text-purple-200 ml-1">捕獲時100%CP (PL20): <strong class="text-amber-300 text-sm">${d.cpPL20 || '-'}</strong></span> </div> </div> </div> <div class="text-right flex items-center gap-1 bg-purple-900/60 border border-purple-500/40 px-3 py-1.5 rounded-lg flex-shrink-0"> <span class="text-amber-400 text-sm">👾</span> <span class="font-black text-white text-sm sm:text-base">${d.tier}</span> </div> </div> <div class="bg-black/40 border border-purple-500/30 rounded-xl p-2.5 flex flex-wrap items-center gap-2"> <span class="text-[11px] text-purple-300 font-bold">⚡ ボスの使用技:</span> ${(d.moves || []).map(m => `<span class="text-xs px-2.5 py-0.5 rounded-md text-white font-bold ${m.color}">${m.name}</span>`).join("")} </div> <div class="space-y-2"> <h3 class="text-sm font-extrabold text-sky-300 flex items-center gap-1.5"> <span>🗡️</span> アタッカー (ダイマックス・キョダイマックス火力 TOP 5) </h3> <div class="grid grid-cols-2 sm:grid-cols-5 gap-2"> ${(d.attackers || []).map(a => ` <div class="bg-black/50 border border-purple-500/40 hover:border-sky-400 transition rounded-xl p-2 relative flex flex-col items-center text-center"> <span class="absolute top-1.5 left-1.5 bg-blue-600 text-white font-black text-[10px] w-5 h-5 rounded flex items-center justify-center">#${a.rank}</span> <img src="${getPokeImg(a.dex, a.name)}" class="w-14 h-14 object-contain my-1"> <div class="text-xs font-bold text-white truncate w-full">${a.name}</div> <div class="text-[10px] text-slate-200 mt-1 space-y-1 w-full bg-slate-900/80 p-1.5 rounded text-left"> <div class="truncate"><span class="bg-slate-700 text-slate-200 px-1 rounded font-bold mr-1">通常</span>${a.fast}</div> <div class="truncate text-sky-300 font-bold"><span class="bg-sky-900 text-sky-200 px-1 rounded font-bold mr-1">SP</span>${a.charge}</div> </div> </div> `).join("")} </div> </div> <div class="space-y-2"> <h3 class="text-sm font-extrabold text-emerald-300 flex items-center gap-1.5"> <span>🛡️</span> タンク (耐久＆0.5秒高速メーターチャージ TOP 5) </h3> <div class="grid grid-cols-2 sm:grid-cols-5 gap-2"> ${(d.tanks || []).map(t => ` <div class="bg-black/50 border border-purple-500/40 hover:border-emerald-400 transition rounded-xl p-2 relative flex flex-col items-center text-center"> <span class="absolute top-1.5 left-1.5 bg-emerald-600 text-white font-black text-[10px] w-5 h-5 rounded flex items-center justify-center">#${t.rank}</span> <img src="${getPokeImg(t.dex, t.name)}" class="w-14 h-14 object-contain my-1"> <div class="text-xs font-bold text-white truncate w-full">${t.name}</div> <div class="text-[10px] text-slate-200 mt-1 space-y-1 w-full bg-slate-900/80 p-1.5 rounded text-left"> <div class="truncate text-emerald-300 font-bold"><span class="bg-emerald-900 text-emerald-200 px-1 rounded font-bold mr-1">通常</span>${t.fast}</div> <div class="truncate"><span class="bg-slate-700 text-slate-200 px-1 rounded font-bold mr-1">SP</span>${t.charge}</div> </div> </div> `).join("")} </div> <div class="text-[11px] text-purple-200/90 bg-black/40 border border-purple-500/30 p-2.5 rounded-lg mt-2"> ${d.tankNote || ''} </div> </div> <div class="space-y-2 pt-2 border-t border-purple-500/30"> <h3 class="text-sm font-extrabold text-amber-300">📋 立ち回り (9DB実戦定石ステップ)</h3> <div class="grid grid-cols-1 sm:grid-cols-2 gap-2"> ${(d.routine || []).map(r => ` <div class="bg-black/60 border border-purple-500/40 rounded-xl p-2.5 flex items-start gap-2.5"> <div class="bg-blue-600 text-white font-black text-xs w-6 h-6 rounded flex items-center justify-center flex-shrink-0 mt-0.5">${r.step}</div> <div> <div class="text-xs font-extrabold text-white">${r.title}</div> <ul class="text-[11px] text-purple-200/90 list-disc list-inside mt-0.5">${r.details.map(det => `<li>${det}</li>`).join("")}</ul> </div> </div> `).join("")} </div> </div> </div> `;
  }

  function jumpToCounterTarget(targetKey, isDmax, fromEventId, backLabel) {
    if (!targetKey) return;
    pushNavState(fromEventId || "", backLabel || "元のイベントに戻る");
    switchMainTab("battles");
    if (isDmax) {
      switchBattleSub("dmax");
      if (DMAX_9DB_DATA[targetKey]) {
        activeDmax9dbKey = targetKey;
        renderDmax9dbSection();
      }
    } else {
      switchBattleSub("raids");
      if (RAID_DATA[targetKey]) {
        activeRaidKey = targetKey;
        renderRaidSection();
      }
    }
    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
  }

  function hideEvent(id, e) {
    if (e) e.stopPropagation();
    hiddenEventIds.add(id);
    renderGanttTimeline();
    renderEventAccordions();
    updateGlobalHiddenUI();
  }

  function restoreAllHiddenEvents() {
    hiddenEventIds.clear();
    renderGanttTimeline();
    renderEventAccordions();
    updateGlobalHiddenUI();
  }

  function updateGlobalHiddenUI() {
    const btn = document.getElementById("globalRestoreBtn"),
      count = document.getElementById("globalHiddenCount");
    if (hiddenEventIds.size > 0) {
      btn.classList.remove("hidden");
      count.textContent = hiddenEventIds.size;
    } else {
      btn.classList.add("hidden");
    }
  }

  function markNewsRead(id) {
    readNewsIds.add(id);
    renderNewsSection();
  }

  function resetReadNews() {
    readNewsIds.clear();
    renderNewsSection();
  }