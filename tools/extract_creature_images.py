"""Convert the bestiary creature portraits into small WebP files for the Enemies page.

Usage:  python tools/extract_creature_images.py [game_dir] [data_dir]
Reads materials/textures/gui/menu/species/{fauna,fauna_neutral,other}/*.dds from the game's packs
(read-only), trims the empty border, scales them down and writes
data_dir/icons/gui/menu/species/<category>/<name>.webp (WebP keeps the set small). Run build_site_data.py afterwards.
Needs Pillow:  python -m pip install --user Pillow
"""
import glob, io, os, sys, zipfile
from PIL import Image

GAME = sys.argv[1] if len(sys.argv) > 1 else r'D:/SteamLibrary/steamapps/common/Riftbreaker'
DATA = sys.argv[2] if len(sys.argv) > 2 else 'riftbreaker_data'
PREFIX = 'materials/textures/gui/menu/species/'
CATEGORIES = ('fauna/', 'fauna_neutral/', 'other/')
MAX_SIZE = 320  # longest side in pixels; the page shows them at 48-240 px

# texture -> pack holding the newest copy (later packs override earlier ones)
packs = []
for sub in ['startup/*startup*.zip', '*_win_data.zip', 'dlc_*/startup/*.zip', 'dlc_*/*.zip']:
    packs += sorted(glob.glob(os.path.join(GAME, 'packs', sub)))
where = {}
for p in packs:
    with zipfile.ZipFile(p) as z:
        for n in z.namelist():
            rel = n[len(PREFIX):]
            if n.startswith(PREFIX) and n.endswith('.dds') and rel.startswith(CATEGORIES) \
                    and 'species_fauna_bg' not in rel and 'unknown_species' not in rel and 'crystal_' not in rel.split('/')[0]:
                where[n] = p

by_pack = {}
for tex, pack in where.items():
    by_pack.setdefault(pack, []).append(tex)
ok = 0
for pack, texs in by_pack.items():
    with zipfile.ZipFile(pack) as z:
        for tex in texs:
            dst = os.path.join(DATA, 'icons', *tex[len('materials/textures/'):-4].split('/')) + '.webp'
            try:
                img = Image.open(io.BytesIO(z.read(tex))).convert('RGBA')
                # Trim to the visible creature: ignore the faint drop shadow edges.
                box = img.getchannel('A').point(lambda a: 255 if a > 24 else 0).getbbox()
                if box:
                    img = img.crop(box)
                img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                img.save(dst, 'WEBP', quality=82, method=6)
                ok += 1
            except Exception as e:
                print('  could not convert', tex, '-', e)
print(f'{ok} creature images -> {os.path.join(DATA, "icons", "gui", "menu", "species")}')
