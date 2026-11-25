// Defense tower finder: filter towers by damage type, range and air targeting.
// Data: data/defense.json (built by tools/build_site_data.py).
(function () {
  "use strict";
  const ICONS = "riftbreaker_data/icons/";
  const RANGE_MAX = 200; // longest tower range in game (Heavy Artillery level 3); fixed so bars compare across levels
  const TYPE_ORDER = ["physical", "fire", "acid", "cryo", "energy", "area"];

  let DATA = null;
  const state = { q: "", types: new Set(), reach: 0, air: false, nomin: false, noammo: false, level: 1, sort: "range", open: null };

  const $ = (id) => document.getElementById(id);

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat(Infinity)) if (c != null && c !== false) n.append(c);
    return n;
  }
  function icon(path, alt, cls) {
    if (!path) return null;
    const img = el("img", { src: ICONS + path + ".png", alt: alt || "", loading: "lazy", class: cls });
    img.addEventListener("error", () => img.remove());
    return img;
  }
  const fmt = (v) => v == null ? "—" : (Math.round(v * 100) / 100).toLocaleString();

  // ---------- theme (shared key with the main page) ----------
  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem("theme"); } catch (e) { /* storage blocked */ }
    if (saved) document.documentElement.dataset.theme = saved;
    $("theme-toggle").addEventListener("click", () => {
      const cur = document.documentElement.dataset.theme ||
        (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) { /* ignore */ }
    });
  }

  // ---------- data helpers ----------
  function lvl(t) {
    return t.levels.find((l) => l.level === state.level) || t.levels[t.levels.length - 1];
  }
  function typeName(d) { return (DATA.damage_types[d] || d || "Unknown"); }
  function searchText(t) {
    const l = t.levels[0];
    return [t.name, t.description, typeName(l.damage_type), l.ammo && l.ammo.name, t.kind,
      t.water ? "water floating" : "", l.air ? "air anti-air aa" : ""].join(" ").toLowerCase();
  }

  function filtered() {
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    const list = DATA.towers.filter((t) => {
      const l = lvl(t);
      if (state.types.size && !state.types.has(l.damage_type)) return false;
      if ((l.range_max || 0) < state.reach) return false;
      if (state.air && !l.air) return false;
      if (state.nomin && l.range_min > 0) return false;
      if (state.noammo && l.ammo) return false;
      const hay = t._search;
      return words.every((w) => hay.includes(w));
    });
    const by = {
      range: (a, b) => (lvl(b).range_max || 0) - (lvl(a).range_max || 0),
      damage: (a, b) => (lvl(b).damage || 0) - (lvl(a).damage || 0),
      type: (a, b) => TYPE_ORDER.indexOf(lvl(a).damage_type) - TYPE_ORDER.indexOf(lvl(b).damage_type),
      energy: (a, b) => (lvl(a).energy || 0) - (lvl(b).energy || 0),
      name: () => 0,
    }[state.sort];
    return list.sort((a, b) => by(a, b) || a.name.localeCompare(b.name));
  }

  // ---------- render ----------
  function renderTypeChips() {
    const counts = {};
    DATA.towers.forEach((t) => { const d = t.levels[0].damage_type; counts[d] = (counts[d] || 0) + 1; });
    const box = $("d-types");
    box.replaceChildren(...TYPE_ORDER.filter((d) => counts[d]).map((d) =>
      el("button", {
        type: "button", class: "chip d-chip", "data-type": d, "aria-pressed": String(state.types.has(d)),
        onclick: () => { state.types.has(d) ? state.types.delete(d) : state.types.add(d); update(); },
      }, el("span", { class: "dt-dot dt-" + d, "aria-hidden": "true" }), typeName(d) + " ",
        el("span", { class: "chip-n", text: String(counts[d]) }))));
  }

  function rangeBar(l) {
    const min = l.range_min || 0, max = l.range_max || 0;
    const bar = el("div", { class: "rb", role: "img",
      "aria-label": min ? `Range ${min} to ${max} meters` : `Range up to ${max} meters` });
    bar.append(
      el("span", { class: "rb-fill dt-bg-" + l.damage_type, style: `left:${min / RANGE_MAX * 100}%;width:${(max - min) / RANGE_MAX * 100}%` }),
      min ? el("span", { class: "rb-dead", style: `width:${min / RANGE_MAX * 100}%`, title: `Can't hit enemies closer than ${min} m` }) : null);
    return el("div", { class: "d-range-cell" }, bar,
      el("span", { class: "rb-val" }, el("b", { text: String(max) }), " m", min ? el("small", { text: ` (min ${min})` }) : null));
  }

  function rateText(t, l) {
    if (l.beam) return "beam";
    if (t.kind === "mines") return "mines";
    if (l.fire_rate == null) return "—";
    return fmt(l.fire_rate) + "/s";
  }

  function row(t) {
    const l = lvl(t);
    const open = state.open === t.key;
    const head = el("button", {
      type: "button", class: "d-row", "aria-expanded": String(open), "aria-controls": "dd-" + t.key.replace(/\W/g, "_"),
      onclick: () => { state.open = open ? null : t.key; update(false); },
    },
      icon(l.icon, "", "d-ico"),
      el("span", { class: "d-name" }, el("span", { class: "nm", text: t.name }),
        el("span", { class: "d-tags" },
          t.kind !== "turret" ? el("span", { class: "tag", text: t.kind === "drones" ? "Drones" : "Mine layer" }) : null,
          t.water ? el("span", { class: "tag", text: "On water" }) : null,
          l.ammo ? el("span", { class: "tag tag-ammo", title: "Uses " + l.ammo.name + " tower ammo" },
            icon(l.ammo.icon, ""), l.ammo.name + " ammo") : null)),
      el("span", { class: "dt-badge dt-bg-" + l.damage_type, text: typeName(l.damage_type) }),
      rangeBar(l),
      el("span", { class: "d-stats" },
      el("span", { class: "d-stat" }, el("small", { text: "Damage" }), el("b", { text: fmt(l.damage ?? l.dot) }),
        l.damage == null && l.dot ? el("small", { text: " DoT" }) : null),
      el("span", { class: "d-stat" }, el("small", { text: "Rate" }), el("b", { text: rateText(t, l) })),
      el("span", { class: "d-stat" }, el("small", { text: "Energy" }), el("b", { text: l.energy ? fmt(l.energy) + "/s" : "—" })),
      el("span", { class: "d-air " + (l.air ? "yes" : "no"), title: l.air ? "Targets air units" : "Ground only" },
        l.air ? "✈ Air" : "Ground")));

    const items = [];
    items.push(el("p", { class: "d-desc", text: t.description }));
    const facts = [
      ["Range", (l.range_min ? `${l.range_min}–` : "") + `${l.range_max} m`],
      ["Damage per hit", fmt(l.damage)],
      l.projectiles > 1 ? ["Projectiles per shot", fmt(l.projectiles)] : null,
      l.splash ? ["Splash radius", fmt(l.splash) + " m"] : null,
      l.dot ? ["Damage over time", fmt(l.dot) + (l.dot_length ? ` for ${fmt(l.dot_length)} s` : "")] : null,
      l.stun ? ["Stun", fmt(l.stun) + " s"] : null,
      ["Health", fmt(l.health)],
      ["Build time", l.build_time != null ? fmt(l.build_time) + " s" : "—"],
    ].filter(Boolean);
    items.push(el("dl", { class: "d-facts" }, facts.map(([k, v]) => [el("dt", { text: k }), el("dd", { text: v })])));
    const cost = Object.entries(l.cost || {});
    if (cost.length) {
      items.push(el("div", { class: "d-cost" }, el("span", { class: "lv-k", text: "Cost" }),
        cost.map(([r, v]) => el("span", { class: "res" }, icon((DATA.resources[r] || {}).icon, ""),
          `${fmt(v)} ${(DATA.resources[r] || {}).name || r}`))));
    }
    // Level comparison for the stats that change.
    const lv = el("table", { class: "d-levels" },
      el("thead", {}, el("tr", {}, el("th", { text: "Level" }), el("th", { class: "num", text: "Range" }),
        el("th", { class: "num", text: "Damage" }), el("th", { class: "num", text: "Rate" }), el("th", { class: "num", text: "Energy" }))),
      el("tbody", {}, t.levels.map((x) => el("tr", { class: x.level === l.level ? "cur" : null },
        el("td", { text: String(x.level) }), el("td", { class: "num", text: `${x.range_max} m` }),
        el("td", { class: "num", text: fmt(x.damage ?? x.dot) }), el("td", { class: "num", text: rateText(t, x) }),
        el("td", { class: "num", text: x.energy ? fmt(x.energy) + "/s" : "—" })))));
    items.push(el("div", { class: "table-scroll" }, lv));

    const detail = el("div", { class: "d-detail", id: "dd-" + t.key.replace(/\W/g, "_"), hidden: !open }, items);
    return el("div", { class: "d-item" + (open ? " open" : ""), role: "listitem" }, head, detail);
  }

  function renderList() {
    const list = filtered();
    $("d-count").textContent = `${list.length} of ${DATA.towers.length} towers` + (state.level > 1 ? ` · level ${state.level} stats` : "");
    const scale = el("div", { class: "d-scale", "aria-hidden": "true" },
      el("span"), el("span"), el("span"),
      el("span", { class: "d-scale-axis" }, [0, 50, 100, 150, 200].map((v) =>
        el("span", { style: `left:${v / RANGE_MAX * 100}%`, text: v + (v === 200 ? " m" : "") }))));
    $("d-list").replaceChildren(scale, ...(list.length ? list.map(row)
      : [el("p", { class: "empty", text: "No tower matches these filters." })]));
  }

  // ---------- state <-> controls / URL ----------
  function syncControls() {
    $("d-search").value = state.q;
    $("d-reach").value = state.reach;
    $("d-reach-out").textContent = state.reach;
    $("d-air").checked = state.air;
    $("d-nomin").checked = state.nomin;
    $("d-noammo").checked = state.noammo;
    $("d-sort").value = state.sort;
    document.querySelectorAll("#d-level button").forEach((b) =>
      b.setAttribute("aria-checked", String(+b.dataset.level === state.level)));
    document.querySelectorAll("#d-types .chip").forEach((b) =>
      b.setAttribute("aria-pressed", String(state.types.has(b.dataset.type))));
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.types.size) p.set("type", [...state.types].join(","));
    if (state.reach) p.set("reach", state.reach);
    if (state.air) p.set("air", "1");
    if (state.nomin) p.set("nomin", "1");
    if (state.noammo) p.set("noammo", "1");
    if (state.level !== 1) p.set("lvl", state.level);
    if (state.sort !== "range") p.set("sort", state.sort);
    const h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.q = p.get("q") || "";
    state.types = new Set((p.get("type") || "").split(",").filter((d) => DATA.damage_types[d]));
    state.reach = Math.max(0, Math.min(RANGE_MAX, +p.get("reach") || 0));
    state.air = p.get("air") === "1";
    state.nomin = p.get("nomin") === "1";
    state.noammo = p.get("noammo") === "1";
    state.level = [1, 2, 3].includes(+p.get("lvl")) ? +p.get("lvl") : 1;
    state.sort = ["range", "damage", "type", "name", "energy"].includes(p.get("sort")) ? p.get("sort") : "range";
  }
  function update(hash = true) {
    syncControls();
    renderList();
    if (hash) writeHash();
  }

  function init() {
    initTheme();
    DATA.towers.forEach((t) => { t._search = searchText(t); });
    readHash();
    renderTypeChips();
    $("d-search").addEventListener("input", (e) => { state.q = e.target.value.trim(); update(); });
    $("d-reach").addEventListener("input", (e) => { state.reach = +e.target.value; update(); });
    $("d-air").addEventListener("change", (e) => { state.air = e.target.checked; update(); });
    $("d-nomin").addEventListener("change", (e) => { state.nomin = e.target.checked; update(); });
    $("d-noammo").addEventListener("change", (e) => { state.noammo = e.target.checked; update(); });
    $("d-sort").addEventListener("change", (e) => { state.sort = e.target.value; update(); });
    document.querySelectorAll("#d-level button").forEach((b) =>
      b.addEventListener("click", () => { state.level = +b.dataset.level; update(); }));
    $("d-reset").addEventListener("click", () => {
      Object.assign(state, { q: "", types: new Set(), reach: 0, air: false, nomin: false, noammo: false, sort: "range" });
      update();
    });
    // "/" focuses search, like many wikis.
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); $("d-search").focus(); }
    });
    update(false);
  }

  fetch("data/defense.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { DATA = d; init(); })
    .catch(() => {
      $("d-list").replaceChildren(el("p", { class: "empty",
        text: "Couldn't load data/defense.json. Serve this folder over HTTP (see README) rather than opening the file directly." }));
    });
})();
