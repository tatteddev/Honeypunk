#!/usr/bin/env python3
"""
Apply palette color mappings from palette.md to Honeypunk.yaml.

Modes:
1. Normalization (default) – ensures all hex colors are uppercase and prefixed with '#'.
2. Semantic remap (enable with --semantic) – assigns palette colors to classification keys
     based on semantic role mappings defined in mappings.yaml and roles.yaml.

Usage examples:
        python tools/apply_palette.py                                 # normalize only
        python tools/apply_palette.py --semantic                      # semantic remap using defaults
        python tools/apply_palette.py --semantic --dry-run            # show planned changes
        python tools/apply_palette.py --semantic \
                --mappings tools/mappings.yaml --roles tools/roles.yaml   # custom files

Expected files:
    docs/palette.md : markdown table | Color Name | Hex | Theme Usage |
    Honeypunk.yaml  : theme root YAML
Optional:
    tools/mappings.yaml : semantic role -> classification keys list
    tools/roles.yaml    : semantic role -> palette color name
"""

from __future__ import annotations

import re
import argparse
from pathlib import Path
from typing import Set, Dict, List, Tuple, Optional
import sys
import yaml as pyyaml  # for simple mappings (ruamel used for theme)

from ruamel.yaml import YAML


def parse_palette_md(palette_path: Path) -> Tuple[Set[str], Dict[str, str]]:
    """
    Parse docs/palette.md and extract hex color codes.
    
    Returns a set of uppercase hex codes (e.g., '#00D1FF') found in the palette.
    """
    with palette_path.open("r", encoding="utf-8") as fh:
        content = fh.read()
    
    # Extract table rows
    rows: Dict[str, str] = {}
    hex_pattern = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?)\s*\|")
    for line in content.splitlines():
        m = hex_pattern.match(line)
        if m:
            name = m.group(1).strip()
            hx = m.group(2).upper()
            rows[name] = hx
    print(f"Loaded {len(rows)} palette entries from {palette_path.name}")
    return set(rows.values()), rows


def normalize_color(value: str) -> str:
    """Normalize a color string to uppercase with # prefix."""
    val = value.strip().upper()
    if val.startswith('"#'):
        val = val[2:-1] if val.endswith('"') else val[2:]
    elif val.startswith('#'):
        val = val[1:]
    return f"#{val}" if val else value


def update_yaml_colors(yaml_path: Path, palette_colors: Set[str]) -> int:
    """
    Load Honeypunk.yaml and update all color entries.
    
    Returns the number of color values updated.
    """
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    
    with yaml_path.open("r", encoding="utf-8") as fh:
        doc = yaml.load(fh)
    
    sections = doc.get("Sections", {})
    replacements = 0
    
    for section_name, section in sections.items():
        if not isinstance(section, dict):
            continue
        
        for key, values in section.items():
            if key == "GUID":
                continue
            
            if not isinstance(values, list) or len(values) != 2:
                continue
            
            # Process each slot in the [background, foreground] pair
            for idx in (0, 1):
                val = values[idx]
                if not isinstance(val, str):
                    continue
                
                # Skip flag-based values like "05x00000000"
                if re.match(r"[0-9a-fA-F]{2}x[0-9a-fA-F]{8}", val):
                    continue
                
                # Normalize and check if it's a recognized color
                normalized = normalize_color(val)
                
                # Only update if it's a hex color (6 or 8 digits)
                if re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", normalized):
                    # Already in palette or needs mapping - preserve as-is
                    # (Future enhancement: could map old colors to nearest new palette color)
                    if normalized != val.strip('"').upper():
                        values[idx] = normalized
                        replacements += 1
    
    with yaml_path.open("w", encoding="utf-8") as fh:
        yaml.dump(doc, fh)
    
    return replacements


