"""Copy text data files out of Riftbreaker pack zips (read-only on the game folder).
Later packs (higher number) override earlier ones, matching the game's load order."""
import zipfile, glob, os, sys
GAME = sys.argv[1] if len(sys.argv) > 1 else r"D:/SteamLibrary/steamapps/common/Riftbreaker"
OUT = sys.argv[2] if len(sys.argv) > 2 else "extracted"
BINARY = {'mesh','nxs','dds','skeleton','png','jpg','tga','fnt','wem','bnk','ogg','wav','bk2','webm','mp4','animation','anim','cursor','hlsl','h','program','tile','terrain','bin','crc'}
packs = []
for sub in ['engine/*engine*.zip', 'startup/*startup*.zip', '*_win_data.zip', 'dlc_*/startup/*.zip', 'dlc_*/*.zip']:
    packs += sorted(glob.glob(os.path.join(GAME, 'packs', sub)))
n = 0
for p in packs:
    with zipfile.ZipFile(p) as z:
        for name in z.namelist():
            if name.endswith('/'): continue
            ext = name.rsplit('.', 1)[-1].lower() if '.' in name.rsplit('/',1)[-1] else ''
            if ext in BINARY: continue
            dst = os.path.join(OUT, *name.split('/'))
            if os.name == 'nt': dst = '\\\\?\\' + os.path.abspath(dst)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as f: f.write(z.read(name))
            n += 1
    print('read', os.path.relpath(p, GAME))
print(n, 'files written to', OUT)
