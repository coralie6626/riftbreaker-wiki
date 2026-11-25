"""Build the small data files the website loads, from the full exports in riftbreaker_data/.

Usage:
    python tools/build_site_data.py [riftbreaker_data] [data]

Writes data/energy.json: every building that produces, consumes or stores energy,
grouped by building with one entry per upgrade level.
Writes data/defense.json: every defense tower with damage type, range and weapon stats per level.
Writes data/enemies.json: every creature with health, attacks, resistances and biomes per tier.
"""
import json
import os
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "riftbreaker_data"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data"

LEVEL_RE = re.compile(r"_lvl_(\d+)$")
# Order the calculator lists categories in.
CATEGORY_ORDER = ["energy", "main", "resources", "defense", "megastructures", "tools", "decorations"]


def load(name):
    with open(os.path.join(SRC, name), encoding="utf-8") as f:
        return json.load(f)


def energy_storage(b):
    return sum(s.get("max") or 0 for s in (b.get("storage") or []) if s.get("resource") == "energy")


def rates(d, skip=()):
    """Per-second rates, minus placeholder ('null' = player-chosen liquid) and zero entries."""
    return {r: v for r, v in (d or {}).items() if r != "null" and r not in skip and v}


def relevant(b):
    """Buildings the calculator lists: anything touching energy, plus liquid handling buildings
    (pumps, compressors, decompressors) that supply fuel to power plants."""
    return ("energy" in (b.get("produces") or {})
            or "energy" in (b.get("consumes") or {})
            or energy_storage(b) > 0
            or bool(b.get("consumes_any") or b.get("produces_any")))


def main():
    buildings = load("buildings.json")
    loc = load("localization_en.json")
    resources = {r["id"]: r for r in load("resources.json")}
    # Veins and vents are map deposits a building sits on, not resources it uses up per second.
    deposits = {rid for rid, r in resources.items() if r.get("type") == "vein"}
    # Liquids (resource group "local"), in the game's own order. Their compressed forms are not
    # defined in any data file; the game names them "<liquid>_compressed".
    liquids = sorted((rid for rid, r in resources.items() if r.get("type") == "local"),
                     key=lambda rid: int(resources[rid].get("order") or 999))
    # Pools a Liquid Pump can sit on: liquid id -> deposit id.
    pools = {r["ore"]: rid for rid, r in resources.items()
             if r.get("type") == "vein" and r.get("specific_type") == "local" and r.get("ore") in liquids}

    picked = [b for b in buildings if b.get("category") and b["category"] != "consumable" and relevant(b)]

    # Drop event/unused copies: not in any research tree, and sharing a name with one that is.
    researched_names = {b["name"] for b in picked if b.get("unlocked_by_research")}
    picked = [b for b in picked if b.get("unlocked_by_research") or b["name"] not in researched_names]

    groups = {}
    for b in picked:
        m = LEVEL_RE.search(b["id"])
        base = b["id"][: m.start()] if m else b["id"]
        level = int(m.group(1)) if m else 1
        cost = (b.get("costs") or {}).get("default") or {}
        groups.setdefault(base, []).append({
            "id": b["id"],
            "level": level,
            "icon": b.get("icon"),
            "produces": rates(b.get("produces")),
            "consumes": rates(b.get("consumes"), skip=deposits),
            # Several deposits listed means the building can sit on any one of them
            # (Rare Element Mine), and then makes only that deposit's resource.
            "requires": [r for r in (b.get("consumes") or {}) if r in deposits],
            # Groups of alternatives: the building uses / makes only one resource of each group.
            "consumes_one_of": [g for g in (b.get("consumes_one_of") or []) if not set(g) & deposits],
            "produces_one_of": b.get("produces_one_of") or [],
            # Outputs the building can make but does not need to get rid of to keep running.
            "optional_outputs": b.get("optional_outputs") or [],
            # Flows naming a resource group rather than one resource; the player picks the liquid
            # in game, and in and out carry the same one (see liquid_io in energy.json).
            "group_io": [{"kind": "in", "group": g["group"], "value": g.get("value")} for g in b.get("consumes_any") or []]
                        + [{"kind": "out", "group": g["group"], "value": g.get("value")} for g in b.get("produces_any") or []],
            "energy_storage": energy_storage(b),
            "cost": {r: v for r, v in (cost.get("cost") or {}).items() if r != "null"},
            "build_time": cost.get("build_time"),
            "_b": b,
        })

    out_buildings = []
    resource_ids = set()
    if any(l["group_io"] for ls in groups.values() for l in ls):
        resource_ids.update(liquids, (x + "_compressed" for x in liquids), pools.values())
    for base, levels in groups.items():
        levels.sort(key=lambda l: l["level"])
        first = levels[0]["_b"]
        for l in levels:
            resource_ids.update(l["produces"], l["consumes"], l["requires"], l["cost"])
            del l["_b"]
        out_buildings.append({
            "key": base,
            "name": first["name"],
            "category": first["category"],
            "description": first.get("description") or "",
            "limit": first.get("limit"),
            "in_research_tree": bool(first.get("unlocked_by_research")),
            "levels": levels,
        })

    def sort_key(b):
        cat = b["category"]
        return (CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER), b["name"].lower())

    out_buildings.sort(key=sort_key)

    def resource_name(rid):
        own = (resources.get(rid) or {}).get("localization_id")
        return loc.get(own or "") or loc.get("resource_name/" + rid) or rid.replace("_", " ").capitalize()

    def resource_icon(rid):
        base = rid[: -len("_compressed")] if rid.endswith("_compressed") else rid
        icon = (resources.get(rid) or resources.get(base) or {}).get("icon")
        if icon and os.path.exists(os.path.join(SRC, "icons", icon + ".png")):
            return icon
        return None

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "energy.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Generated by tools/build_site_data.py from riftbreaker_data/buildings.json",
            "units": "Resource rates are per second.",
            # `ore`: for deposits, the resource mined from them (links a Rare Element Mine's vein to its output).
            "resources": {r: {"name": resource_name(r), "icon": resource_icon(r),
                              **({"ore": resources[r].get("ore")} if r in deposits and resources[r].get("ore") else {})}
                          for r in sorted(resource_ids)},
            # How a building's group flows map to resources for a chosen liquid X:
            # group "local" -> X, "local_compressed" -> X_compressed, "vein" -> the pool of X (a deposit).
            "liquid_io": {"liquids": liquids, "pools": pools},
            "buildings": out_buildings,
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {path}: {len(out_buildings)} buildings, {sum(len(b['levels']) for b in out_buildings)} levels")


