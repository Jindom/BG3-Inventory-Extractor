"""
BG3 Save File Inventory Extractor
==================================
Extracts character inventories and camp stash items from a BG3 save file (.lsv).
Produces a text report suitable for feeding to AI for equipment suggestions.

Requirements:
  - Python 3.8+
  - Divine.exe (from lslib / ExportTool) in PATH or specified via --divine

Usage:
  python bg3_inventory.py --save "path/to/quicksave.lsv"
  python bg3_inventory.py --save "path/to/quicksave.lsv" --ignore-mods
  python bg3_inventory.py --save "path/to/quicksave.lsv" --divine "path/to/Divine.exe"
"""

import xml.etree.ElementTree as ET
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

# ─── Known mod prefixes / suffixes ───────────────────────────────────────────

MOD_PREFIXES = (
    'AMX_', 'OBSC_', 'TMOG_', 'U_Autoloot', 'AC_OBJ_', 'CBR_', 'Slutty_',
    'PK_', 'KISS_', 'LADY_', 'SPIDERS_', 'DAUGHTER_', 'NH_', 'NHC_', 'MC_',
    'HW_', 'CALEB_', 'MOURNINGLACE_', 'Headpiece_', 'DRYAD_', 'Dryad_',
    'BLOOD_', 'SILVER_', 'SY_', 'RAF_', 'MOO_', 'DLC_', 'DARK_', 'WYR_',
    'NIGHT_', 'SUN_', 'TIF_', 'HARPY_', 'LaDSv2_', 'Popper_', 'Prosthesis_',
    'Wild_', 'Winged_', 'Veil_', 'Desiree_', 'Dream_', 'Collector_', 'Nurse_',
    'Necromancer_', 'Tops_', 'Dominion_', 'Decadent_', 'Emperor_',
    'CAMP_ARM_', 'HEART_', 'Painting_', 'Underwear_', 'Body_Backpack_',
    'Dresses_Backpack_', 'Robe_', 'ARM_HUM_M_', 'ARM_Lahn_',
    'ARM_Instrument_', 'MourningLace_', 'Mykys_', 'OBJ_Armours_and_Clothes_',
    'Agility_', 'Alfira_', 'Automaton_', 'Black_', 'Bonespike_', 'Butler_',
    'Chainshirt_', 'Scalemail_', 'CU_', 'C_', 'Feather_', 'LOW_', 'Mask_',
    'MMY_', 'ARN_', 'Spawn_', 'Necklace_', 'Longsword_', 'ARM_Shoes_Camp_Lahn',
    'Bard_', 'Bhaalist_', 'Dribbles_', 'Drow_', 'Druid_', 'Food_',
    'Githyanki_', 'Helldusk_', 'Jaheira_', 'Jannath_', 'Jergal_',
    'Justiciar_', "Ketheric's_", 'Mizora_', 'Monk_', "Nightsong's_",
    'Oathbreaker_', "Orin's_", 'Selunite_', 'Soul_', 'Surgeon_', 'Viconia_',
    "Vlaakith's_", 'Wavemother_', 'DefaultBodies_', 'Snare_', 'HUM_F_',
    'CLT_', 'LOOT_Lahn', 'OBJ_MB', 'OBJ_ImmutableContainer', 'UNI_Daisy',
    'OBJ_Haunted_', 'OBJ_BlosBag_', 'OBJ_Camp_Clothes_Bag', 'OBJ_MusicBox',
    'OBJ_Camp_Pack',
)

MOD_SUFFIXES = ('_KEL', '_MSK', '_BCB')

# Internal body / system items to skip
SKIP_STATS_LOWER = {
    'obj_bodypart_generic_head', 'obj_bodypart_generic_body',
    'obj_bodypart', 'obj_genericlootitem', 'obj_internalcontainer',
}

# ─── Helper functions ────────────────────────────────────────────────────────

def find_divine(hint_path=None):
    """Locate Divine.exe. Checks: explicit path -> divine/ subfolder -> same folder -> PATH."""
    if hint_path:
        if os.path.isfile(hint_path):
            return os.path.abspath(hint_path)
        raise FileNotFoundError(f"Divine.exe not found at: {hint_path}")

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Check bundled divine/ subfolder (pre-packaged)
    bundled = os.path.join(script_dir, "divine", "Divine.exe")
    if os.path.isfile(bundled):
        return bundled

    # Check same directory as this script
    local = os.path.join(script_dir, "Divine.exe")
    if os.path.isfile(local):
        return local

    # Check PATH
    found = shutil.which("Divine.exe") or shutil.which("divine")
    if found:
        return found

    raise FileNotFoundError(
        "Cannot find Divine.exe. Place it next to this script, in a divine/ subfolder, or use --divine."
    )


