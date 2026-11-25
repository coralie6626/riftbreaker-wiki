# Riftbreaker game data

These files are generated from the game's own data files by `tools/extract_text.py` and `tools/export_data.py`.
Every category has a `.csv` summary (opens in Excel) and a `.json` file with full detail.

| File | What it holds |
|---|---|
| `weapons` | Mech weapons for every tier: damage, fire rate, splash, DoT, crit, stun, ammo, charge levels, craft cost, unlocking research |
| `buildings` | Every building: build cost and time, health, resources consumed and produced per second, storage, upgrade chain, tower weapon stats |
| `enemies` | Every ground and air unit: health, regeneration, resistance multipliers, melee and ranged damage, species, loot |
| `boss_skills` | Elite and boss skills (the icons on their health bars): what each does, its values at levels 1–4, and which elite species can roll it |
| `icons/` | PNG icons for weapons, buildings, items, resources, research and boss skills, converted from the game's textures. `icons/gui/menu/species/` holds the bestiary creature portraits as WebP (`extract_creature_images.py`) |
| `enemy_families.json`, `creature_species.json` | Bestiary families and the spawn groups that place creatures in each biome |
| `biomes` | Each biome: resources found there, map size, creature species and creature names, unlock requirement |
| `resources` | Every resource definition: ores, liquids, vents, global resources |
| `skills` | Mech skills for each tier, with values from the skill scripts (cooldown, speed and similar) |
| `consumables` | Grenades, turrets, mines and so on, for each tier |
| `upgrades` | Mech upgrade items: stat bonuses (health, regeneration, resistances...) |
| `weapon_mods` | Weapon mod items, with the stat each one changes and its value range |
| `research` | Every research node in the story, survival, open-world and prologue trees: cost, prerequisites, unlocks |
| `difficulties.json` | Difficulty settings |
| `localization_en.json` | All English UI text, keyed by ID |

## Reading the numbers
- Stats are shown as `min-max (base X)`. Items roll a random value within min-max when they drop or are crafted.
- Resistances are damage multipliers. For example, `fire=2.0` means the unit takes double fire damage, and `acid=0.1` means it takes 10% of acid damage.
- Resource rates in `buildings` are per second.
- Some entries are internal, debug or deprecated blueprints (for example the `deprecated` weapon type). Filter them out as needed.

## Regenerating after a game patch
```
python tools/extract_text.py "D:/SteamLibrary/steamapps/common/Riftbreaker" extracted
python tools/export_data.py extracted riftbreaker_data
python tools/extract_icons.py "D:/SteamLibrary/steamapps/common/Riftbreaker" riftbreaker_data
python tools/extract_creature_images.py "D:/SteamLibrary/steamapps/common/Riftbreaker" riftbreaker_data
python tools/build_viewer.py
```
`extract_icons.py` and `extract_creature_images.py` need Pillow (`python -m pip install --user Pillow`). Open `viewer.html` to browse everything. It must stay next to the `riftbreaker_data` folder so the icons load.

The game's descriptions for boss skills are placeholders, so the `boss_skills` descriptions were written from the skill scripts.
Extraction only reads the game's `.zip` packs and never changes the game folder. Later packs override earlier ones, matching the game's patch order.
