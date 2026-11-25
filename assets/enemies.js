// Enemy finder: health, damage and weaknesses for every creature, by tier and biome.
// Data: data/enemies.json (built by tools/build_site_data.py).
(function () {
  "use strict";
  const TYPES = ["physical", "fire", "acid", "cryo", "energy", "area"];
  const TIERS = ["normal", "alpha", "ultra"];
  const TIER_NAME = { normal: "Normal", alpha: "Alpha", ultra: "Ultra" };
  const SHOW = ["hostile", "special", "neutral", "all"];
  const SORTS = ["name", "health", "damage", "weak"];
  const DEFAULTS = { q: "", weak: new Set(), biome: "", show: "hostile", air: false, ranged: false, tier: "normal", sort: "name" };

  let DATA = null;
  const state = { ...DEFAULTS, weak: new Set(), open: null };

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
  const fmt = (v) => v == null ? "—" : (Math.round(v * 100) / 100).toLocaleString();
  // Bestiary portrait, or an empty box of the same size so rows stay aligned.
  function portrait(src, cls, alt) {
    if (!src) return el("span", { class: cls + " e-noimg", "aria-hidden": "true" });
    const img = el("img", { src, alt: alt || "", loading: "lazy", decoding: "async", class: cls });
    img.addEventListener("error", () => img.replaceWith(el("span", { class: cls + " e-noimg", "aria-hidden": "true" })));
    return img;
  }

  // ---------- theme (shared key with the other pages) ----------
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
  const typeName = (d) => DATA.damage_types[d] || d;
  const biomeName = (b) => (DATA.biomes[b] || b).replace(/ Biome$/, "");
  // The chosen tier, or the closest one the creature has (bosses and nests have one tier).
  function lvl(e) {
    return e.levels.find((l) => l.tier === state.tier) || e.levels[e.levels.length - 1];
  }
  const mult = (l, d) => (l.res[d] == null ? 1 : l.res[d]);
  function hits(l) {
    const out = l.melee.map((m) => ({ ...m, how: "Melee" }));
    if (l.ranged) out.push({ type: l.ranged.type, value: l.ranged.damage, how: "Ranged" });
    return out;
  }
  const maxHit = (l) => Math.max(0, ...hits(l).map((h) => h.value || 0));
  const neutral = (e) => e.category === "fauna_neutral";
  const special = (e) => e.kind !== "creature";

  function searchText(e) {
    return [e.name, e.family, e.key, e.kind, e.description, neutral(e) ? "neutral passive" : "",
      e.air ? "air flying" : "", e.kind === "nest" ? "spawner" : "", e.biomes.map(biomeName).join(" ")]
      .join(" ").toLowerCase();
  }

  function filtered() {
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    const list = DATA.enemies.filter((e) => {
      const l = lvl(e);
      if (state.show === "hostile" && (neutral(e) || special(e))) return false;
      if (state.show === "special" && !special(e)) return false;
      if (state.show === "neutral" && !neutral(e)) return false;
      if (state.biome && !e.biomes.includes(state.biome)) return false;
      if (state.air && !e.air) return false;
      if (state.ranged && !l.ranged) return false;
      for (const d of state.weak) if (mult(l, d) <= 1) return false;
      return words.every((w) => e._search.includes(w));
    });
    // "Biggest weakness" sorts by the selected types when any are picked, else by the creature's top multiplier.
    const weakScore = (l) => state.weak.size
      ? Math.min(...[...state.weak].map((d) => mult(l, d)))
      : Math.max(...TYPES.map((d) => mult(l, d)));
    const by = {
      name: () => 0,
      health: (a, b) => (lvl(b).health || 0) - (lvl(a).health || 0),
      damage: (a, b) => maxHit(lvl(b)) - maxHit(lvl(a)),
      weak: (a, b) => weakScore(lvl(b)) - weakScore(lvl(a)),
    }[state.sort];
    return list.sort((a, b) => by(a, b) || a.name.localeCompare(b.name));
  }

  // ---------- render ----------
  function renderWeakChips() {
    $("e-weak").replaceChildren(...TYPES.map((d) =>
      el("button", {
        type: "button", class: "chip d-chip", "data-type": d, "aria-pressed": String(state.weak.has(d)),
        onclick: () => { state.weak.has(d) ? state.weak.delete(d) : state.weak.add(d); update(); },
      }, el("span", { class: "dt-dot dt-" + d, "aria-hidden": "true" }), typeName(d))));
  }

  function renderBiomes() {
    const used = new Set(DATA.enemies.flatMap((e) => e.biomes));
    const opts = [...used].sort((a, b) => biomeName(a).localeCompare(biomeName(b)))
      .map((b) => el("option", { value: b, text: biomeName(b) }));
    $("e-biome").append(...opts);
  }

  function resCell(l, d) {
    const m = mult(l, d);
    const cls = m > 1 ? "weak" : m < 1 ? "strong" : "even";
    const label = m > 1 ? `takes ${fmt(m)}× ${typeName(d)} damage (weak)`
      : m < 1 ? `takes ${fmt(m)}× ${typeName(d)} damage (resists)` : `normal ${typeName(d)} damage`;
    // The dot labels the column on narrow screens, where the header row is hidden.
    return el("span", { class: "e-res " + cls + (state.weak.has(d) ? " picked" : ""), title: label, "aria-label": label },
      el("span", { class: "dt-dot dt-" + d, "aria-hidden": "true" }), m === 1 ? "·" : "×" + fmt(m));
  }

  function dmgText(l) {
    const h = hits(l);
    return h.length ? h.reduce((a, b) => ((b.value || 0) > (a.value || 0) ? b : a)) : null;
  }

  function row(e) {
    const l = lvl(e);
    const open = state.open === e.key;
    const id = "ed-" + e.key.replace(/\W/g, "_");
    const top = dmgText(l);
    const noRes = !Object.keys(l.res).length;
    const head = el("button", {
      type: "button", class: "d-row e-row", "aria-expanded": String(open), "aria-controls": id,
      onclick: () => { state.open = open ? null : e.key; update(false); },
    },
      portrait(l.image, "e-thumb"),
      el("span", { class: "d-name" }, el("span", { class: "nm", text: e.name }),
        el("span", { class: "d-tags" },
          e.air ? el("span", { class: "tag", text: "✈ Flying" }) : null,
          e.kind === "boss" ? el("span", { class: "tag tag-boss", text: "Boss" }) : null,
          e.kind === "nest" ? el("span", { class: "tag", text: "Nest" }) : null,
          e.kind === "structure" ? el("span", { class: "tag", text: "Tower" }) : null,
          neutral(e) ? el("span", { class: "tag", text: "Neutral" }) : null,
          l.ranged ? el("span", { class: "tag", text: "Ranged" }) : null,
          // Single-tier creatures (bosses, nests) show their only stats whatever tier is picked.
          l.tier !== state.tier ? el("span", { class: "tag", text: "One tier", title: "This creature has no Alpha / Ultra tier" }) : null)),
      el("span", { class: "d-stat e-hp" }, el("small", { text: "Health" }), el("b", { text: fmt(l.health) }),
        l.regen ? el("small", { text: `+${fmt(l.regen)}/s` }) : null),
      el("span", { class: "d-stat e-dmg" }, el("small", { text: "Hit" }),
        top ? el("b", {}, el("span", { class: "dt-dot dt-" + top.type, "aria-hidden": "true" }), fmt(top.value)) : el("b", { text: "—" })),
      noRes ? el("span", { class: "e-resrow e-nores", text: "No resistances" })
        : el("span", { class: "e-resrow" }, TYPES.map((d) => resCell(l, d))));

    const items = [];
    // Portraits of every tier side by side, so Alpha / Ultra variants are easy to tell apart.
    const pics = e.levels.filter((x) => x.image && (x.tier === "normal" || x.image !== e.levels[0].image));
    if (pics.length) {
      items.push(el("div", { class: "e-gallery" }, pics.map((x) =>
        el("figure", { class: x.tier === l.tier ? "cur" : null },
          portrait(x.image, "e-big", `${e.name} ${x.tier === "normal" ? "" : TIER_NAME[x.tier]}`.trim()),
          e.levels.length > 1 ? el("figcaption", { text: TIER_NAME[x.tier] }) : null))));
    }
    if (e.description) items.push(el("p", { class: "d-desc", text: e.description }));
    const facts = [
      ["Biomes", e.biomes.length ? e.biomes.map(biomeName).join(", ") : "Story / events only"],
      ["Health regen", l.regen ? fmt(l.regen) + "/s" : "None"],
      l.reflect ? ["Reflects damage", `up to ${fmt(l.reflect * 100)}%`] : null,
      ["Movement", e.air ? "Flying" : "Ground"],
    ].filter(Boolean);
    items.push(el("dl", { class: "d-facts" }, facts.map(([k, v]) => el("div", {}, el("dt", { text: k }), el("dd", { text: v })))));

    const atk = hits(l);
    if (atk.length) {
      items.push(el("div", { class: "d-cost" }, el("span", { class: "lv-k", text: "Attacks" }),
        atk.map((h) => el("span", { class: "res" }, el("span", { class: "dt-dot dt-" + h.type, "aria-hidden": "true" }),
          `${h.how}: ${fmt(h.value)} ${typeName(h.type)}` +
          (h.how === "Ranged" && l.ranged.rate ? `, ${fmt(l.ranged.rate)}/s` : "") +
          (h.how === "Ranged" && l.ranged.splash ? `, ${fmt(l.ranged.splash)} m splash` : "")))));
    }

    if (e.levels.length > 1) {
      const t = el("table", { class: "d-levels e-levels" },
        el("thead", {}, el("tr", {}, el("th", { text: "Tier" }), el("th", { class: "num", text: "Health" }),
          el("th", { class: "num", text: "Hit" }), TYPES.map((d) => el("th", { class: "num", title: typeName(d) },
            el("span", { class: "dt-dot dt-" + d, "aria-hidden": "true" }), typeName(d).slice(0, 4))))),
        el("tbody", {}, e.levels.map((x) => el("tr", { class: x.tier === l.tier ? "cur" : null },
          el("td", { text: TIER_NAME[x.tier] }), el("td", { class: "num", text: fmt(x.health) }),
          el("td", { class: "num", text: fmt(maxHit(x) || null) }),
          TYPES.map((d) => el("td", { class: "num", text: x.res[d] == null ? "—" : "×" + fmt(x.res[d]) }))))));
      items.push(el("div", { class: "table-scroll" }, t));
    }

    const detail = el("div", { class: "d-detail", id, hidden: !open }, items);
    return el("div", { class: "d-item" + (open ? " open" : ""), role: "listitem" }, head, detail);
  }

  function renderList() {
    const list = filtered();
    $("e-count").textContent = `${list.length} of ${DATA.enemies.length} creatures · ${TIER_NAME[state.tier]} tier`;
    const scale = el("div", { class: "d-scale e-scale", "aria-hidden": "true" },
      el("span"), el("span", { text: "Creature" }), el("span", { text: "Health" }), el("span", { text: "Hit" }),
      el("span", { class: "e-resrow" }, TYPES.map((d) => el("span", { class: "e-res-h" },
        el("span", { class: "dt-dot dt-" + d }), typeName(d)))));
    $("e-list").replaceChildren(scale, ...(list.length ? list.map(row)
      : [el("p", { class: "empty", text: "No creature matches these filters." })]));
  }

  // ---------- state <-> controls / URL ----------
  function syncControls() {
    $("e-search").value = state.q;
    $("e-biome").value = state.biome;
    $("e-show").value = state.show;
    $("e-air").checked = state.air;
    $("e-ranged").checked = state.ranged;
    $("e-sort").value = state.sort;
    document.querySelectorAll("#e-tier button").forEach((b) =>
      b.setAttribute("aria-checked", String(b.dataset.tier === state.tier)));
    document.querySelectorAll("#e-weak .chip").forEach((b) =>
      b.setAttribute("aria-pressed", String(state.weak.has(b.dataset.type))));
  }
  function writeHash() {
    const p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.weak.size) p.set("weak", [...state.weak].join(","));
    if (state.biome) p.set("biome", state.biome);
    if (state.show !== DEFAULTS.show) p.set("show", state.show);
    if (state.air) p.set("air", "1");
    if (state.ranged) p.set("ranged", "1");
    if (state.tier !== DEFAULTS.tier) p.set("tier", state.tier);
    if (state.sort !== DEFAULTS.sort) p.set("sort", state.sort);
    const h = p.toString();
    history.replaceState(null, "", h ? "#" + h : location.pathname + location.search);
  }
  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    state.q = p.get("q") || "";
    state.weak = new Set((p.get("weak") || "").split(",").filter((d) => TYPES.includes(d)));
    state.biome = DATA.biomes[p.get("biome")] ? p.get("biome") : "";
    state.show = SHOW.includes(p.get("show")) ? p.get("show") : DEFAULTS.show;
    state.air = p.get("air") === "1";
    state.ranged = p.get("ranged") === "1";
    state.tier = TIERS.includes(p.get("tier")) ? p.get("tier") : DEFAULTS.tier;
    state.sort = SORTS.includes(p.get("sort")) ? p.get("sort") : DEFAULTS.sort;
  }
  function update(hash = true) {
    syncControls();
    renderList();
    if (hash) writeHash();
  }

  function init() {
    initTheme();
    DATA.enemies.forEach((e) => { e._search = searchText(e); });
    renderWeakChips();
    renderBiomes();
    readHash();
    $("e-search").addEventListener("input", (ev) => { state.q = ev.target.value.trim(); update(); });
    $("e-biome").addEventListener("change", (ev) => { state.biome = ev.target.value; update(); });
    $("e-show").addEventListener("change", (ev) => { state.show = ev.target.value; update(); });
    $("e-air").addEventListener("change", (ev) => { state.air = ev.target.checked; update(); });
    $("e-ranged").addEventListener("change", (ev) => { state.ranged = ev.target.checked; update(); });
    $("e-sort").addEventListener("change", (ev) => { state.sort = ev.target.value; update(); });
    document.querySelectorAll("#e-tier button").forEach((b) =>
      b.addEventListener("click", () => { state.tier = b.dataset.tier; update(); }));
    $("e-reset").addEventListener("click", () => {
      Object.assign(state, { ...DEFAULTS, weak: new Set(), tier: state.tier });
      update();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "/" && !["INPUT", "SELECT"].includes(document.activeElement.tagName)) { ev.preventDefault(); $("e-search").focus(); }
    });
    update(false);
  }

  fetch("data/enemies.json")
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { DATA = d; init(); })
    .catch(() => {
      $("e-list").replaceChildren(el("p", { class: "empty",
        text: "Couldn't load data/enemies.json. Serve this folder over HTTP (see README) rather than opening the file directly." }));
    });
})();