def run_divine(divine_exe, action, extra_args):
    """Run Divine.exe with the given action and arguments."""
    cmd = [divine_exe, "-g", "bg3", "-a", action] + extra_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[ERROR] Divine.exe failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def extract_save(divine_exe, lsv_path, output_dir):
    """Extract .lsv save to output directory."""
    print(f"  Extracting save: {os.path.basename(lsv_path)} ...")
    run_divine(divine_exe, "extract-package",
               ["-s", lsv_path, "-d", output_dir])


def convert_lsf_to_lsx(divine_exe, lsf_path, lsx_path):
    """Convert a single .lsf file to .lsx (XML)."""
    run_divine(divine_exe, "convert-resource",
               ["-i", "lsf", "-o", "lsx", "-s", lsf_path, "-d", lsx_path])


def convert_all_lsf(divine_exe, directory):
    """Convert every .lsf in directory (recursively) to .lsx in-place."""
    lsf_files = glob.glob(os.path.join(directory, "**", "*.lsf"), recursive=True)
    if not lsf_files:
        print("  No .lsf files found to convert.")
        return
    print(f"  Converting {len(lsf_files)} LSF file(s) to XML ...")
    for lsf in lsf_files:
        lsx = lsf.rsplit(".", 1)[0] + ".lsx"
        convert_lsf_to_lsx(divine_exe, lsf, lsx)


def is_mod_item(stats):
    if stats.startswith(MOD_PREFIXES):
        return True
    for s in MOD_SUFFIXES:
        if s in stats:
            return True
    return False


def parse_position(pos_str):
    return tuple(float(p) for p in pos_str.strip().split())


def positions_match(pos1, pos2, tol=0.01):
    return all(abs(a - b) < tol for a, b in zip(pos1, pos2))


# ─── Save data readers ───────────────────────────────────────────────────────

def read_save_info(output_dir):
    """Read SaveInfo.json and return character metadata + party positions."""
    path = os.path.join(output_dir, "SaveInfo.json")
    if not os.path.isfile(path):
        print("[WARN] SaveInfo.json not found – character names may be generic.",
              file=sys.stderr)
        return None, {}
    with open(path, "r", encoding="utf-8") as f:
        info = json.load(f)

    # Build character positions dict  {label: (x,y,z)}
    char_positions = {}
    for ch in info.get("Active Party", {}).get("Characters", []):
        origin = ch.get("Origin", "Unknown")
        race = ch.get("Race", "")
        level = ch.get("Level", "?")
        classes = ch.get("Classes", [])
        main_class = classes[0].get("Main", "?") if classes else "?"
        sub_class = classes[0].get("Sub", "") if classes else ""

        # Build friendly race name
        race_pretty = race.replace("_", " ").replace("Elf HighElf", "High Elf") \
                          .replace("HalfElf High", "Half-Elf")

        if origin == "Generic":
            label = f"Custom {main_class} ({race_pretty}, {sub_class}, Level {level})"
        else:
            label = f"{origin} ({race_pretty} {main_class}, {sub_class}, Level {level})"

        pos = ch.get("Position", [0, 0, 0])
        char_positions[label] = tuple(pos)

    return info, char_positions


def get_template_names(globals_root):
    """Build template UUID -> display name mapping from CacheTemplates."""
    template_map = {}
    region = globals_root.find('.//region[@id="CacheTemplates"]')
    if region is None:
        return template_map
    for tmpl in region.findall('.//node[@id="Template"]'):
        mapkey = name = stats = ""
        for attr in tmpl.findall('attribute'):
            aid = attr.get('id')
            if aid == 'MapKey':   mapkey = attr.get('value', '')
            elif aid == 'Name':   name   = attr.get('value', '')
            elif aid == 'Stats':  stats  = attr.get('value', '')
        if mapkey:
            template_map[mapkey] = name or stats or mapkey
    return template_map


