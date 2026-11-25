"""Convert the icons referenced by the exported tables into PNG files.

Usage:  python tools/extract_icons.py [game_dir] [data_dir]
Reads icon paths (the "icon" field) from data_dir/*.json, takes the matching .dds textures
straight from the game's packs (read-only) and writes data_dir/icons/<icon path>.png.
Needs Pillow:  python -m pip install --user Pillow
"""
import glob, io, json, os, sys, zipfile
from PIL import Image

GAME = sys.argv[1] if len(sys.argv) > 1 else r'D:/SteamLibrary/steamapps/common/Riftbreaker'
DATA = sys.argv[2] if len(sys.argv) > 2 else 'riftbreaker_data'
OUT = os.path.join(DATA, 'icons')


def collect(obj, found):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'icon' and isinstance(v, str) and v: found.add(v)
            else: collect(v, found)
    elif isinstance(obj, list):
        for x in obj: collect(x, found)


icons = set()
for f in glob.glob(os.path.join(DATA, '*.json')):
    if os.path.basename(f) in ('localization_en.json', 'creature_species.json'): continue
    with open(f, encoding='utf-8') as fh:
        rows = json.load(fh)
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and isinstance(r.get('icon'), str): icons.add(r['icon'])
print(len(icons), 'icons referenced')

# texture path -> zip that holds the newest copy (later packs override earlier ones)
wanted = {'materials/textures/' + i.strip('/') + '.dds': i for i in icons}
where = {}
packs = []
for sub in ['startup/*startup*.zip', '*_win_data.zip', 'dlc_*/startup/*.zip', 'dlc_*/*.zip']:
    packs += sorted(glob.glob(os.path.join(GAME, 'packs', sub)))
for p in packs:
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            if n in wanted: where[n] = p

ok = failed = 0
by_pack = {}
for tex, pack in where.items(): by_pack.setdefault(pack, []).append(tex)
for pack, texs in by_pack.items():
    with zipfile.ZipFile(pack) as z:
        for tex in texs:
            dst = os.path.join(OUT, *wanted[tex].strip('/').split('/')) + '.png'
            try:
                img = Image.open(io.BytesIO(z.read(tex)))
                img.load()
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                img.convert('RGBA').save(dst, optimize=True)
                ok += 1
            except Exception as e:
                failed += 1
                print('  could not convert', tex, '-', e)
missing = len(icons) - len(where)
print(f'{ok} converted, {failed} failed, {missing} not found in the packs -> {OUT}')
