# tools

Helper scripts for working on the mods. Standard-library Python 3.8+ only, no installs needed.

## check_mods.py

Checks every mod in `mods/` (except `_template`) and prints a report per mod:

- **Missing textures**: textures referenced by `.nif` files that aren't in the mod's `textures/` folder. A `.dds` counts as a match for a `.tga`/`.bmp` reference, the same way the engine handles it.
- **Non-lowercase paths**: files or folders in shipped folders (`meshes/`, `textures/`, `icons/`, `sound/`, …) with uppercase letters, plus texture paths inside `.nif` files. `source/` and `docs/` are skipped.
- **Oversized textures**: textures wider or taller than 2048 px. Reads DDS, TGA, BMP and PNG headers.

```
python tools/check_mods.py                     # all mods
python tools/check_mods.py BetterDaggers       # just these mods
python tools/check_mods.py --data-dir "D:/Games/Morrowind/Data Files"   # also resolve vanilla/dependency textures
python tools/check_mods.py --max-size 4096     # different size limit
python tools/check_mods.py --json              # machine-readable output
```

Exits with code 1 if any issue is found.

Notes:
- A mesh that reuses vanilla textures will show them as missing unless you pass `--data-dir` pointing at a folder with those textures (loose files; the script can't read `.bsa` archives).
- `.nif`/`.dds` files that are still Git LFS pointers (not pulled) are skipped with a warning. Run `git lfs pull` first.
- Texture references are found by scanning the `.nif` for length-prefixed `.dds`/`.tga`/`.bmp` strings, not by fully parsing the file. It's built for Morrowind-era NIFs (4.0.0.2) like the ones Blender's Morrowind exporter writes.
