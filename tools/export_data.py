"""Build wiki-style data tables from extracted Riftbreaker files.

Usage:  python tools/export_data.py [extracted_dir] [output_dir]
Reads only the extracted copy (see extract_text.py); never touches the game folder.
Writes, per category, a full-detail JSON file and a flat CSV summary.
"""
import csv, glob, json, os, re, sys, copy
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import riftparse as rp
from riftparse import to_obj, as_list

SRC = sys.argv[1] if len(sys.argv) > 1 else 'extracted'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'riftbreaker_data'
os.makedirs(OUT, exist_ok=True)
TIERS = ['standard', 'advanced', 'superior', 'extreme']


def D(x):
    return x if isinstance(x, dict) else {}


def P(*parts):
    return os.path.join(SRC, *parts)


def load(path):
    return to_obj(rp.parse_file(path))


# ---------------------------------------------------------------- localization
LOC = {}
for f in sorted(glob.glob(P('gui', '*localizations.csv'))):
    with open(f, encoding='utf-8-sig', newline='') as fh:
        rows = csv.reader(fh, delimiter=';', quoting=csv.QUOTE_NONE)  # files don't use CSV quoting
        header = next(rows, None)
        if not header: continue
        try: en = [h.strip().upper() for h in header].index('ENGLISH')
        except ValueError: en = 1
        for row in rows:
            if len(row) > en and row[0]:
                LOC[row[0].strip().lower()] = row[en].strip()


def L(key):
    if not key or not isinstance(key, str): return None
    k = key.strip().lower()
    return LOC.get(k) or LOC.get('gui/hud/' + k) or LOC.get('gui/menu/' + k)


def clean_text(s):
    if not s: return s
    s = re.sub(r'<[^>]+>', '', s)  # strip markup tags like <style="...">
    return s.replace('\\n', ' ').strip()


# ---------------------------------------------------------------- entities
print('parsing entities ...')
RAW = {}  # name -> raw component dict
for f in glob.glob(P('entities', '**', '*.ent'), recursive=True):
    try:
        top = rp.parse_file(f)
    except Exception as e:
        print('  skip', f, e); continue
    for key, val in top:
        if key != 'EntityBlueprint' or not isinstance(val, list): continue
        obj = to_obj(val)
        name = obj.get('name')
        if isinstance(name, list): name = name[0]
        if isinstance(name, str):
            obj['__file__'] = os.path.relpath(f, SRC).replace('\\', '/')
            RAW[name] = obj

_resolved = {}


def ent(name, _depth=0):
    """Blueprint with base_blueprint inheritance applied (child components replace base ones)."""
    if not name or name not in RAW: return None
    if name in _resolved: return _resolved[name]
    o = RAW[name]
    base = o.get('base_blueprint')
    if isinstance(base, str) and base in RAW and _depth < 20:
        b = ent(base, _depth + 1) or {}
        merged = copy.deepcopy(b)
        merged.update(o)
        merged['__inherits__'] = [base] + b.get('__inherits__', [])
        o = merged
    _resolved[name] = o
    return o


