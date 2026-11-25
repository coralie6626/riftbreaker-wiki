// Riftbreaker Field Guide: power chart + energy calculator.
// Data comes from data/energy.json (built by tools/build_site_data.py).
(function () {
  "use strict";

  const ICONS = "riftbreaker_data/icons/";
  const CATEGORIES = {
    energy: "Energy", main: "Main", resources: "Resources", defense: "Defense",
    megastructures: "Megastructures", tools: "Tools", decorations: "Decorations",
  };
  // Buildings whose output depends on time of day or weather.
  const VARIABLE = {
    "buildings/energy/solar_panels": "Day only",
    "buildings/energy/wind_turbine": "Varies with wind",
  };
  const EXAMPLE = [
    ["buildings/main/headquarters", 2, 1],
    ["buildings/energy/solar_panels", 2, 8],
    ["buildings/energy/wind_turbine", 1, 6],
    ["buildings/energy/carbonium_powerplant", 1, 2],
    ["buildings/energy/energy_storage", 1, 2],
    ["buildings/resources/carbonium_factory", 1, 4],
    ["buildings/resources/steel_factory", 1, 4],
    ["buildings/main/communications_hub", 1, 1],
    ["buildings/defense/tower_basic", 2, 8],
    ["buildings/defense/short_range_radar", 1, 2],
  ];

  let DATA = null;
  const byKey = new Map();
  const state = { chartLevel: 1, cat: "all", q: "", rows: [] };

  // ---------- helpers ----------
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null) n.append(kid.nodeType ? kid : String(kid));
    return n;
  }
  // replaceChildren() would print null as the text "null", so drop empty slots first.
  const setKids = (node, ...kids) => node.replaceChildren(...kids.filter((k) => k != null));
  function icon(path, alt) {
    if (!path) return el("span", { style: "width:28px;height:28px;display:inline-block" });
    const img = el("img", { src: ICONS + path + ".png", alt: alt || "", loading: "lazy", width: 28, height: 28 });
    img.addEventListener("error", () => { img.style.visibility = "hidden"; });
    return img;
  }
  const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
  const fmt = (v) => nf.format(v);
  const signed = (v) => (v > 0 ? "+" : v < 0 ? "−" : "") + fmt(Math.abs(v));
  const resName = (r) => (DATA.resources[r] && DATA.resources[r].name) || r;
  function resLabel(r) {
    const info = DATA.resources[r];
    return el("span", { class: "res" }, info && info.icon ? el("img", { src: ICONS + info.icon + ".png", alt: "" }) : null, resName(r));
  }
  const levelOf = (b, lvl) => b.levels.find((l) => l.level === lvl) || null;
  const energyNet = (l) => (l.produces.energy || 0) - (l.consumes.energy || 0);
  const levelTag = (b, l) => (b.levels.length > 1 ? " · Lv " + l.level : "");

  // ---------- alternatives ----------
  // Some buildings take one input OR another (Fusion: water or super coolant), or make one output
  // OR another (Armory: consumables or mech ammo). `choices(l)` lists those groups; a row stores
  // which resource it uses from each one in `row.use` (same order). Defaults to the first option.
  //
  // Liquid buildings (Pump, Compressor, Decompressor) name a resource *group* instead: they work
  // with whichever liquid the player picks, and their in and out carry that same liquid. They get
  // one "liquid" choice; `liquidRes` maps each group to the resource for the chosen liquid.
  const hasLiquid = (l) => !!(l.group_io && l.group_io.length);
  function liquidOptions(l) {
    const io = DATA.liquid_io;
    // A pump can only take liquids that form pools on the map.
    return l.group_io.some((g) => g.group === "vein") ? io.liquids.filter((x) => io.pools[x]) : io.liquids;
  }
  function liquidRes(group, x) {
    if (group === "local") return x;
    if (group === "local_compressed") return x + "_compressed";
    if (group === "vein") return DATA.liquid_io.pools[x];
    return null;
  }
  const choices = (l) => [
    ...(l.consumes_one_of || []).map((g) => ({ kind: "in", g })),
    ...(l.produces_one_of || []).map((g) => ({ kind: "out", g })),
    ...(hasLiquid(l) ? [{ kind: "liquid", g: liquidOptions(l) }] : []),
  ];
  const defaultUse = (l) => choices(l).map((c) => c.g[0]);
  function validUse(l, use) {
    return choices(l).map((c, i) => (use && c.g.includes(use[i]) ? use[i] : c.g[0]));
  }

  // What one building really uses and makes, with the chosen option of each group.
  function effective(l, use) {
    const pick = validUse(l, use);
    const consumes = { ...l.consumes }, produces = { ...l.produces };
    let requires = l.requires;
    choices(l).forEach((c, i) => {
      if (c.kind === "liquid") {
        for (const io of l.group_io) {
          const r = liquidRes(io.group, pick[i]);
          if (!r) continue;
          if (io.group === "vein") requires = [...requires, r];   // a pool is a deposit, not a flow
          else (io.kind === "in" ? consumes : produces)[r] = io.value;
        }
        return;
      }
      const bag = c.kind === "in" ? consumes : produces;
      for (const r of c.g) if (r !== pick[i]) delete bag[r];
      // Rare Element Mine: the chosen ore decides which vein it sits on.
      if (c.kind === "out" && requires.length > 1) {
        const vein = requires.find((d) => DATA.resources[d] && DATA.resources[d].ore === pick[i]);
        if (vein) requires = [vein];
      }
    });
    return { consumes, produces, requires };
  }

  // "Burns 100 Water or 50 Super coolant/s". Pass `use` to describe one chosen option instead.
  // "Pumps 100 liquid/s from a pool", or with a chosen liquid "Restores 100 Water/s from Comp. water".
  function liquidText(l, x) {
    const inn = l.group_io.find((g) => g.kind === "in"), out = l.group_io.find((g) => g.kind === "out");
    const v = fmt((out || inn).value);
    const name = (group, generic) => (x ? resName(liquidRes(group, x)) : generic);
    if (inn && inn.group === "vein") return `Pumps ${v} ${name("local", "liquid")}/s` + (x ? "" : " from a pool");
    if (inn && inn.group === "local_compressed") return `Restores ${v} ${name("local", "liquid")}/s` + (x ? " from " + name("local_compressed") : " from its compressed form");
    if (inn && inn.group === "local") return `Compresses ${v} ${name("local", "liquid")}/s`;
    return "";
  }

  function fuelText(l, use) {
    const x = use ? effective(l, use) : l;
    const groups = use ? [] : l.consumes_one_of || [];
    const parts = [];
    let liquid = null;
    if (hasLiquid(l)) {
      liquid = use ? validUse(l, use)[choices(l).length - 1] : null;
      parts.push(liquidText(l, liquid));
    }
    // Liquid flows are described above, so leave them out of "On …" and "Burns …".
    const lr = liquid ? new Set(l.group_io.map((g) => liquidRes(g.group, liquid))) : new Set();
    const req = x.requires.filter((r) => !lr.has(r));
    if (liquid && x.requires.length > req.length) parts.unshift("On " + resName(liquidRes("vein", liquid)));
    if (req.length === 1) parts.push("On " + resName(req[0]));
    else if (req.length > 1) parts.push("On any rare ore vein");
    const seen = new Set(lr), fuel = [];
    for (const r of Object.keys(x.consumes)) {
      if (r === "energy" || seen.has(r)) continue;
      const g = groups.find((gr) => gr.includes(r)) || [r];
      g.forEach((m) => seen.add(m));
      fuel.push(g.map((m) => fmt(x.consumes[m]) + " " + resName(m)).join(" or "));
    }
    if (fuel.length) parts.push("Burns " + fuel.join(" + ") + "/s");
    return parts.join(" · ");
  }

  // ---------- theme ----------
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("theme"); } catch (e) { /* storage blocked */ }
    if (saved) document.documentElement.dataset.theme = saved;
    document.getElementById("theme-toggle").addEventListener("click", () => {
      const cur = document.documentElement.dataset.theme ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    });
  }

  // ---------- hero stats ----------
  function renderStats() {
    const all = DATA.buildings.flatMap((b) => b.levels.map((l) => ({ b, l })));
    const best = (fn) => all.reduce((a, x) => (fn(x) > fn(a) ? x : a));
    const plants = DATA.buildings.filter((b) => b.category === "energy" && b.levels[0].produces.energy);
    const top = best((x) => x.l.produces.energy || 0);
    const hungry = best((x) => x.l.consumes.energy || 0);
    const battery = best((x) => x.l.energy_storage || 0);
    const tile = (path, k, v, d) => el("div", { class: "stat" }, icon(path),
      el("div", {}, el("div", { class: "k", text: k }), el("div", { class: "v", text: v }), el("div", { class: "d", text: d })));
    document.getElementById("stats").replaceChildren(
      tile(plants[0] && plants[0].levels[0].icon, "Power plant types", String(plants.length), "Each with 3 upgrade levels"),
      tile(top.l.icon, "Strongest generator", fmt(top.l.produces.energy) + "/s", top.b.name + levelTag(top.b, top.l)),
      tile(hungry.l.icon, "Hungriest building", fmt(hungry.l.consumes.energy) + "/s", hungry.b.name),
      tile(battery.l.icon, "Largest battery", fmt(battery.l.energy_storage), battery.b.name + levelTag(battery.b, battery.l)),
    );
  }

  // ---------- power chart ----------
  function producers() {
    return DATA.buildings.filter((b) => b.category === "energy" && b.levels.some((l) => l.produces.energy));
  }

  function renderChart() {
    const chart = document.getElementById("power-chart");
    const tip = document.getElementById("tooltip");
    const list = producers();
    // Fixed scale across levels, so switching level shows real growth.
    const max = Math.max(...list.flatMap((b) => b.levels.map((l) => l.produces.energy || 0)));
    const items = list.map((b) => ({ b, l: levelOf(b, state.chartLevel) }))
      .filter((x) => x.l)
      .sort((a, z) => z.l.produces.energy - a.l.produces.energy);

    chart.replaceChildren();
    for (const { b, l } of items) {
      const v = l.produces.energy;
      const pct = (v / max) * 100;
      const note = [VARIABLE[b.key], fuelText(l)].filter(Boolean).join(" · ") || "No fuel needed";
      const val = el("span", { class: "bar-val" + (pct > 14 ? " inside" : ""), text: fmt(v) });
      val.style.left = pct + "%";
      const bar = el("div", { class: "bar" });
      bar.style.width = pct + "%";
      const track = el("div", { class: "bar-track", tabindex: 0, "aria-label": `${b.name}: ${fmt(v)} energy per second. ${note}` }, bar, val);
      const show = (evt) => showTip(tip, track, evt, b, l);
      track.addEventListener("pointermove", show);
      track.addEventListener("focus", show);
      track.addEventListener("pointerleave", () => { tip.hidden = true; });
      track.addEventListener("blur", () => { tip.hidden = true; });
      chart.append(
        el("div", { class: "bar-label" }, icon(l.icon),
          el("div", {}, el("div", { class: "nm", text: b.name }), el("div", { class: "nt", text: note }))),
        track,
      );
    }
    renderPowerTable(list);
  }

  // Buildings that can output liquid `res`, at `level` (or their highest level below it), with the
  // rate each makes. Covers liquid buildings set to that liquid (Pump, Decompressor) and buildings
  // that always make it (Water Filtering Plant, Gas Extractor...). Skips `except` (the plant itself).
  function liquidSuppliers(res, level, except) {
    const out = [];
    for (const s of DATA.buildings) {
      if (s === except) continue;
      const lv = [...s.levels].reverse().find((x) => x.level <= level) || s.levels[0];
      let rate = 0;
      if (hasLiquid(lv)) {
        const o = lv.group_io.find((g) => g.kind === "out" && g.group === "local");
        if (o && liquidOptions(lv).includes(res)) rate = o.value;
      } else if (lv.produces[res] && !(lv.optional_outputs || []).includes(res)) {
        rate = lv.produces[res];
      }
      if (rate > 0) out.push({ b: s, l: lv, rate });
    }
    return out.sort((a, z) => z.rate - a.rate);
  }

  // Tooltip block: for each liquid the plant burns, which buildings supply it and how many it takes.
  function supplyLines(b, l) {
    const liquids = new Set(DATA.liquid_io.liquids);
    const fuels = Object.keys(l.consumes).filter((r) => liquids.has(r));
    if (!fuels.length) return [];
    const rows = fuels.map((r) => {
      const need = l.consumes[r];
      const sup = liquidSuppliers(r, l.level, b);
      const kids = [resLabel(r), ": "];
      if (!sup.length) kids.push("no building makes it");
      sup.forEach((s, i) => {
        if (i) kids.push(" · ");
        kids.push(s.b.name + " ", el("b", { text: "×" + Math.ceil(need / s.rate) }));
      });
      return el("div", { class: "tr supply" }, ...kids);
    });
    const alt = (l.consumes_one_of || []).some((g) => g.length > 1 && g.every((r) => liquids.has(r)));
    return [el("div", { class: "th", text: `Fuel supply at Lv ${l.level}` + (alt ? " (either one)" : "") }), ...rows];
  }

  function showTip(tip, track, evt, b, l) {
    // One line per resource, or per group of alternatives joined with "or".
    const lines = (rates, groups, verb, optional) => {
      const seen = new Set(), out = [];
      for (const r of Object.keys(rates)) {
        if (r === "energy" || seen.has(r)) continue;
        const g = (groups || []).find((gr) => gr.includes(r)) || [r];
        g.forEach((m) => seen.add(m));
        const kids = [verb + " "];
        g.forEach((m, i) => {
          if (i) kids.push(" or ");
          kids.push(el("b", { text: fmt(rates[m]) + "/s" }), resLabel(m));
          if ((optional || []).includes(m)) kids.push(" (optional)");
        });
        out.push(el("div", { class: "tr" }, ...kids));
      }
      return out;
    };
    setKids(tip,
      el("div", { class: "tv", text: fmt(l.produces.energy) + " energy/s" }),
      el("div", { class: "tn", text: b.name + " · Level " + l.level }),
      ...lines(l.consumes, l.consumes_one_of, "Uses"),
      ...l.requires.map((r) => el("div", { class: "tr" }, "Built on ", resLabel(r))),
      ...lines(l.produces, l.produces_one_of, "Also makes", l.optional_outputs),
      l.energy_storage ? el("div", { class: "tr", text: "Stores " + fmt(l.energy_storage) + " energy" }) : null,
      ...supplyLines(b, l),
      b.description ? el("div", { class: "td", text: b.description }) : null,
    );
    tip.hidden = false;
    const root = tip.parentElement.getBoundingClientRect();
    const r = track.getBoundingClientRect();
    const x = evt && evt.clientX ? evt.clientX : r.left + 40;
    let left = x - root.left + 14;
    left = Math.min(left, root.width - tip.offsetWidth - 4);
    tip.style.left = Math.max(0, left) + "px";
    tip.style.top = (r.bottom - root.top + 6) + "px";
  }

  function renderPowerTable(list) {
    const levels = [1, 2, 3];
    const t = document.getElementById("power-table");
    t.replaceChildren(
      el("thead", {}, el("tr", {}, el("th", { text: "Building" }),
        ...levels.map((n) => el("th", { class: "num", text: "Lv " + n })), el("th", { text: "Needs" }))),
      el("tbody", {}, ...list.map((b) => el("tr", {},
        el("td", { text: b.name }),
        ...levels.map((n) => { const l = levelOf(b, n); return el("td", { class: "num", text: l && l.produces.energy ? fmt(l.produces.energy) : "–" }); }),
        el("td", { text: [VARIABLE[b.key], fuelText(b.levels[0])].filter(Boolean).join(" · ") || "–" }),
      ))),
    );
  }

  function initLevelToggle() {
    const seg = document.getElementById("level-toggle");
    seg.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-level]");
      if (!btn) return;
      state.chartLevel = Number(btn.dataset.level);
      for (const b of seg.querySelectorAll("button")) b.setAttribute("aria-checked", String(b === btn));
      renderChart();
    });
  }

  // ---------- calculator: picker ----------
  function renderCatFilter() {
    const box = document.getElementById("cat-filter");
    const cats = ["all", ...Object.keys(CATEGORIES).filter((c) => DATA.buildings.some((b) => b.category === c))];
    box.replaceChildren(...cats.map((c) => el("button", {
      type: "button", class: "chip", "aria-pressed": String(state.cat === c),
      text: c === "all" ? "All" : CATEGORIES[c],
      onclick: () => { state.cat = c; renderCatFilter(); renderPicker(); },
    })));
  }

  function renderPicker() {
    const list = document.getElementById("picker-list");
    const q = state.q.trim().toLowerCase();
    const shown = DATA.buildings.filter((b) =>
      (state.cat === "all" || b.category === state.cat) &&
      (!q || b.name.toLowerCase().includes(q) || (CATEGORIES[b.category] || "").toLowerCase().includes(q)));
    list.replaceChildren();
    if (!shown.length) { list.append(el("div", { class: "empty", text: "No buildings match." })); return; }
    let lastCat = null;
    for (const b of shown) {
      if (b.category !== lastCat) { list.append(el("div", { class: "cat-head", text: CATEGORIES[b.category] || b.category })); lastCat = b.category; }
      list.append(pickRow(b));
    }
  }

  // One picker entry: clicking the name adds level 1; the level buttons add that level directly.
  function pickRow(b) {
    const first = b.levels[0];
    const img = icon(first.icon);
    const energy = el("span", { class: "e" });
    const showLevel = (l) => {
      const e = energyNet(l);
      energy.className = "e " + (e > 0 ? "pos" : e < 0 ? "neg" : "");
      energy.textContent = e ? signed(e) + "/s" : l.energy_storage ? "storage" : "no power";
      if (l.icon) img.src = ICONS + l.icon + ".png";
    };
    showLevel(first);

    const main = el("button", { type: "button", class: "pick-main", title: b.description,
      "aria-label": `Add ${b.name}${b.levels.length > 1 ? " level " + first.level : ""}`,
      onclick: () => addRow(b.key, first.level, 1) }, img, el("span", { class: "nm", text: b.name }));

    let levels = null;
    if (b.levels.length > 1) {
      levels = el("div", { class: "lv", role: "group", "aria-label": b.name + " level" },
        el("span", { class: "lv-k", text: "Lv", "aria-hidden": "true" }),
        ...b.levels.map((l) => {
          const e = energyNet(l);
          const btn = el("button", { type: "button", text: String(l.level),
            title: `Add level ${l.level}: ${e ? signed(e) + " energy/s" : "storage " + fmt(l.energy_storage)}`,
            "aria-label": `Add ${b.name} level ${l.level}`,
            onclick: () => addRow(b.key, l.level, 1) });
          btn.addEventListener("pointerenter", () => showLevel(l));
          btn.addEventListener("focus", () => showLevel(l));
          btn.addEventListener("pointerleave", () => showLevel(first));
          btn.addEventListener("blur", () => showLevel(first));
          return btn;
        }));
    }
    return el("div", { class: "pick" + (levels ? " has-lv" : "") }, main, energy, levels);
  }

  // ---------- calculator: rows & state ----------
  const rowId = (r) => r.key + "|" + r.level + "|" + (r.use || []).join("~");

  function addRow(key, level, count) {
    const b = byKey.get(key);
    const row = { key, level, count, use: defaultUse(levelOf(b, level) || b.levels[0]) };
    const hit = state.rows.find((r) => rowId(r) === rowId(row));
    if (hit) hit.count += count; else state.rows.push(row);
    update();
  }

  // A select for each either-or group: "Uses: Water / Super coolant", "Makes: Consumables / Mech ammo".
  function choiceSelects(b, l, row) {
    const pick = validUse(l, row.use);
    return choices(l).map((c, i) => {
      const rates = c.kind === "in" ? l.consumes : l.produces;
      const label = c.kind === "liquid" ? "Liquid" : c.kind === "in" ? "Uses" : "Makes";
      const sel = el("select", { class: "alt", "aria-label": `${b.name}: ${c.kind === "liquid" ? "liquid" : c.kind === "in" ? "resource used" : "resource made"}` },
        ...c.g.map((r) => el("option", { value: r, selected: r === pick[i],
          text: c.kind === "liquid" ? resName(r) : `${resName(r)} ${fmt(rates[r])}/s` })));
      sel.addEventListener("change", () => { row.use = pick.slice(); row.use[i] = sel.value; mergeDupes(); update(); });
      return el("label", { class: "alt-wrap" }, el("span", { text: label }), sel);
    });
  }

  function renderRows() {
    const box = document.getElementById("rows");
    if (!state.rows.length) {
      box.replaceChildren(el("div", { class: "empty", text: "No buildings yet. Pick some from the list, or load the example base." }));
      return;
    }
    box.replaceChildren(...state.rows.map((row, i) => {
      const b = byKey.get(row.key);
      const l = levelOf(b, row.level) || b.levels[0];
      const e = energyNet(l) * row.count;
      const lvl = el("select", { class: "lvl", "aria-label": "Level of " + b.name, disabled: b.levels.length < 2 },
        ...b.levels.map((x) => el("option", { value: x.level, selected: x.level === l.level, text: "Lv " + x.level })));
      lvl.addEventListener("change", () => {
        row.level = Number(lvl.value);
        row.use = validUse(levelOf(b, row.level) || b.levels[0], row.use);
        mergeDupes(); update();
      });
      const cnt = el("input", { class: "cnt", type: "number", min: 0, max: b.limit || 9999, value: row.count, "aria-label": "Number of " + b.name });
      cnt.addEventListener("change", () => {
        let n = Math.max(0, Math.floor(Number(cnt.value) || 0));
        if (b.limit) n = Math.min(n, b.limit);
        row.count = n; update();
      });
      const sub = [VARIABLE[b.key], fuelText(l, row.use), b.limit ? "Max " + b.limit : ""].filter(Boolean).join(" · ");
      const alts = choiceSelects(b, l, row);
      return el("div", { class: "row" },
        icon(l.icon), el("div", { class: "nm" }, b.name, sub ? el("small", { text: sub }) : null,
          alts.length ? el("div", { class: "alts" }, ...alts) : null),
        lvl, cnt,
        el("div", { class: "e " + (e > 0 ? "pos" : e < 0 ? "neg" : ""), text: e ? signed(e) : "0" }),
        el("button", { type: "button", class: "rm", "aria-label": "Remove " + b.name, text: "×", onclick: () => { state.rows.splice(i, 1); update(); } }));
    }));
  }

  function mergeDupes() {
    const seen = new Map();
    state.rows = state.rows.filter((r) => {
      const k = rowId(r);
      if (seen.has(k)) { seen.get(k).count += r.count; return false; }
      seen.set(k, r); return true;
    });
  }

  function totals() {
    const t = { prod: 0, cons: 0, night: 0, storage: 0, res: {}, deposits: {}, cost: {} };
    for (const row of state.rows) {
      const b = byKey.get(row.key);
      const l = levelOf(b, row.level) || b.levels[0];
      const x = effective(l, row.use);
      const n = row.count;
      const p = (x.produces.energy || 0) * n;
      t.prod += p;
      if (b.key === "buildings/energy/solar_panels") t.night -= p;
      t.cons += (x.consumes.energy || 0) * n;
      t.storage += (l.energy_storage || 0) * n;
      for (const [r, v] of Object.entries(x.consumes)) if (r !== "energy") t.res[r] = (t.res[r] || 0) - v * n;
      for (const [r, v] of Object.entries(x.produces)) if (r !== "energy") t.res[r] = (t.res[r] || 0) + v * n;
      for (const r of x.requires) t.deposits[r] = (t.deposits[r] || 0) + n;
      for (const [r, v] of Object.entries(l.cost)) t.cost[r] = (t.cost[r] || 0) + v * n;
    }
    t.net = t.prod - t.cons;
    t.night += t.net;
    return t;
  }

  function renderSummary(t) {
    const ok = t.net >= 0;
    const tile = (k, v, cls, extra) => el("div", { class: "sum " + (cls || "") }, el("div", { class: "k", text: k }), el("div", { class: "v", text: v }), extra || null);
    const hasSolar = state.rows.some((r) => r.key === "buildings/energy/solar_panels" && r.count);
    const pct = t.prod ? Math.min(100, (t.cons / t.prod) * 100) : (t.cons ? 100 : 0);
    const fill = el("div", { class: "meter-fill" + (t.cons > t.prod ? " over" : "") });
    fill.style.width = pct + "%";
    setKids(document.getElementById("summary"),
      tile("Produced", fmt(t.prod) + "/s"),
      tile("Consumed", fmt(t.cons) + "/s"),
      tile("Net balance", signed(t.net) + "/s", "net " + (state.rows.length ? (ok ? "ok" : "short") : ""),
        state.rows.length ? el("div", { class: "s " + (ok ? "pos" : "neg"), text: ok ? "✓ Surplus" : "✕ Deficit" }) : null),
      hasSolar ? tile("At night (no solar)", signed(t.night) + "/s", "net " + (t.night >= 0 ? "ok" : "short"),
        el("div", { class: "s " + (t.night >= 0 ? "pos" : "neg"), text: t.night >= 0 ? "✓ Still powered" : "✕ Runs on storage" })) : null,
      tile("Energy storage", fmt(t.storage)),
      el("div", { class: "meter" },
        el("div", { class: "meter-bar", role: "img", "aria-label": `Consumption is ${Math.round(t.prod ? (t.cons / t.prod) * 100 : 0)}% of production` }, fill),
        el("div", { class: "meter-cap" }, el("span", { text: "Grid load" }),
          el("span", { text: t.prod ? Math.round((t.cons / t.prod) * 100) + "% of production" : "no production" }))),
    );
  }

  function renderExtras(t) {
    const box = document.getElementById("extras");
    const blocks = [];
    const res = Object.entries(t.res).filter(([, v]) => v);
    if (res.length) {
      blocks.push(el("div", {}, el("h3", { text: "Other resources per second" }),
        el("table", {}, el("tbody", {}, ...res.sort((a, z) => a[1] - z[1]).map(([r, v]) =>
          el("tr", {}, el("td", {}, resLabel(r)), el("td", { class: "num " + (v > 0 ? "pos" : "neg"), text: signed(v) }))))),
        res.some(([r]) => r.endsWith("_compressed"))
          ? el("p", { class: "note", text: "Compressed liquids are shipped between bases through the rift. A decompressor draws them from that shared stock, and a compressor adds to it." })
          : null));
    }
    const deps = Object.entries(t.deposits);
    if (deps.length) {
      blocks.push(el("div", {}, el("h3", { text: "Deposits to build on" }),
        el("table", {}, el("tbody", {},
          ...deps.map(([r, n]) => el("tr", {}, el("td", {}, resLabel(r)), el("td", { class: "num", text: "× " + n })))))));
    }
    const cost = Object.entries(t.cost);
    if (cost.length) {
      blocks.push(el("div", {}, el("h3", { text: "Total build cost" }),
        el("table", {}, el("tbody", {}, ...cost.sort((a, z) => z[1] - a[1]).map(([r, v]) =>
          el("tr", {}, el("td", {}, resLabel(r)), el("td", { class: "num", text: fmt(v) }))))),
        el("p", { class: "note", text: "Cost of building each at its listed level from scratch." })));
    }
    box.replaceChildren(...blocks);
  }

  // ---------- URL state ----------
  // #b=energy/solar_panels.2.8,energy/fusion_powerplant.1.2.supercoolant
  // building.level.count, then the chosen option of each either-or group (joined by ~) when not the default.
  const short = (k) => k.replace(/^buildings\//, "");
  function writeHash() {
    const s = state.rows.filter((r) => r.count > 0).map((r) => {
      const l = levelOf(byKey.get(r.key), r.level);
      const use = validUse(l, r.use);
      const custom = use.join("~") !== defaultUse(l).join("~");
      return `${short(r.key)}.${r.level}.${r.count}` + (custom ? "." + use.join("~") : "");
    }).join(",");
    history.replaceState(null, "", s ? "#b=" + s : location.pathname + location.search);
  }
  function readHash() {
    const m = location.hash.match(/^#b=(.+)$/);
    if (!m) return [];
    return decodeURIComponent(m[1]).split(",").map((part) => {
      const [k, lv, n, u] = part.split(".");
      const key = "buildings/" + k;
      const b = byKey.get(key);
      if (!b) return null;
      const level = levelOf(b, Number(lv)) ? Number(lv) : b.levels[0].level;
      const count = Math.max(0, Math.min(b.limit || 9999, Math.floor(Number(n) || 1)));
      const use = validUse(levelOf(b, level), u ? u.split("~") : null);
      return { key, level, count, use };
    }).filter(Boolean);
  }

  function update() {
    renderRows();
    const t = totals();
    renderSummary(t);
    renderExtras(t);
    if (state.rows.length || location.hash.startsWith("#b=")) writeHash();
  }

  function toast(msg) {
    const n = el("div", { class: "toast", role: "status", text: msg });
    document.body.append(n);
    setTimeout(() => n.remove(), 1800);
  }

  function initCalculator() {
    document.getElementById("search").addEventListener("input", (e) => { state.q = e.target.value; renderPicker(); });
    document.getElementById("load-example").addEventListener("click", () => {
      state.rows = EXAMPLE.filter(([k]) => byKey.has(k)).map(([key, level, count]) =>
        ({ key, level, count, use: defaultUse(levelOf(byKey.get(key), level)) }));
      update();
    });
    document.getElementById("clear-all").addEventListener("click", () => { state.rows = []; update(); });
    document.getElementById("copy-link").addEventListener("click", async () => {
      writeHash();
      try { await navigator.clipboard.writeText(location.href); toast("Link copied"); }
      catch (e) { toast("Copy failed. Use the address bar."); }
    });
    window.addEventListener("hashchange", () => { state.rows = readHash(); update(); });
    state.rows = readHash();
    renderCatFilter();
    renderPicker();
    update();
  }

  // ---------- boot ----------
  initTheme();
  fetch("data/energy.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((data) => {
      DATA = data;
      for (const b of data.buildings) byKey.set(b.key, b);
      renderStats();
      initLevelToggle();
      renderChart();
      initCalculator();
    })
    .catch((err) => {
      document.querySelector("main").prepend(el("div", { class: "wrap" }, el("p", { class: "panel" },
        "Could not load data/energy.json (" + err.message + "). Open this page through a local web server, not by double-clicking the file.")));
    });
})();
