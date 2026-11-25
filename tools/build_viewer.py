"""Build viewer.html: a single self-contained page for browsing the exported tables.

Usage:  python tools/build_viewer.py [data_dir] [output_html]
Run after export_data.py. The page embeds the data, so it opens straight from disk.
"""
import csv, json, os, sys

DATA = sys.argv[1] if len(sys.argv) > 1 else 'riftbreaker_data'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'viewer.html'
HERE = os.path.dirname(os.path.abspath(__file__))

CATEGORIES = [
    ('weapons', 'Weapons'), ('buildings', 'Buildings'), ('enemies', 'Enemies'), ('boss_skills', 'Boss skills'), ('biomes', 'Biomes'),
    ('resources', 'Resources'), ('skills', 'Skills'), ('consumables', 'Consumables'),
    ('upgrades', 'Upgrades'), ('weapon_mods', 'Weapon mods'), ('research', 'Research'),
]
# bulky fields that add little in the detail panel
DROP = {'building_desc', 'icon', 'position'}

bundle = []
for key, label in CATEGORIES:
    csv_path, json_path = os.path.join(DATA, key + '.csv'), os.path.join(DATA, key + '.json')
    if not os.path.exists(csv_path): continue
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    with open(json_path, encoding='utf-8') as f:
        details = json.load(f)
    if len(details) != len(rows) - 1:
        print(f'  warning: {key} csv/json row counts differ; details disabled'); details = [None] * (len(rows) - 1)
    cols, body = rows[0], rows[1:]
    # icon column: relative path to the converted PNG (see extract_icons.py), if it exists
    icons = []
    for d in details:
        ic = d.get('icon') if isinstance(d, dict) else None
        rel = f'{DATA}/icons/{ic.strip("/")}.png' if isinstance(ic, str) and ic else ''
        icons.append(rel.replace('\\', '/') if rel and os.path.exists(rel) else '')
    if any(icons):
        cols = ['icon'] + cols
        body = [[icons[i]] + r for i, r in enumerate(body)]
    details = [{k: v for k, v in d.items() if k not in DROP} if isinstance(d, dict) else d for d in details]
    # base items with no tier suffix are the standard tier
    if 'tier' in cols and 'id' in cols:
        ti, ii = cols.index('tier'), cols.index('id')
        for r in body:
            if not r[ti] and r[ii].endswith('_item'): r[ti] = 'standard'
    # show the readable name first and the long internal id last
    if 'id' in cols and 'name' in cols:
        lead = [cols.index('icon')] if 'icon' in cols else []
        order = lead + [cols.index('name')] + [i for i, c in enumerate(cols) if c not in ('id', 'name', 'icon')] + [cols.index('id')]
        cols = [cols[i] for i in order]; body = [[r[i] for i in order] for r in body]
    rows = [cols] + body
    bundle.append({'key': key, 'label': label, 'columns': rows[0], 'rows': rows[1:], 'details': details})
    print(f'  {label}: {len(rows) - 1}')

with open(os.path.join(HERE, 'viewer_template.html'), encoding='utf-8') as f:
    html = f.read()
payload = json.dumps(bundle, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
html = html.replace('/*__DATA__*/null', payload)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'wrote {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)')