def find_all(obj, key):
    """Yield every value stored under `key` anywhere in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                for x in as_list(v): yield x
            yield from find_all(v, key)
    elif isinstance(obj, list):
        for x in obj: yield from find_all(x, key)


def first(v):
    return v[0] if isinstance(v, list) and v else v


def tier_of(name):
    for t in TIERS:
        if re.search(r'_%s(_|$)' % t, name): return t
    return None


def lua_db(e):
    d = D(e).get('LuaDesc') or {}
    d = first(d) if isinstance(d, list) else d
    return d.get('database') if isinstance(d, dict) and isinstance(d.get('database'), dict) else None


# ---------------------------------------------------------------- tables
T = P('scripts', 'blueprint_tables')
WSTATS = load(os.path.join(T, 'weapon_stats.dat'))
CHARGE = load(os.path.join(T, 'weapon_charge_factors.dat'))
WMODS = load(os.path.join(T, 'weapon_mods.dat'))
EMODS = load(os.path.join(T, 'entity_mods.dat'))
CRAFT = load(os.path.join(T, 'crafting_table.dat')).get('EntityBlueprints', {})


def weapon_stats(bp):
    w = D(WSTATS.get(bp)).get('WeaponItemDesc')
    if not w: return None
    stats = {}
    for s in as_list(D(w.get('stat_def_vec')).get('WeaponStatDef')):
        st = s.get('stat_type')
        if not st: continue
        stats[st] = {k: s[k] for k in ('default_value', 'min_value', 'max_value') if k in s}
        if 'stat_features' in s: stats[st]['features'] = s['stat_features']
    out = {k: v for k, v in w.items() if k != 'stat_def_vec' and v is not True}
    out['stats'] = stats
    return out


def stat_str(st):
    if not st: return ''
    lo, hi, d = st.get('min_value'), st.get('max_value'), st.get('default_value')
    rng = str(lo) if lo == hi else f'{lo}-{hi}'
    return f'{rng} (base {d})' if d is not None and d != lo else rng


def costs_from_cost_desc(cd):
    out = {}
    if not isinstance(cd, dict): return out
    for rc in find_all(cd, 'ResearchCost'):
        if isinstance(rc, dict) and 'resource' in rc:
            out[rc['resource']] = rc.get('count', rc.get('amount'))
    return out


def craft_cost(item):
    return costs_from_cost_desc(D(CRAFT.get(item)).get('CostDesc'))


def cost_str(c):
    return ', '.join(f'{k} {v}' for k, v in c.items()) if c else ''


# research: blueprint -> list of research nodes unlocking it
RESEARCH_NODES = []
UNLOCKED_BY = defaultdict(list)
for f in sorted(glob.glob(P('scripts', 'research', '*.rt'))):
    tree = os.path.splitext(os.path.basename(f))[0]
    data = load(f).get('Research', {})
    for rt in as_list(D(data.get('categories')).get('ResearchTree')):
        cat = rt.get('category')
        for node in as_list(D(rt.get('nodes')).get('ResearchNode')):
            if not isinstance(node, dict): continue
            nm = node.get('research_name')
            costs = {c['resource']: c.get('count') for c in as_list(D(node.get('research_costs')).get('ResearchCost')) if isinstance(c, dict) and 'resource' in c}
            reqs = [r.get('research_name') for r in as_list(D(node.get('requirements')).get('ResearchNodeRequirement')) if isinstance(r, dict)]
            awards = [a.get('blueprint') for a in as_list(D(node.get('research_awards')).get('ResearchAward')) if isinstance(a, dict)]
            rec = {
                'tree': tree, 'category_id': cat, 'category': L(cat), 'id': nm, 'name': L(nm),
                'costs': costs, 'requires': [{'id': r, 'name': L(r)} for r in reqs],
                'unlocks': awards, 'position': node.get('position'), 'icon': node.get('icon'),
            }
            RESEARCH_NODES.append(rec)
            for a in awards:
                UNLOCKED_BY[a].append(f"{tree}: {L(nm) or nm}")

# ---------------------------------------------------------------- helpers for items


def item_record(item_name):
    e = ent(item_name) or {}
    inv = D(first(e.get('InventoryItemDesc')))
    bp = inv.get('item_bp')
    body = ent(bp) if bp else None
    rec = {
        'id': item_name,
        'name': L(inv.get('name')),
        'description': clean_text(L(inv.get('description'))),
        'tier': tier_of(item_name),
        'type': inv.get('type'), 'subtype': inv.get('subtype'),
        'item_blueprint': bp,
        'icon': inv.get('icon'),
        'craft_cost': craft_cost(item_name),
        'unlocked_by_research': UNLOCKED_BY.get(item_name, []) + (UNLOCKED_BY.get(bp, []) if bp else []),
        'stats': weapon_stats(item_name) or weapon_stats(item_name[:-5]) or (weapon_stats(bp) if bp else None),
        'charge_levels': None,
        'item_script_data': lua_db(e),
        'blueprint_script_data': lua_db(body),
        'source_file': e.get('__file__'),
    }
    for key in filter(None, [bp, item_name]):
        cl = CHARGE.get(key) or CHARGE.get(re.sub(r'_(standard|advanced|superior|extreme)$', '', key))
        if cl:
            rec['charge_levels'] = as_list(D(cl.get('Vector_ChargeLevel')).get('ChargeLevel')); break
    mods = D(EMODS.get(item_name)).get('EntityModDesc')
    if mods: rec['entity_mods'] = mods
    if not rec['tier'] and rec['stats'] and rec['stats'].get('rarity'):
        rec['tier'] = str(rec['stats']['rarity']).lower()
    return rec


def items_under(prefix, skip=('debug',)):
    names = sorted(n for n, o in RAW.items() if n.startswith(prefix) and n.endswith('_item')
                   and 'InventoryItemDesc' in o and not any(s in n for s in skip))
    return [item_record(n) for n in names]


def write(name, records, columns):
    with open(os.path.join(OUT, name + '.json'), 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=1, ensure_ascii=False)
    with open(os.path.join(OUT, name + '.csv'), 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow([c for c, _ in columns])
        for r in records:
            row = []
            for _, fn in columns:
                try: v = fn(r)
                except Exception: v = ''
                if isinstance(v, (list, tuple)): v = '; '.join(map(str, v))
                elif isinstance(v, dict): v = cost_str(v)
                row.append('' if v is None else v)
            w.writerow(row)
    print(f'  {name}: {len(records)} rows')


def S(stat):
    return lambda r: stat_str(D(D(r.get('stats')).get('stats')).get(stat))


# ---------------------------------------------------------------- WEAPONS
print('weapons ...')
weapons = items_under('items/weapons/')
write('weapons', weapons, [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('tier', lambda r: r['tier']),
    ('type', lambda r: r['type']), ('subtype', lambda r: r['subtype']),
    ('damage_type', lambda r: D(r['stats']).get('damage_type')),
    ('rarity', lambda r: D(r['stats']).get('rarity')),
    ('ammo', lambda r: D(r['stats']).get('ammo_storage')),
    ('damage', S('DAMAGE_VALUE')), ('fire_rate', S('FIRE_RATE')), ('per_shot', S('FIRE_PER_SHOT')),
    ('per_burst', S('FIRE_PER_BURST')), ('splash', S('DAMAGE_SPLASH')), ('dot', S('DAMAGE_OVER_TIME')),
    ('dot_length', S('DAMAGE_OVER_TIME_LENGTH')), ('crit_chance', S('DAMAGE_CRITICAL_CHANCE')),
    ('crit_factor', S('DAMAGE_CRITICAL_FACTOR')), ('penetration', S('DAMAGE_PENETRATION')),
    ('lifesteal', S('DAMAGE_LIFESTEAL')), ('stun', S('AMMO_STUN')), ('ammo_cost', S('AMMO_COST')),
    ('ammo_speed', S('AMMO_SPEED')), ('spread', S('AMMO_SPREAD')), ('beam_range', S('BEAM_RANGE')),
    ('craft_cost', lambda r: r['craft_cost']), ('unlocked_by', lambda r: r['unlocked_by_research']),
    ('description', lambda r: r['description']),
])

# ---------------------------------------------------------------- SKILLS / CONSUMABLES / UPGRADES
print('skills, consumables, upgrades ...')
skills = items_under('items/skills/')
consumables = items_under('items/consumables/')
upgrades = items_under('items/upgrades/')
generic_cols = [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('tier', lambda r: r['tier']),
    ('type', lambda r: r['type']), ('subtype', lambda r: r['subtype']),
    ('damage_type', lambda r: D(r['stats']).get('damage_type')),
    ('damage', S('DAMAGE_VALUE')), ('splash', S('DAMAGE_SPLASH')), ('dot', S('DAMAGE_OVER_TIME')),
    ('ammo_cost', S('AMMO_COST')),
    ('script_values', lambda r: ', '.join(f'{k}={v}' for k, v in {**D(r['blueprint_script_data']), **D(r['item_script_data'])}.items()
                                          if isinstance(v, (int, float, str)) and not str(v).startswith(('effects/', 'voice_over', 'weapon,', 'vibration')))),
    ('craft_cost', lambda r: r['craft_cost']), ('unlocked_by', lambda r: r['unlocked_by_research']),
    ('description', lambda r: r['description']),
]
write('skills', skills, generic_cols)
write('consumables', consumables, generic_cols)
write('upgrades', upgrades, [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('tier', lambda r: r['tier']),
    ('mods', lambda r: ', '.join(f'{k}={v}' for k, v in D(D(r.get('entity_mods')).get('entity_mods')).items())),
    ('boost_values', lambda r: ', '.join(f'{k}={v}' for k, v in D(D(r.get('entity_mods')).get('boost_values')).items())),
    ('craft_cost', lambda r: r['craft_cost']), ('unlocked_by', lambda r: r['unlocked_by_research']),
    ('description', lambda r: r['description']),
])

wmods = []
for name, d in sorted(WMODS.items()):
    m = D(d.get('WeaponModDesc'))
    e = ent(name) or {}
    inv = D(first(e.get('InventoryItemDesc')))
    wmods.append({'id': name, 'name': L(inv.get('name')) or L('gui/menu/inventory/stat_name/' + str(m.get('stat_type', '')).lower()), 'description': clean_text(L(inv.get('description'))),
                  'tier': tier_of(name), **m, 'craft_cost': craft_cost(name), 'icon': inv.get('icon')})
write('weapon_mods', wmods, [(k, (lambda k: lambda r: r.get(k))(k)) for k in
                             ['id', 'name', 'tier', 'rarity', 'stat_type', 'function_type', 'value_type', 'min_value', 'max_value', 'craft_cost', 'description']])

# ---------------------------------------------------------------- BUILDINGS
def spawned_attack(bp, _depth=0):
    """Damage dealt by something a building spawns (attack drones, mines): the blueprint's own weapon
    stats, else follow its script's planted/explosion blueprint to a BombAmmoComponent damage."""
    if not bp or _depth > 4: return None
    w = weapon_stats(bp)
    if w:
        s = D(w.get('stats'))
        return {'damage_type': w.get('damage_type'), 'damage': D(s.get('DAMAGE_VALUE')).get('max_value'),
                'fire_rate': D(s.get('FIRE_RATE')).get('max_value')}
    e = ent(bp)
    if not e: return None
    for pat in find_all(D(e.get('BombAmmoComponent')), 'DamagePattern'):
        dmg = next((d for d in find_all(pat, 'Damage') if isinstance(d, dict)), None)
        if dmg:
            return {'damage_type': dmg.get('type'), 'damage': dmg.get('value'), 'splash': pat.get('area_damage_radius')}
    db = D(lua_db(e))
    return spawned_attack(db.get('plant_blueprint') or db.get('bp'), _depth + 1)