def collect_items(filepath):
    """Parse items from an LSX file. Returns only current-state items (2nd half)."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    nodes = root.findall('.//region[@id="Items"]//node[@id="Items"]//node[@id="Item"]')
    half = len(nodes) // 2
    items = []
    for node in nodes[half:]:
        data = {}
        for attr in node.findall('attribute'):
            data[attr.get('id')] = attr.get('value', '')
        if 'Translate' in data and 'Stats' in data:
            items.append({
                'pos':      parse_position(data['Translate']),
                'stats':    data.get('Stats', ''),
                'template': data.get('CurrentTemplate', ''),
                'flags':    int(data.get('Flags', '0')),
            })
    return items


def categorize_item(stats):
    s = stats.lower()
    if s.startswith('wpn_'):
        return 'Weapons'
    if 'amulet' in s or 'ring' in s or 'necklace' in s or 'circlet' in s:
        return 'Jewelry & Accessories'
    if s.startswith('arm_') and ('vanity' in s or 'camp' in s or 'hat' in s or 'shoes' in s):
        return 'Clothing & Vanity'
    if s.startswith('arm_') or any(k in s for k in ('armor', 'mail', 'leather', 'robe',
        'shield', 'plate', 'gloves', 'boots', 'helmet', 'cloak')):
        return 'Armor & Equipment'
    if 'scroll' in s and 'case' not in s:
        return 'Scrolls'
    if 'arrow' in s:
        return 'Ammunition'
    if 'potion' in s or s.startswith('cons_') or s.startswith('alch_solution'):
        return 'Potions & Elixirs'
    if s.startswith('alch_ingredient'):
        return 'Alchemy Ingredients'
    if 'puz_key' in s or s.endswith('key') or 'key_' in s:
        return 'Keys'
    if any(k in s for k in ('book', 'journal', 'letter', 'note', 'diary', 'recipe', 'plans', 'lore', 'orders')):
        return 'Books & Documents'
    if any(k in s for k in ('bag', 'backpack', 'chest', 'pouch', 'quiver', 'case', 'box')):
        return 'Containers'
    if s.startswith('mag_') or s.startswith('uni_'):
        return 'Magic Items'
    if 'quest' in s or s.startswith('glo_') or any(k in s for k in ('coin', 'crystal', 'bulb')):
        return 'Quest & Special Items'
    if any(s.startswith(p) for p in ('for_', 'scl_', 'den_', 's_')):
        return 'Story Items'
    if any(k in s for k in ('food', 'drink', 'herb', 'sausage', 'cheese')):
        return 'Food & Supplies'
    if 'dye' in s:
        return 'Dyes'
    if s.startswith('obj_') and any(k in s for k in ('poison', 'bottle', 'bomb', 'grenade', 'trap')):
        return 'Throwables & Coatings'
    if s.startswith('obj_') and any(k in s for k in ('tool', 'kit', 'shovel', 'torch')):
        return 'Tools'
    if any(k in s for k in ('valuable', 'gem', 'gold')):
        return 'Valuables'
    if 'toy' in s or 'sponge' in s:
        return 'Miscellaneous'
    return 'Other'


def display_name(stats, template, template_map):
    n = template_map.get(template, '')
    return n if n and n != template else stats


# ─── Report builder ──────────────────────────────────────────────────────────

def build_report(output_dir, char_positions, save_info, ignore_mods):
    globals_lsx = os.path.join(output_dir, "Globals.lsx")
    if not os.path.isfile(globals_lsx):
        print(f"[ERROR] Globals.lsx not found in {output_dir}", file=sys.stderr)
        sys.exit(1)

    print("  Parsing Globals.lsx (this may take a moment for large saves) ...")
    tree = ET.parse(globals_lsx)
    root = tree.getroot()
    template_map = get_template_names(root)

    print("  Collecting items ...")
    all_items = collect_items(globals_lsx)
    print(f"  Found {len(all_items)} items in Globals")

    # Header
    lines = []
    lines.append("=" * 70)
    mode = "Vanilla Items Only" if ignore_mods else "All Items (Including Mods)"
    lines.append(f"BG3 SAVE FILE - INVENTORY REPORT ({mode})")
    lines.append("=" * 70)
    if save_info:
        lines.append(f"Save Name    : {save_info.get('Save Name', 'N/A')}")
        lines.append(f"Game Version : {save_info.get('Game Version', 'N/A')}")
        lines.append(f"Current Level: {save_info.get('Current Level', 'N/A')}")
        diff = save_info.get('Difficulty', [])
        lines.append(f"Difficulty   : {' / '.join(diff)}")
    lines.append("")

    def should_skip(stats):
        if stats.lower() in SKIP_STATS_LOWER:
            return True
        if ignore_mods and is_mod_item(stats):
            return True
        return False

    # Per-character inventories
    assigned = set()
    for char_label, char_pos in char_positions.items():
        matching = []
        for i, it in enumerate(all_items):
            if positions_match(it['pos'], char_pos) and not should_skip(it['stats']):
                matching.append(it)
                assigned.add(i)

        lines.append("")
        lines.append("=" * 70)
        lines.append(f"  {char_label}")
        lines.append(f"  Total items: {len(matching)}")
        lines.append("=" * 70)

        by_cat = defaultdict(list)
        for it in matching:
            dn = display_name(it['stats'], it['template'], template_map)
            by_cat[categorize_item(it['stats'])].append(dn)

        for cat in sorted(by_cat):
            counted = Counter(by_cat[cat])
            lines.append(f"\n  [{cat}] ({len(by_cat[cat])} items)")
            for name, cnt in sorted(counted.items()):
                qty = f" x{cnt}" if cnt > 1 else ""
                lines.append(f"    - {name}{qty}")

    # Camp stash & other locations
    lines.append("")
    lines.append("=" * 70)
    lines.append("  CAMP SUPPLY / STASH ITEMS")
    lines.append("=" * 70)

    by_pos = defaultdict(list)
    for i, it in enumerate(all_items):
        if i in assigned or should_skip(it['stats']):
            continue
        is_char = any(positions_match(it['pos'], cp) for cp in char_positions.values())
        if is_char:
            continue
        key = tuple(round(c, 2) for c in it['pos'])
        by_pos[key].append(it)

    big = [(p, its) for p, its in by_pos.items() if len(its) >= 5]
    big.sort(key=lambda x: -len(x[1]))

    for pos, items in big[:10]:
        lines.append(f"\n  Location ({pos[0]}, {pos[1]}, {pos[2]}): {len(items)} items")
        by_cat = defaultdict(list)
        for it in items:
            dn = display_name(it['stats'], it['template'], template_map)
            by_cat[categorize_item(it['stats'])].append(dn)
        for cat in sorted(by_cat):
            counted = Counter(by_cat[cat])
            lines.append(f"    [{cat}] ({len(by_cat[cat])} items)")
            for name, cnt in sorted(counted.items()):
                qty = f" x{cnt}" if cnt > 1 else ""
                lines.append(f"      - {name}{qty}")

    small = [(p, its) for p, its in by_pos.items() if 1 <= len(its) < 5]
    if small:
        total = sum(len(its) for _, its in small)
        lines.append(f"\n  Other scattered items ({total} items at {len(small)} locations):")
        for pos, items in sorted(small, key=lambda x: -len(x[1]))[:20]:
            for it in items:
                dn = display_name(it['stats'], it['template'], template_map)
                lines.append(f"    - {dn} at ({pos[0]}, {pos[1]}, {pos[2]})")

    return "\n".join(lines)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="BG3 Save Inventory Extractor – extract item lists from a .lsv save file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bg3_inventory.py --save "C:\\saves\\quicksave.lsv"
  python bg3_inventory.py --save my_save.lsv --ignore-mods
  python bg3_inventory.py --save my_save.lsv --divine "C:\\tools\\Divine.exe" -o report.txt
        """,
    )
    parser.add_argument("--save", required=True,
                        help="Path to the .lsv save file")
    parser.add_argument("--divine", default=None,
                        help="Path to Divine.exe (auto-detected if next to this script or in PATH)")
    parser.add_argument("--ignore-mods", action="store_true",
                        help="Filter out known modded items and show only vanilla items")
    parser.add_argument("-o", "--output", default=None,
                        help="Output report file path (default: inventory_report.txt next to save)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Keep the temporary extraction folder (for debugging)")

    args = parser.parse_args()

    # Validate save file
    save_path = os.path.abspath(args.save)
    if not os.path.isfile(save_path):
        print(f"[ERROR] Save file not found: {save_path}", file=sys.stderr)
        sys.exit(1)

    # Locate Divine.exe
    divine_exe = find_divine(args.divine)
    print(f"[OK] Divine.exe : {divine_exe}")
    print(f"[OK] Save file  : {save_path}")

    # Create temp working directory next to the save file
    save_dir = os.path.dirname(save_path)
    save_stem = os.path.splitext(os.path.basename(save_path))[0]
    work_dir = os.path.join(save_dir, f"_bg3inv_{save_stem}")

    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir)
    os.makedirs(work_dir)

    try:
        # Step 1: Extract .lsv
        print("\n[Step 1/3] Extracting save archive ...")
        extract_save(divine_exe, save_path, work_dir)

        # Step 2: Convert all .lsf → .lsx
        print("[Step 2/3] Converting LSF files to XML ...")
        convert_all_lsf(divine_exe, work_dir)

        # Step 3: Parse & build report
        print("[Step 3/3] Parsing inventory data ...")
        save_info, char_positions = read_save_info(work_dir)
        if not char_positions:
            print("[ERROR] No characters found in SaveInfo.json", file=sys.stderr)
            sys.exit(1)

        report = build_report(work_dir, char_positions, save_info, args.ignore_mods)

        # Write output
        if args.output:
            out_path = os.path.abspath(args.output)
        else:
            out_path = os.path.join(save_dir, f"{save_stem}_inventory.txt")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)

        line_count = report.count('\n') + 1
        print(f"\n{'='*50}")
        print(f"  Report saved to: {out_path}")
        print(f"  Total lines: {line_count}")
        if args.ignore_mods:
            print(f"  Mode: Vanilla items only (mod items filtered)")
        else:
            print(f"  Mode: All items (including mods)")
        print(f"{'='*50}")
        print(f"\nTip: Feed this report to an AI chatbot and ask:")
        print(f'  "Based on my inventory and party composition,')
        print(f'   what equipment should each character use?"')

    finally:
        if not args.keep_temp:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            print(f"\n[DEBUG] Temp files kept at: {work_dir}")


if __name__ == "__main__":
    main()
