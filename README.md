# Tyddy-Mods-Morrowind
The hub for Tyddy mods and projects (or they will rot in my portable HDD)

## Structure

```
mods/
  _template/      ← copy this to start a new mod
  <ModName>/      ← one folder per mod, laid out like Data Files
wip/              ← experiments and unfinished stuff
tools/            ← helper scripts (asset checker)
```

To start a new mod: copy `mods/_template`, rename it, and fill in its README.

Before a release, run `python tools/check_mods.py` to catch missing textures, uppercase paths and textures over 2K (see [tools/README.md](tools/README.md)).

## License

- **Assets** (meshes, textures, plugins): [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
- **Scripts** (Lua): MIT

See [LICENSE](LICENSE). Requires a legal copy of The Elder Scrolls III: Morrowind.