def turret_info(e):
    """Targeting for towers: what they shoot at and the aim range (inherited from the level 1 blueprint).
    Drone and mine towers have no turret; they use the drones' search radius instead."""
    t = first(e.get('TurretDesc'))
    if isinstance(t, dict):
        vol = D(t.get(''))  # the aim volume block follows `aim_volume "SphericalAimVolume"`
        return {'targets': [x for x in str(t.get('target') or '').split('|') if x],
                'range_min': vol.get('range_min'), 'range_max': vol.get('range_max')}
    db = D(lua_db(e))
    if db.get('drone_blueprint'):
        return {'targets': [], 'range_min': 0, 'range_max': db.get('drone_search_radius'),
                'spawns': db.get('drone_blueprint'), 'spawned_attack': spawned_attack(db['drone_blueprint'])}
    return None


print('buildings ...')
buildings = []
for name in sorted(RAW):
    e = ent(name)
    bd = first(e.get('BuildingDesc')) if e else None
    if not isinstance(bd, dict) or name.startswith(('debug', 'editor')): continue
    cost_variants = {}
    for ci in as_list(D(bd.get('costs')).get('BuildingCostInfo')):
        if isinstance(ci, dict):
            cost_variants[ci.get('name', 'default')] = {'build_time': ci.get('building_time'), 'cost': ci.get('building_cost') if isinstance(ci.get('building_cost'), dict) else {}}
    h = D(first(e.get('HealthDesc')))
    conv = D(first(e.get('ResourceConverterDesc')))

    def res_entries(block):
        return [g for g in as_list(D(block).get('GameplayResource')) if isinstance(g, dict)]

    def res_list(block):
        return {g['resource']: g.get('value') for g in res_entries(block) if g.get('resource')}

    def any_of_group(block):
        # Entries naming a resource *group* instead of one resource: the building works with any
        # member, chosen in game (a Liquid Decompressor outputs whichever liquid you load into it).
        # Entries with the same `family` in `in` and `out` carry the same resource through.
        return [{k: g.get(k) for k in ('group', 'specific_group', 'value', 'family') if g.get(k) is not None}
                for g in res_entries(block) if g.get('group') and not g.get('resource')]

    def one_of(block):
        # Entries sharing a `family` are alternatives: the building uses (or makes) only one of
        # them at a time, e.g. a Fusion Powerplant takes water OR supercoolant.
        fams = defaultdict(list)
        for g in res_entries(block):
            if g.get('family') and g.get('resource'): fams[g['family']].append(g['resource'])
        return [rs for rs in fams.values() if len(rs) > 1]
    storage = []
    for s in find_all(D(e.get('ResourceStorageDesc')), 'Storage'):
        if isinstance(s, dict): storage.append({k: v for k, v in s.items() if k in ('resource', 'group', 'subgroup', 'max')})
    rec = {
        'id': name, 'name': L(bd.get('localization_id')), 'description': clean_text(L(bd.get('description'))),
        'category': bd.get('category'), 'type': D(first(e.get('TypeDesc'))).get('type'), 'icon': bd.get('menu_icon'),
        'costs': cost_variants, 'max_health': h.get('max_health'), 'health_regen': h.get('regeneration'),
        'limit': bd.get('limit'), 'upgrades_to': bd.get('upgrade'), 'sellable': bd.get('sellable'),
        'consumes': res_list(conv.get('in')), 'produces': res_list(conv.get('out')),
        'consumes_one_of': one_of(conv.get('in')), 'produces_one_of': one_of(conv.get('out')),
        'consumes_any': any_of_group(conv.get('in')), 'produces_any': any_of_group(conv.get('out')),
        'optional_outputs': [g['resource'] for g in res_entries(conv.get('out')) if str(g.get('optional')) == '1' and g.get('resource')],
        'storage': storage,
        'resistances': first(e.get('ResistanceComponent')),
        'weapon': weapon_stats(name), 'turret': turret_info(e), 'unlocked_by_research': UNLOCKED_BY.get(name, []),
        'script_data': lua_db(e), 'building_desc': bd, 'source_file': e.get('__file__'),
    }
    buildings.append(rec)


