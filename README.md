# Riftbreaker Field Guide

A static site with Riftbreaker infographics and planning tools, built from the game's own data files.
No backend or build step: plain HTML, CSS and JavaScript.

## Layout
| Path | What it is |
|---|---|
| `index.html` | The site: power source comparison chart and energy calculator |
| `defense.html` | Defense tower finder: filter towers by damage type, range, air targeting and ammo |
| `enemies.html` | Enemy finder: health, damage and resistances per tier, filter by weakness and biome |
| `assets/style.css`, `assets/app.js`, `assets/defense.js`, `assets/enemies.js` | Styles and page logic |
| `data/energy.json`, `data/defense.json`, `data/enemies.json` | Small data files the pages load (generated, do not edit by hand) |
| `viewer.html` | Full data browser for every exported category |
| `riftbreaker_data/` | Full exports from the game, plus icons (see its README) |
| `tools/` | Extraction and build scripts |

## Run locally
The page loads JSON with `fetch`, which browsers block for files opened straight from disk. Serve the folder instead:
```
python -m http.server 8765 --bind 127.0.0.1
```
Then open http://127.0.0.1:8765/.

## Updating after a game patch
Run the steps in `riftbreaker_data/README.md`, then rebuild the site data:
```
python tools/build_site_data.py
```

## Calculator notes
- Rates are per second at full operation.
- Deposits a building sits on (ore veins, geothermal and gas vents) are listed as placement needs, not as resources used up.
- Some buildings take one input or another (Fusion Powerplant: water or super coolant), or make one output or another (Armory, Rare Element Mine). The game marks these with a shared `family` in the entity file; `export_data.py` writes them as `consumes_one_of` / `produces_one_of`. The calculator counts one option per building and lets you pick which.
- The Liquid Pump, Compressor and Decompressor work with whichever liquid the player picks, so their recipes name a resource *group* (`local`, `local_compressed`, `vein`) instead of a resource. `export_data.py` writes these as `consumes_any` / `produces_any`, and the calculator gives each a "Liquid" picker. Compressed liquids have no data file of their own; the game names them `<liquid>_compressed`.
- The share link stores the layout in the URL hash, for example `#b=energy/solar_panels.2.8,energy/fusion_powerplant.1.2.supercoolant` (building, level, count, then the chosen option when it isn't the first).

## Defense tower notes
- Range is the turret's aim range from the entity's `TurretDesc` (`range_min`/`range_max`), exported by `export_data.py` as `turret`. Upgrade levels inherit it from level 1 unless they override it.
- Drone and mine towers have no turret: their range is the drones' search radius, and their damage comes from the drone's weapon or the mine's explosion.
- Filters are kept in the URL hash, for example `defense.html#type=fire,energy&air=1&reach=30&lvl=3`.

## Enemy notes
- `data/enemies.json` groups each creature with its Alpha and Ultra tiers. Bosses, nests and alien towers have one tier.
- Resistances are damage multipliers from the unit's `ResistanceComponent`. Neutral wildlife has none, so it takes normal damage from everything.
- Portraits are the game's bestiary images, one per tier, from `tools/extract_creature_images.py`. Anoryx Worm and Viremoth have none in the game files.
- Biomes come from the creature species each biome spawns. Creatures with no biome only appear in story missions or events.
- Filters are kept in the URL hash, for example `enemies.html#weak=fire&tier=ultra&biome=jungle`.

## Hosting
Any static host works (GitHub Pages, Netlify, Cloudflare Pages). Publish `index.html`, `defense.html`, `enemies.html`, `assets/`, `data/`, and `riftbreaker_data/icons/` (the page uses those icons).