def load_yaml_doc(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return pyyaml.safe_load(fh)


def load_semantic_files(mappings_path: Path, roles_path: Path) -> Tuple[Dict[str, List[str]], Dict[str, Dict[str, Optional[str]]]]:
    mappings_raw = load_yaml_doc(mappings_path)
    roles_raw = load_yaml_doc(roles_path)
    if not isinstance(mappings_raw, dict) or not isinstance(roles_raw, dict):
        raise ValueError("Mappings or roles file malformed; expected top-level dicts.")

    # Normalize mappings: role -> list(classification keys)
    mappings: Dict[str, List[str]] = {}
    for role, keys in mappings_raw.items():
        if isinstance(keys, list):
            mappings[role] = [str(k) for k in keys]
        else:
            print(f"[warn] Role '{role}' has non-list mappings; skipping")

    # Normalize roles: allow either string (foreground only) or dict {foreground|fg, background|bg}
    roles: Dict[str, Dict[str, Optional[str]]] = {}
    for role, spec in roles_raw.items():
        if isinstance(spec, str):
            roles[role] = {"foreground": spec, "background": None}
        elif isinstance(spec, dict):
            fg = spec.get("foreground") or spec.get("fg")
            bg = spec.get("background") or spec.get("bg")
            roles[role] = {"foreground": fg, "background": bg}
        else:
            print(f"[warn] Role '{role}' has unsupported spec type; skipping")
    return mappings, roles


def build_role_color_maps(roles: Dict[str, Dict[str, Optional[str]]], palette_name_to_hex: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    fg_map: Dict[str, str] = {}
    bg_map: Dict[str, str] = {}
    for role, spec in roles.items():
        fg_name = spec.get("foreground")
        bg_name = spec.get("background")
        if fg_name:
            hx_fg = palette_name_to_hex.get(fg_name)
            if hx_fg:
                fg_map[role] = hx_fg
            else:
                print(f"[warn] Foreground color name '{fg_name}' for role '{role}' not in palette.")
        if bg_name:
            hx_bg = palette_name_to_hex.get(bg_name)
            if hx_bg:
                bg_map[role] = hx_bg
            else:
                print(f"[warn] Background color name '{bg_name}' for role '{role}' not in palette.")
    return fg_map, bg_map


def detect_overlaps(mappings: Dict[str, List[str]]) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for role, keys in mappings.items():
        for k in keys:
            lk = k.lower()
            index.setdefault(lk, []).append(role)
    return {k: roles for k, roles in index.items() if len(roles) > 1}


def apply_semantic(yaml_path: Path,
                   mappings: Dict[str, List[str]],
                   fg_map: Dict[str, str],
                   bg_map: Dict[str, str],
                   dry_run: bool = False,
                   report: bool = False,
                   palette_colors: Optional[Set[str]] = None) -> int:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    with yaml_path.open("r", encoding="utf-8") as fh:
        doc = yaml.load(fh)
    sections = doc.get("Sections", {})

    # Flatten classification lookup to section -> key
    changed = 0
    planned: List[str] = []
    applied_items: List[str] = []
    # Normalize keys for matching (case-insensitive)
    role_to_keys_ci = {role: {k.lower(): k for k in keys} for role, keys in mappings.items()}

    for section_name, section in sections.items():
        if not isinstance(section, dict):
            continue
        for key, pair in section.items():
            if key == "GUID" or not isinstance(pair, list) or len(pair) != 2:
                continue
            key_ci = key.lower()
            for role, keys_ci in role_to_keys_ci.items():
                if key_ci in keys_ci:
                    # Foreground
                    target_fg = fg_map.get(role)
                    if target_fg:
                        current_fg = pair[1]
                        if isinstance(current_fg, str) and current_fg.upper() != target_fg.upper():
                            planned.append(f"FG {key} -> {target_fg} (was {current_fg})")
                            if not dry_run:
                                pair[1] = target_fg
                                changed += 1
                                applied_items.append(f"FG {key}: {current_fg} -> {target_fg}")
                    # Background
                    target_bg = bg_map.get(role)
                    if target_bg:
                        current_bg = pair[0]
                        # Skip flag-coded or non-hex backgrounds (e.g., 05x..., null markers)
                        if isinstance(current_bg, str) and not re.match(r"^[0-9A-Fa-f]{2}x[0-9A-Fa-f]{8}$", current_bg):
                            if current_bg.upper() != target_bg.upper():
                                planned.append(f"BG {key} -> {target_bg} (was {current_bg})")
                                if not dry_run:
                                    pair[0] = target_bg
                                    changed += 1
                                    applied_items.append(f"BG {key}: {current_bg} -> {target_bg}")
                    break  # stop scanning roles once matched

    if dry_run:
        print("Semantic dry-run changes:")
        for line in planned:
            print("  " + line)
        print(f"Planned {len(planned)} changes.")
        return 0
    with yaml_path.open("w", encoding="utf-8") as fh:
        yaml.dump(doc, fh)
    print(f"Applied {changed} semantic changes (fg+bg).")

    if report:
        print("\nChange Report:")
        for item in applied_items:
            print("  " + item)
        if palette_colors:
            # Audit palette usage
            used: Set[str] = set()
            for section in sections.values():
                if isinstance(section, dict):
                    for v in section.values():
                        if isinstance(v, list) and len(v) == 2:
                            for idx in (0, 1):
                                c = v[idx]
                                if isinstance(c, str):
                                    norm = normalize_color(c)
                                    if re.fullmatch(r"#[0-9A-F]{6}(?:[0-9A-F]{2})?", norm):
                                        used.add(norm.upper())
            unused = sorted([c for c in palette_colors if c.upper() not in used])
            print("\nPalette Usage Audit:")
            print(f"  Total palette colors: {len(palette_colors)}")
            print(f"  Used colors: {len(used)}")
            print(f"  Unused colors ({len(unused)}):")
            for c in unused:
                print("    " + c)
    return changed


def parse_args(argv: List[str]):
    ap = argparse.ArgumentParser(description="Normalize or semantically remap Honeypunk theme colors.")
    ap.add_argument("--semantic", action="store_true", help="Enable semantic role remapping mode.")
    ap.add_argument("--mappings", default="tools/mappings.yaml", help="Path to semantic mappings YAML.")
    ap.add_argument("--roles", default="tools/roles.yaml", help="Path to role->palette color YAML.")
    ap.add_argument("--dry-run", action="store_true", help="Show planned semantic changes without writing.")
    ap.add_argument("--report", action="store_true", help="After applying, emit detailed change and palette usage report.")
    return ap.parse_args(argv)


from typing import Optional

def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    root = Path(__file__).resolve().parents[1]
    palette_path = root / "docs" / "palette.md"
    yaml_path = root / "Honeypunk.yaml"
    
    if not palette_path.exists():
        print(f"Error: {palette_path} not found")
        return 1
    
    if not yaml_path.exists():
        print(f"Error: {yaml_path} not found")
        return 1
    
    # Load palette (colors set + name->hex map)
    palette_colors, name_to_hex = parse_palette_md(palette_path)

    if args.semantic:
        mappings_path = Path(args.mappings)
        roles_path = Path(args.roles)
        if not mappings_path.exists():
            print(f"Error: mappings file {mappings_path} not found")
            return 1
        if not roles_path.exists():
            print(f"Error: roles file {roles_path} not found")
            return 1
        mappings, roles = load_semantic_files(mappings_path, roles_path)
        overlaps = detect_overlaps(mappings)
        if overlaps:
            print("[warn] Overlapping classification keys detected:")
            for key, roles_list in overlaps.items():
                print(f"  {key} in roles: {', '.join(roles_list)}")
        fg_map, bg_map = build_role_color_maps(roles, name_to_hex)
        apply_semantic(yaml_path, mappings, fg_map, bg_map, dry_run=args.dry_run, report=args.report, palette_colors=palette_colors)
    else:
        count = update_yaml_colors(yaml_path, palette_colors)
        print(f"Normalized {count} color values in {yaml_path.name}")
        print("(Use --semantic to apply role-based color assignments.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