def rates_str(rates, groups=(), optional=(), any_of=()):
    """'energy 20, plasma 10 or resin 10': alternatives joined with 'or', optional outputs marked,
    group entries shown as 'any local 100'."""
    done, parts = set(), []
    for k, v in rates.items():
        if k in done: continue
        grp = next((g for g in groups if k in g), [k])
        done.update(grp)
        parts.append(' or '.join(f"{r} {rates.get(r)}" + (' (optional)' if r in optional else '') for r in grp))
    parts += [f"any {g['group']} {g.get('value')}" for g in any_of]
    return ', '.join(parts)


def bcost(r, variant='default'):
    c = D(r['costs'].get(variant))
    return c.get('cost')


write('buildings', buildings, [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('category', lambda r: r['category']),
    ('cost', lambda r: bcost(r)), ('build_time', lambda r: D(r['costs'].get('default')).get('build_time')),
    ('other_cost_modes', lambda r: '; '.join(f"{k}: {cost_str(v.get('cost'))}" for k, v in r['costs'].items() if k != 'default')),
    ('max_health', lambda r: r['max_health']), ('limit', lambda r: r['limit']),
    ('consumes_per_sec', lambda r: rates_str(r['consumes'], r['consumes_one_of'], any_of=r['consumes_any'])),
    ('produces_per_sec', lambda r: rates_str(r['produces'], r['produces_one_of'], r['optional_outputs'], r['produces_any'])),
    ('storage', lambda r: ', '.join(f"{s.get('resource') or s.get('subgroup')}:{s.get('max')}" for s in r['storage'])),
    ('upgrades_to', lambda r: r['upgrades_to']),
    ('weapon_damage', lambda r: stat_str(D(D(r['weapon']).get('stats')).get('DAMAGE_VALUE'))),
    ('weapon_fire_rate', lambda r: stat_str(D(D(r['weapon']).get('stats')).get('FIRE_RATE'))),
    ('weapon_damage_type', lambda r: D(r['weapon']).get('damage_type')),
    ('unlocked_by', lambda r: r['unlocked_by_research']), ('description', lambda r: r['description']),
])

