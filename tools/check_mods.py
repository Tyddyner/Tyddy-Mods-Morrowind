#!/usr/bin/env python3
"""Asset sanity checker for the mods in this repo.

For every mod folder in mods/ (except _template) it reports:

  * textures referenced by .nif files that can't be found in the mod
    (or in any --data-dir you pass, e.g. an extracted vanilla Data Files),
  * shipped files/folders whose path isn't all lowercase, plus texture
    paths inside .nif files that aren't lowercase,
  * textures wider or taller than the size limit (2048 px by default).

Standard library only, so it runs on a plain Python 3.8+ install on
Windows or Linux:

    python tools/check_mods.py                  # all mods
    python tools/check_mods.py BetterDaggers    # one or more mods by name
    python tools/check_mods.py --data-dir "D:/Morrowind/Data Files"
    python tools/check_mods.py --json > report.json

Exit code is 1 if any mod has an issue, 0 otherwise, so it can gate CI.

How NIF texture paths are found: Morrowind-era NIFs (version 4.0.0.2) store
NiSourceTexture file names as a uint32 length followed by the characters.
Instead of parsing the whole block tree, the checker scans the file for
length-prefixed strings ending in .dds/.tga/.bmp. That catches every
external texture reference without needing a full NIF parser.

How texture lookup works (mirrors Morrowind/OpenMW): the path is taken
relative to textures/ (a leading "textures\\" is stripped), matching is
case-insensitive, and the .dds version is accepted in place of .tga/.bmp
because the engine prefers it.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODS_DIR = REPO_ROOT / "mods"

# Folders inside a mod that ship to Data Files and must stay lowercase.
# source/ and docs/ are work files and aren't checked.
SHIPPED_DIRS = ("meshes", "textures", "icons", "sound", "music",
                "bookart", "splash", "fonts", "scripts")

TEXTURE_EXTS = (".dds", ".tga", ".bmp", ".png")
NIF_TEXTURE_RE = re.compile(rb"[\x20-\x7e]{1,255}?\.(?:dds|tga|bmp)", re.IGNORECASE)
LFS_POINTER_PREFIX = b"version https://git-lfs"


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class ModReport:
    name: str
    missing_textures: list = field(default_factory=list)   # (nif, texture path)
    non_lowercase: list = field(default_factory=list)      # (where, path)
    oversized: list = field(default_factory=list)          # (texture, w, h)
    warnings: list = field(default_factory=list)           # free-form notes
    nif_count: int = 0
    texture_count: int = 0

    @property
    def issue_count(self) -> int:
        return len(self.missing_textures) + len(self.non_lowercase) + len(self.oversized)

    def to_dict(self) -> dict:
        return {
            "mod": self.name,
            "nifs_scanned": self.nif_count,
            "textures_scanned": self.texture_count,
            "missing_textures": [{"nif": n, "texture": t} for n, t in self.missing_textures],
            "non_lowercase": [{"where": w, "path": p} for w, p in self.non_lowercase],
            "oversized_textures": [{"texture": t, "width": w, "height": h}
                                   for t, w, h in self.oversized],
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def is_lfs_pointer(path: Path) -> bool:
    """True if the file is a Git LFS pointer instead of the real binary."""
    try:
        with path.open("rb") as f:
            return f.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX
    except OSError:
        return False


def rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def normalize_texture_path(raw: str) -> str:
    """Turn a NIF texture reference into a lowercase path relative to textures/."""
    p = raw.replace("\\", "/").strip().lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    if p.lower().startswith("data files/"):
        p = p[len("data files/"):]
    if p.lower().startswith("textures/"):
        p = p[len("textures/"):]
    return p.lower()


def nif_texture_refs(data: bytes) -> list:
    """Return the texture paths referenced by a NIF, in file order, de-duplicated."""
    found = []
    seen = set()
    for m in NIF_TEXTURE_RE.finditer(data):
        start, end = m.span()
        # The regex is lazy and may start too early; walk forward to the
        # offset whose preceding uint32 equals the string length.
        for s in range(start, end):
            if s < 4:
                continue
            (length,) = struct.unpack_from("<I", data, s - 4)
            if length == end - s:
                text = data[s:end].decode("ascii")
                if text not in seen:
                    seen.add(text)
                    found.append(text)
                break
    return found


def texture_size(path: Path):
    """Read (width, height) from a DDS/TGA/BMP/PNG header, or None if unknown."""
    try:
        with path.open("rb") as f:
            head = f.read(32)
    except OSError:
        return None
    ext = path.suffix.lower()
    try:
        if ext == ".dds" and head[:4] == b"DDS ":
            height, width = struct.unpack_from("<II", head, 12)
            return width, height
        if ext == ".tga" and len(head) >= 18:
            width, height = struct.unpack_from("<HH", head, 12)
            return width, height
        if ext == ".bmp" and head[:2] == b"BM":
            width, height = struct.unpack_from("<ii", head, 18)
            return abs(width), abs(height)
        if ext == ".png" and head[:8] == b"\x89PNG\r\n\x1a\n":
            width, height = struct.unpack_from(">II", head, 16)
            return width, height
    except struct.error:
        pass
    return None


def build_texture_index(roots) -> dict:
    """Map lowercase path relative to textures/ -> actual file, across roots."""
    index = {}
    for root in roots:
        tex_dir = find_child_ci(root, "textures")
        if tex_dir is None:
            continue
        for f in tex_dir.rglob("*"):
            if f.is_file():
                index.setdefault(rel(f, tex_dir).lower(), f)
    return index


def find_child_ci(parent: Path, name: str):
    """Find a direct child folder by case-insensitive name."""
    if not parent.is_dir():
        return None
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == name:
            return child
    return None


def resolve_texture(tex: str, index: dict) -> bool:
    """True if the texture exists, accepting a .dds in place of .tga/.bmp."""
    if tex in index:
        return True
    stem, dot, _ = tex.rpartition(".")
    return bool(dot) and f"{stem}.dds" in index


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_mod(mod_dir: Path, data_dirs, max_size: int) -> ModReport:
    report = ModReport(mod_dir.name)

    # Non-lowercase paths in shipped folders (folder names included).
    for child in sorted(mod_dir.iterdir()):
        if not child.is_dir() or child.name.lower() not in SHIPPED_DIRS:
            continue
        for p in sorted([child, *child.rglob("*")]):
            if p.name == ".gitkeep":
                continue
            if p.name != p.name.lower():
                report.non_lowercase.append(("file" if p.is_file() else "folder",
                                             rel(p, mod_dir)))

    # Shipped plugin files at the mod root aren't case-sensitive for lookups,
    # so they're left alone on purpose.

    texture_index = build_texture_index([mod_dir, *data_dirs])

    # Missing textures referenced by NIFs.
    meshes_dir = find_child_ci(mod_dir, "meshes")
    nifs = sorted(meshes_dir.rglob("*")) if meshes_dir else []
    for nif in nifs:
        if not nif.is_file() or nif.suffix.lower() != ".nif":
            continue
        report.nif_count += 1
        nif_rel = rel(nif, mod_dir)
        if is_lfs_pointer(nif):
            report.warnings.append(f"{nif_rel}: Git LFS pointer, not scanned (run `git lfs pull`)")
            continue
        refs = nif_texture_refs(nif.read_bytes())
        if not refs:
            report.warnings.append(f"{nif_rel}: no texture references found")
        for raw in refs:
            tex = normalize_texture_path(raw)
            if raw.replace("\\", "/") != raw.replace("\\", "/").lower():
                report.non_lowercase.append(("nif texture path", f"{nif_rel} -> {raw}"))
            if not resolve_texture(tex, texture_index):
                report.missing_textures.append((nif_rel, raw))

    # Oversized textures (only the mod's own textures, not --data-dir ones).
    tex_dir = find_child_ci(mod_dir, "textures")
    textures = sorted(tex_dir.rglob("*")) if tex_dir else []
    for tex in textures:
        if not tex.is_file() or tex.suffix.lower() not in TEXTURE_EXTS:
            continue
        report.texture_count += 1
        tex_rel = rel(tex, mod_dir)
        if is_lfs_pointer(tex):
            report.warnings.append(f"{tex_rel}: Git LFS pointer, size not checked (run `git lfs pull`)")
            continue
        size = texture_size(tex)
        if size is None:
            report.warnings.append(f"{tex_rel}: couldn't read image header")
            continue
        w, h = size
        if w > max_size or h > max_size:
            report.oversized.append((tex_rel, w, h))

    return report


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def print_report(report: ModReport, max_size: int) -> None:
    status = "OK" if report.issue_count == 0 else f"{report.issue_count} issue(s)"
    print(f"=== {report.name} — {status} "
          f"({report.nif_count} nif, {report.texture_count} textures) ===")

    def section(title, items, fmt):
        if items:
            print(f"  {title} ({len(items)}):")
            for item in items:
                print(f"    - {fmt(item)}")

    section("Missing textures", report.missing_textures,
            lambda i: f"{i[0]} -> {i[1]}")
    section("Non-lowercase paths", report.non_lowercase,
            lambda i: f"[{i[0]}] {i[1]}")
    section(f"Textures larger than {max_size}px", report.oversized,
            lambda i: f"{i[0]} ({i[1]}x{i[2]})")
    section("Warnings", report.warnings, str)
    print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check mod folders for missing NIF textures, "
                    "non-lowercase paths and oversized textures.")
    parser.add_argument("mods", nargs="*",
                        help="mod folder names to check (default: all in mods/)")
    parser.add_argument("--mods-dir", type=Path, default=DEFAULT_MODS_DIR,
                        help="folder containing the mods (default: repo mods/)")
    parser.add_argument("--data-dir", type=Path, action="append", default=[],
                        help="extra Data Files folder to resolve textures against "
                             "(e.g. extracted vanilla textures or a dependency). "
                             "Can be repeated.")
    parser.add_argument("--max-size", type=int, default=2048,
                        help="max texture width/height in px (default: 2048)")
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON instead of text")
    args = parser.parse_args(argv)

    if not args.mods_dir.is_dir():
        parser.error(f"mods folder not found: {args.mods_dir}")

    if args.mods:
        mod_dirs = []
        for name in args.mods:
            d = args.mods_dir / name
            if not d.is_dir():
                parser.error(f"mod not found: {d}")
            mod_dirs.append(d)
    else:
        mod_dirs = sorted(d for d in args.mods_dir.iterdir()
                          if d.is_dir() and not d.name.startswith(("_", ".")))

    for d in args.data_dir:
        if not d.is_dir():
            parser.error(f"--data-dir not found: {d}")

    reports = [check_mod(d, args.data_dir, args.max_size) for d in mod_dirs]

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
    else:
        if not reports:
            print(f"No mods found in {args.mods_dir}")
        for r in reports:
            print_report(r, args.max_size)
        total = sum(r.issue_count for r in reports)
        print(f"{len(reports)} mod(s) checked, {total} issue(s) total.")

    return 1 if any(r.issue_count for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