def stat(w, key):
    v = ((w or {}).get("stats") or {}).get(key) or {}
    return v.get("max_value", v.get("default_value"))


def defense():
    """Towers in the research tree, one entry per tower with its levels."""
    buildings = load("buildings.json")
    loc = load("localization_en.json")
    resources = {r["id"]: r for r in load("resources.json")}
    towers = [b for b in buildings
              if b["id"].startswith("buildings/defense/tower") and b.get("unlocked_by_research") and b.get("turret")]

    def ammo(rid):
        if not rid:
            return None
        r = resources.get(rid) or {}
        name = re.sub(r"<[^>]+>", "", loc.get(r.get("localization_id") or "", "")).strip()
        icon = r.get("icon")
        if not (icon and os.path.exists(os.path.join(SRC, "icons", icon + ".png"))):
            icon = None
        return {"id": rid, "name": name or rid.replace("_", " ").capitalize(), "icon": icon}

    groups = {}
    for b in towers:
        m = LEVEL_RE.search(b["id"])
        base = b["id"][: m.start()] if m else b["id"]
        level = int(m.group(1)) if m else 1
        w, t = b.get("weapon"), b["turret"]
        spawned = t.get("spawned_attack") or {}
        cost = (b.get("costs") or {}).get("default") or {}
        groups.setdefault(base, []).append({
            "id": b["id"],
            "level": level,
            "icon": b.get("icon"),
            # Drone and mine towers have no weapon of their own: their numbers are the drone's / mine's.
            "damage_type": (w or {}).get("damage_type") or spawned.get("damage_type"),
            "damage": stat(w, "DAMAGE_VALUE") if w else spawned.get("damage"),
            "fire_rate": stat(w, "FIRE_RATE") if w else spawned.get("fire_rate"),
            "projectiles": stat(w, "FIRE_PER_SHOT"),
            # Beam weapons (flamers, lasers) damage continuously and have no fire rate.
            "beam": stat(w, "BEAM_RANGE") is not None and stat(w, "FIRE_RATE") is None,
            "splash": stat(w, "DAMAGE_SPLASH") if w else spawned.get("splash"),
            "dot": stat(w, "DAMAGE_OVER_TIME"),
            "dot_length": stat(w, "DAMAGE_OVER_TIME_LENGTH"),
            "stun": stat(w, "AMMO_STUN_LENGTH"),
            "range_min": t.get("range_min") or 0,
            "range_max": t.get("range_max"),
            "targets": t.get("targets") or [],
            "air": "air_unit" in (t.get("targets") or []),
            "ammo": ammo((w or {}).get("ammo_storage") if (w or {}).get("ammo_storage") != "energy" else None),
            "energy": (b.get("consumes") or {}).get("energy"),
            "health": b.get("max_health"),
            "cost": {r: v for r, v in (cost.get("cost") or {}).items() if r != "null"},
            "build_time": cost.get("build_time"),
        })

    out = []
    for base, levels in groups.items():
        levels.sort(key=lambda l: l["level"])
        first = next(b for b in towers if b["id"] == levels[0]["id"])
        spawns = (first["turret"] or {}).get("spawns")
        out.append({
            "key": base,
            "name": first["name"],
            "description": first.get("description") or "",
            "kind": "mines" if spawns and "mine" in spawns else "drones" if spawns else "turret",
            # Floating towers are placed on water.
            "water": "_water_" in base,
            "levels": levels,
        })
    out.sort(key=lambda b: b["name"].lower())

    res_ids = sorted({r for b in out for l in b["levels"] for r in l["cost"]})
    path = os.path.join(OUT, "defense.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Generated by tools/build_site_data.py from riftbreaker_data/buildings.json",
            "units": "Range in meters (game units). Fire rate is shots per second. Energy is per second.",
            "damage_types": {d: loc.get("gui/menu/inventory/stat_name/damage_type_" + d, d).replace(" damage", "")
                             for d in sorted({l["damage_type"] for b in out for l in b["levels"] if l["damage_type"]})},
            "resources": {r: {"name": loc.get((resources.get(r) or {}).get("localization_id") or "")
                              or loc.get("resource_name/" + r) or r.capitalize(),
                              "icon": (resources.get(r) or {}).get("icon")} for r in res_ids},
            "towers": out,
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {path}: {len(out)} towers")


TIER_RE = re.compile(r"_(alpha|ultra)$")
DAMAGE_TYPES = ["physical", "fire", "acid", "cryo", "energy", "area"]


def enemies():
    """Creatures grouped with their Alpha / Ultra tiers, with resistances, attacks and biomes."""
    units = {u["id"]: u for u in load("enemies.json")}
    loc = load("localization_en.json")
    families = {f["name"]: f for f in load("enemy_families.json")}
    biomes = load("biomes.json")
    species_biomes = {}
    for b in biomes:
        for sp in b.get("creature_species") or []:
            species_biomes.setdefault(sp, set()).add(b["id"])

    def tier_data(u):
        # Melee damage sits on the spawnable unit, the ranged weapon often only on its "_base" blueprint.
        base = units.get(u["id"] + "_base") or {}
        w = u.get("ranged_weapon") or base.get("ranged_weapon")
        melee, seen = [], set()
        for d in u.get("melee_damage") or base.get("melee_damage") or []:
            k = (d.get("type"), d.get("value"))
            if k not in seen and d.get("value"):
                seen.add(k)
                melee.append({"type": d.get("type"), "value": d.get("value")})
        res = u.get("resistances") or base.get("resistances") or {}
        species = sorted(set(u.get("species") or []) | set(base.get("species") or []))
        return {
            "id": u["id"],
            "health": u.get("max_health"),
            "regen": u.get("health_regen") or 0,
            "res": {d: res[d] for d in DAMAGE_TYPES if d in res},
            "reflect": res.get("reflect_damage_max_percent"),
            "melee": melee,
            "ranged": {
                "type": w.get("damage_type"),
                "damage": stat(w, "DAMAGE_VALUE"),
                "rate": stat(w, "FIRE_RATE"),
                "splash": stat(w, "DAMAGE_SPLASH"),
                "projectiles": stat(w, "FIRE_PER_SHOT"),
            } if w and stat(w, "DAMAGE_VALUE") else None,
            "species": species,
        }

    # Spawnable, named units: skip "_base" templates, debug sponges and eggs.
    named = [u for u in units.values() if u.get("name") and not u["id"].endswith("_base")
             and not u["id"].endswith("_easy")]
    groups = {}
    for u in named:
        m = TIER_RE.search(u["id"])
        key = u["id"][: m.start()] if m else u["id"]
        tier = m.group(1) if m else "normal"
        groups.setdefault(key, {})[tier] = u

    # Bestiary portraits (tools/extract_creature_images.py). A few creatures use another name for theirs.
    img_dir = os.path.join(SRC, "icons", "gui", "menu", "species")
    img_alias = {"arachnoid_sentinel_crystal": "arachnoid_crystal", "gnerot_burning_fight": "gnerot_boss",
                 "creeper_root": "creeper", "hedroner_morphium": "hedroner_metallic",
                 "spawner_swamp_stickrid": "spawner_swamp", "spawner_wingmite": "spawner_metallic"}

    def image(short, tier, category):
        name = img_alias.get(short, short)
        cats = [category] + [c for c in ("fauna", "fauna_neutral", "other") if c != category]
        for suffix in ([f"_{tier}"] if tier != "normal" else []) + [""]:
            for c in cats:
                if c and os.path.exists(os.path.join(img_dir, c, name + suffix + ".webp")):
                    return f"{SRC}/icons/gui/menu/species/{c}/{name}{suffix}.webp".replace("\\", "/")
        return None

    out = []
    for key, tiers in groups.items():
        first = tiers.get("normal") or next(iter(tiers.values()))
        fam = families.get(first.get("family")) or {}
        # Alpha / Ultra names carry the tier ("Canoptrix Alpha"); some don't, so strip it for the group name.
        name = re.sub(r"\s+(Alpha|Ultra)$", "", first["name"]).replace("�", "–").strip()
        short = key.split("/")[-1]
        levels = [{"tier": t, **tier_data(tiers[t]), "image": image(short, t, fam.get("category"))}
                  for t in ("normal", "alpha", "ultra") if t in tiers]
        species = sorted({s for l in levels for s in l["species"]})
        kind = "boss" if "boss" in short or "burning_fight" in short else \
            "nest" if short.startswith("spawner") or "creeper_root" in short else \
            "structure" if short.startswith("alien_tower") else "creature"
        desc = re.sub(r"<[^>]+>", "", fam.get("description_text") or loc.get("monster_description/" + short, "") or "").strip()
        out.append({
            "key": short,
            "name": name,
            "family": first.get("family"),
            "category": fam.get("category"),  # fauna (hostile), fauna_neutral, flora, other
            "air": first["kind"] == "air",
            "kind": kind,
            "description": desc,
            "biomes": sorted({b for s in species for b in species_biomes.get(s, ())}),
            "levels": levels,
        })

    # Same creature exported under several ids (story / research-mission copies): keep the one seen in biomes.
    by_name = {}
    for e in out:
        k = (e["name"], e["kind"])
        cur = by_name.get(k)
        score = (bool(e["biomes"]), len(e["levels"]), -len(e["key"]))
        if not cur or score > cur[0]:
            by_name[k] = (score, e)
    out = sorted((e for _, e in by_name.values()), key=lambda e: e["name"].lower())

    path = os.path.join(OUT, "enemies.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "source": "Generated by tools/build_site_data.py from riftbreaker_data/enemies.json",
            "units": "Resistances are damage multipliers: 2 = takes double damage, 0.1 = takes 10%.",
            "damage_types": {d: loc.get("gui/menu/inventory/stat_name/damage_type_" + d, d).replace(" damage", "")
                             for d in DAMAGE_TYPES},
            "biomes": {b["id"]: b.get("name") or b["id"] for b in biomes},
            "enemies": out,
        }, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote {path}: {len(out)} enemies")


if __name__ == "__main__":
    main()
    defense()
    enemies()