# ---------------------------------------------------------------- ENEMIES
print('enemies ...')
# names + family info from discoverable groups
UNIT_NAME, UNIT_FAMILY = {}, {}
families = []
for f in sorted(glob.glob(P('scripts', 'units', 'discoverable_group*.dat'))):
    for fam in as_list(load(f).get('FamilyInfo')):
        if not isinstance(fam, dict): continue
        families.append({**{k: v for k, v in fam.items() if k != 'subspecies_vec'}, 'file': os.path.basename(f),
                         'description_text': clean_text(L(fam.get('description')))})
        for sub in as_list(D(fam.get('subspecies_vec')).get('SubSpecies')):
            if not isinstance(sub, dict): continue
            for bp in as_list(D(sub.get('blueprints')).get('String')):
                UNIT_NAME[bp] = L(sub.get('name')) or sub.get('name')
                UNIT_FAMILY[bp] = fam.get('name')

# species -> creatures, and which biome files list them
SPECIES = {}
for f in sorted(glob.glob(P('scripts', 'units', 'creature_species*.kvp'))):
    for sp in as_list(load(f).get('CreatureSpecies')):
        if isinstance(sp, dict) and sp.get('species_name'):
            sp = dict(sp); sp['file'] = os.path.basename(f)
            sp['creatures'] = as_list(D(sp.get('creatures')).get('Creature'))
            SPECIES[sp['species_name']] = sp
