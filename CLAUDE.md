# Tyddy-Mods-Morrowind — instructions for Claude

Hub repo for Tyddy's Morrowind mods. Main target is **OpenMW** (mostly modded); some mods may also support MWSE. Tyddy works on Windows with Blender, GIMP, Substance Painter/Designer 2019 and Mod Organizer 2.

## Repo layout
- `mods/<ModName>/` — one folder per mod, laid out like `Data Files` (`meshes/`, `textures/`, `icons/`, `sound/`, `scripts/`, plugin `.esp`/`.omwaddon` at the root).
- `mods/<ModName>/source/` — work files (`.blend`, layered textures). Never shipped in releases.
- `mods/_template/` — copy this to start a new mod; never edit it for a specific mod.
- `wip/` — experiments.

## Rules
- New mod → copy `mods/_template`, rename to PascalCase, fill in its README (description, requirements, install, changelog).
- Morrowind paths are case-insensitive in-game but keep lowercase folder/file names for meshes/textures to stay OpenMW/Linux-safe.
- Large binaries (`.nif`, `.dds`, `.tga`, `.blend`, `.wav`) go through Git LFS (see `.gitattributes`). Don't commit zips/7z — releases are uploaded as GitHub Releases, packaged as `.7z`.
- Lua: prefer OpenMW Lua API (`openmw.*`); note in the mod README if something is MWSE-only. Keep scripts commented.
- Asset budget reference for weapon props: ~4–5k tris, 2K textures, diffuse + normal (+ PBR maps where the renderer supports them).
- Licensing: assets CC BY-NC-SA 4.0, scripts MIT (see `LICENSE`). Never add original Bethesda assets.
- This cloud environment can't run Morrowind, OpenMW or the CS. Say clearly what needs testing in-game, and add a "Testing" checklist to the mod README when you change gameplay.
- Update the mod's changelog with every change. Commit messages: short, imperative, prefixed with the mod name, e.g. `BetterDaggers: fix normal map paths`.