UNIT_SPECIES = defaultdict(set)
for sn, sp in SPECIES.items():
    for c in sp['creatures']:
        if isinstance(c, dict) and c.get('blueprint'): UNIT_SPECIES[c['blueprint']].add(sn)


def unit_core(name):
    """Follow RandomBlueprintDesc to the first concrete variant."""
    e = ent(name)
    if e and 'HealthDesc' not in e and 'RandomBlueprintDesc' in e:
        bps = [b for b in find_all(e['RandomBlueprintDesc'], 'Blueprint')]
        for b in bps:
            b = b.get('blueprint') if isinstance(b, dict) else b
            if isinstance(b, str) and ent(b): return ent(b), b
        # fall back to <name>_base / <name>_1
        for cand in (name + '_base', name + '_1'):
            if ent(cand): return ent(cand), cand
    return e, name


enemies = []
for name in sorted(RAW):
    if not name.startswith(('units/ground/', 'units/air/')) or '/trigger' in name or name.count('/') > 2: continue
    if re.search(r'_\d+$', name): continue  # skin variants (_1, _2 ...) share stats with the base
    e, core = unit_core(name)
    if not e or 'HealthDesc' not in e: continue
    h = D(first(e.get('HealthDesc')))
    dmg = []
    for md in find_all(e, 'MeleeDamage'):
        if not isinstance(md, dict): continue
        for d in find_all(md, 'Damage'):
            if isinstance(d, dict) and 'value' in d:
                dmg.append({'attack': md.get('name'), 'type': d.get('type'), 'value': d.get('value')})
    if not dmg and core != name:
        for md in find_all(ent(core.replace('_base', '_1')) or {}, 'MeleeDamage'):
            for d in find_all(md, 'Damage'):
                if isinstance(d, dict) and 'value' in d:
                    dmg.append({'attack': md.get('name'), 'type': d.get('type'), 'value': d.get('value')})
    move = D(first(e.get('MovementDataComponent')))
    base_name = name if name in UNIT_NAME else (name + '_base' if name + '_base' in UNIT_NAME else core)
    rec = {
        'id': name, 'name': UNIT_NAME.get(base_name) or UNIT_NAME.get(core) or L('monster_name/' + name.split('/')[-1]), 'family': UNIT_FAMILY.get(base_name) or UNIT_FAMILY.get(core),
        'species': sorted(UNIT_SPECIES.get(name, set()) | UNIT_SPECIES.get(core, set())),
        'kind': name.split('/')[1], 'max_health': h.get('max_health'), 'health_regen': h.get('regeneration'),
        'resistances': first(e.get('ResistanceComponent')), 'melee_damage': dmg,
        'ranged_weapon': weapon_stats(name) or weapon_stats(core),
        'movement': move, 'loot': first(e.get('LootDesc')), 'skills': first(e.get('SkillLinkUnitComponent')),
        'script_data': lua_db(e), 'source_file': e.get('__file__'),
    }
    enemies.append(rec)
write('enemies', enemies, [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('family', lambda r: r['family']), ('kind', lambda r: r['kind']),
    ('species', lambda r: r['species']), ('max_health', lambda r: r['max_health']), ('regen', lambda r: r['health_regen']),
    ('resistances', lambda r: ', '.join(f'{k}={v}' for k, v in D(r['resistances']).items())),
    ('melee_damage', lambda r: ', '.join(f"{d['value']} {d['type']}" for d in r['melee_damage'])),
    ('ranged_damage', lambda r: stat_str(D(D(r['ranged_weapon']).get('stats')).get('DAMAGE_VALUE'))),
    ('ranged_damage_type', lambda r: D(r['ranged_weapon']).get('damage_type')),
    ('speed', lambda r: ', '.join(f'{k}={v}' for k, v in {**D(r['movement']), **D(r['script_data'])}.items() if k.endswith('_speed') and 'angle' not in k)),
])
with open(os.path.join(OUT, 'enemy_families.json'), 'w', encoding='utf-8') as f:
    json.dump(families, f, indent=1, ensure_ascii=False)
with open(os.path.join(OUT, 'creature_species.json'), 'w', encoding='utf-8') as f:
    json.dump(SPECIES, f, indent=1, ensure_ascii=False)

# ---------------------------------------------------------------- BOSS / ELITE SKILLS
print('boss skills ...')
# The game's own descriptions for these are placeholders, so these summaries were written from the skill scripts.
SKILL_INFO = {
    'aura_damage_fire': 'Constant fire damage to you while you are near the enemy.',
    'aura_damage_acid': 'Constant acid damage to you while you are near the enemy.',
    'aura_damage_cryo': 'Constant cryo damage to you while you are near the enemy.',
    'aura_damage_energy': 'Constant energy damage to you while you are near the enemy.',
    'aura_heal': 'Heals the enemy and nearby enemies every second (green beams). Heal per second = max HP x max_heal / 4000, clamped between min_heal and max_heal.',
    'aura_resistance': 'Nearby enemies take reduced damage from everything (resistance = damage multiplier), and so does the enemy itself (resistance_owner).',
    'resurrect': 'Brings dead enemies near it back to life.',
    'bomb_cascade': 'Lines of bombs walk toward you, with warning circles first. cascade_count = number of lines.',
    'lightning_cascade': 'Lines of lightning strikes walk toward you, with warning circles first. Longer reach than bombs.',
    'meteor_shower': 'Meteors keep falling on your position. Keep moving.',
    'underground_rock': 'Rocks burst out of the ground under and around you.',
    'fireball_wave': 'Fires a fan of fireballs outward. elements_count = fireballs per wave.',
    'tornado_wave': 'Sends a fan of slow tornadoes. elements_count = tornadoes per wave.',
    'cryo_orb': 'Throws rolling freezing orbs that last about 7 seconds.',
    'shockwave': 'Releases a shockwave every spawn_time seconds while fighting you.',
    'waller': 'Raises rock walls around you to trap you. Walls last 10 seconds.',
    'eggs': 'Lays eggs that hatch more enemies while it is fighting you.',
    'swarm': 'Releases a swarm of small flying creatures. children_count = swarm size.',
    'drones': 'Spawns attack drones while it is fighting you.',
}
# which elite species can roll each skill, and the highest level they reach
CAN_ROLL = defaultdict(dict)
ALL_SKILLS = set(SKILL_INFO)
for sn, sp in SPECIES.items():
    for c in sp['creatures']:
        if not isinstance(c, dict): continue
        cnt, lvl = c.get('max_unit_skill_count') or 0, c.get('max_unit_skill_level')
        excl = {s.strip() for s in str(c.get('exclude_unit_skills') or '').split(',') if s.strip()}
        forced = {s.strip() for s in (str(c.get('force_include_unit_skills') or '') + ',' + str(c.get('additional_include_unit_skills') or '')).split(',') if s.strip()}
        pool = (ALL_SKILLS - excl if isinstance(cnt, (int, float)) and cnt > 0 else set()) | forced
        for s in pool:
            # max_unit_skill_level is the skill level itself (1-4; 0 only appears on tiers with no skills)
            lv = max(1, min(int(lvl), 4)) if isinstance(lvl, (int, float)) else 1
            CAN_ROLL[s][sn] = max(CAN_ROLL[s].get(sn, 0), lv)

boss_skills = []
for name in sorted(RAW):
    if not name.startswith('units/skills/'): continue
    e = ent(name)
    link = D(first(e.get('SkillLinkUnitComponent')))
    if not link.get('name'): continue
    sid = re.sub(r'_lvl_\d+$', '', name.split('/')[-1])
    m = re.search(r'_lvl_(\d+)$', name)
    params = {k: v for k, v in D(lua_db(e)).items() if isinstance(v, (int, float))}
    level = int(m.group(1)) if m else 1
    rolls = {k: v for k, v in CAN_ROLL.get(sid, {}).items() if v >= level}
    boss_skills.append({
        'id': name, 'skill': sid, 'name': L(link.get('name')) or sid, 'level': int(m.group(1)) if m else 1,
        'icon': link.get('icon'), 'description': SKILL_INFO.get(sid) or clean_text(L(link.get('description'))),
        'parameters': params,
        'can_appear_on': [f'{k} (up to lvl {v})' for k, v in sorted(rolls.items())],
        'source_file': e.get('__file__'),
    })
boss_skills.sort(key=lambda r: (r['skill'], r['level']))
write('boss_skills', boss_skills, [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('skill', lambda r: r['skill']), ('level', lambda r: r['level']),
    ('parameters', lambda r: ', '.join(f'{k}={v}' for k, v in r['parameters'].items())),
    ('can_appear_on', lambda r: ', '.join(x.split(' (')[0] for x in r['can_appear_on'])),
    ('description', lambda r: r['description']),
])

# ---------------------------------------------------------------- RESOURCES
print('resources ...')
resources = []
for f in sorted(glob.glob(P('scripts', 'resources', '*.resource'))):
    for rd in as_list(load(f).get('GameplayResourceDef')):
        if isinstance(rd, dict):
            resources.append({**rd, 'name': L(rd.get('localization_id')), 'file': os.path.basename(f)})
write('resources', resources, [(k, (lambda k: lambda r: r.get(k))(k)) for k in
                               ['id', 'name', 'type', 'ore', 'spawn_type', 'bp', 'hud_visible', 'file']])

# ---------------------------------------------------------------- BIOMES
print('biomes ...')
missions = {}
for f in glob.glob(P('missions', 'survival', '*.mission')):
    missions[os.path.splitext(os.path.basename(f))[0]] = load(f).get('MissionDef', {})
camps = {}
for f in glob.glob(P('campaigns', 'survival', '*.campaign')):
    camps[os.path.splitext(os.path.basename(f))[0]] = load(f).get('CampaignDef', {})
biomes = []
for f in sorted(glob.glob(P('biomes', '*', '*.biome'))):
    bid = os.path.splitext(os.path.basename(f))[0]
    b = load(f).get('BiomeDef', {})
    m = missions.get(bid, {})
    species = sorted(set(cv.get('creature_species') for cv in find_all(m, 'CreatureVolume') if isinstance(cv, dict) and cv.get('creature_species')))
    units = []
    for s in species:
        for c in D(SPECIES.get(s)).get('creatures', []):
            if isinstance(c, dict): units.append(c.get('blueprint'))
    rec = {
        'id': bid, 'name': L(f'gui/menu/biome_name/{bid}') or L(m.get('localization_id')) or L(f'campaigns/survival/{bid}.campaign'),
        'resources': [x.strip() for x in str(b.get('resources', '')).split(',') if x.strip()],
        'resource_names': [L(f'resource_name/{x.strip()}') or x.strip() for x in str(b.get('resources', '')).split(',') if x.strip()],
        'default_liquid_resource': b.get('default_liquid_resource'),
        'survival_mission': {k: m.get(k) for k in ('map_size', 'threat', 'creature_volumes_density', 'creature_volumes_min_distance', 'mission_award', 'player_spawn_logic') if k in m} or None,
        'survival_campaign': camps.get(bid),
        'creature_species': species, 'creature_blueprints': sorted(set(filter(None, units))),
        'creature_names': sorted(set(filter(None, (UNIT_NAME.get(u) or UNIT_NAME.get(u + '_base') for u in units)))),
        'ambient_species': m.get('ambient_creature_species'),
    }
    biomes.append(rec)
write('biomes', biomes, [
    ('id', lambda r: r['id']), ('name', lambda r: r['name']), ('resources', lambda r: r['resource_names']),
    ('liquid', lambda r: r['default_liquid_resource']),
    ('map_size', lambda r: D(r['survival_mission']).get('map_size')), ('threat', lambda r: D(r['survival_mission']).get('threat')),
    ('creature_species', lambda r: r['creature_species']), ('creatures', lambda r: r['creature_names']),
    ('unlock_requirement', lambda r: D(r['survival_campaign']).get('requirement')),
])

# ---------------------------------------------------------------- RESEARCH
print('research ...')
for r in RESEARCH_NODES:
    r['unlock_names'] = []
    for a in r['unlocks']:
        e = ent(a) or {}
        bd = D(first(e.get('BuildingDesc')))
        inv = D(first(e.get('InventoryItemDesc')))
        r['unlock_names'].append(L(bd.get('localization_id')) or L(inv.get('name')) or a)
write('research', RESEARCH_NODES, [
    ('tree', lambda r: r['tree']), ('category', lambda r: r['category'] or r['category_id']), ('id', lambda r: r['id']),
    ('name', lambda r: r['name']), ('cost', lambda r: r['costs']), ('requires', lambda r: [x['name'] or x['id'] for x in r['requires']]),
    ('unlocks', lambda r: r['unlock_names']),
])

# difficulty settings are useful context for wiki numbers
try:
    with open(os.path.join(OUT, 'difficulties.json'), 'w', encoding='utf-8') as f:
        json.dump(load(P('scripts', 'difficulty', 'difficulties.difficulty')), f, indent=1, ensure_ascii=False)
except Exception as e:
    print('  difficulties skipped:', e)

with open(os.path.join(OUT, 'localization_en.json'), 'w', encoding='utf-8') as f:
    json.dump(LOC, f, indent=0, ensure_ascii=False, sort_keys=True)
print('done ->', OUT)
