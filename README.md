# BG3 Inventory Extractor

Extract a full item inventory from any **Baldur's Gate 3** save file (`.lsv`) and get a clean text report you can feed to an AI chatbot for equipment advice.

---

## Features

- **One-command pipeline** – extracts the save, converts binary data to XML, parses items, and writes a report.
- **Automatic character detection** – reads `SaveInfo.json` from the save so it works with *any* party composition.
- **Mod filtering** (`--ignore-mods`) – optionally strips out items from ~100 known mod prefixes so you only see vanilla gear.
- **Categorised output** – items are grouped by type (Weapons, Armor, Scrolls, Potions, etc.) for each character and the camp stash.

---

## Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.8 or newer |
| **Divine.exe** | From [lslib / BG3 ExportTool](https://github.com/Norbyte/lslib/releases). Download the latest release and extract it. |

> **No additional Python packages are needed** – the script uses only the standard library.

---

## Setup

1. Download or clone this folder.
2. Download [ExportTool (lslib)](https://github.com/Norbyte/lslib/releases) and extract it.
3. Place `Divine.exe` (and its companion DLLs) either:
   - **Next to `bg3_inventory.py`**, or
   - **Anywhere in your system PATH**, or
   - Specify its location with `--divine "path/to/Divine.exe"`.

### Folder layout (recommended)

```
BG3-Inventory-Extractor/
├── bg3_inventory.py        ← this script
├── README.md               ← you are here
├── Divine.exe              ← from ExportTool
├── LSLib.dll               ← (companion DLL)
├── granny2.dll             ← (companion DLL)
└── ... other lslib DLLs
```

---

## Finding Your Save Files

BG3 saves are located at:

```
%LOCALAPPDATA%\Larian Studios\Baldur's Gate 3\PlayerProfiles\<Profile>\Savegames\Story\
```

Each save folder contains one or more `.lsv` files (e.g. `QuickSave.lsv`, `AutoSave_1.lsv`, etc.).

---

## Usage

### Basic (all items)

```bash
python bg3_inventory.py --save "C:\path\to\QuickSave.lsv"
```

### Vanilla only (filter out mod items)

```bash
python bg3_inventory.py --save "C:\path\to\QuickSave.lsv" --ignore-mods
```

### Specify Divine.exe location

```bash
python bg3_inventory.py --save "C:\path\to\QuickSave.lsv" --divine "D:\tools\Divine.exe"
```

### Custom output path

```bash
python bg3_inventory.py --save "C:\path\to\QuickSave.lsv" -o my_report.txt
```

### Keep temp files (debugging)

```bash
python bg3_inventory.py --save "C:\path\to\QuickSave.lsv" --keep-temp
```

---

## Command-Line Options

| Flag | Description |
|---|---|
| `--save PATH` | **(required)** Path to the `.lsv` save file |
| `--divine PATH` | Path to `Divine.exe` (auto-detected if next to script or in PATH) |
| `--ignore-mods` | Filter out known modded items; show only vanilla items |
| `-o, --output PATH` | Output report file (default: `<savename>_inventory.txt` next to save) |
| `--keep-temp` | Keep the temporary extraction folder for inspection |

---

## What To Do With the Report

Copy the contents of the generated `.txt` file and paste it into an AI chatbot (ChatGPT, Claude, Copilot, etc.) with a prompt like:

> Here is my BG3 party inventory. Based on each character's class, level, and current gear, what equipment should they be using? What should I prioritize finding or buying?

The report includes each character's class, race, and level alongside their full item list, giving the AI enough context to make useful suggestions.

---

## How It Works

1. **Extract** – `Divine.exe` unpacks the `.lsv` archive into raw files (`Globals.lsf`, `SaveInfo.json`, etc.).
2. **Convert** – `Divine.exe` converts binary `.lsf` files to human-readable `.lsx` (XML).
3. **Parse** – The Python script reads `SaveInfo.json` for character positions, then walks the XML to find every item. Items sharing a character's coordinates are assigned to that character's inventory; the rest go into the camp stash section.
4. **Report** – Items are categorised, counted, and written to a clean text file.

### Note on item pairing

BG3 stores items internally as `[original_state × N, current_state × N]`. The script automatically takes only the current-state half to avoid duplicates.

---

## Limitations

- The mod filter list covers many popular mods but may not catch every modded item. Items from unlisted mods will appear in the report (this is harmless).
- Only items from `Globals.lsx` are parsed (these include all party inventories and the camp stash). Level-specific world items in `LevelCache/` are not included since those are not player-owned.

---

## License

This tool is provided as-is for personal use. [lslib / Divine.exe](https://github.com/Norbyte/lslib) is developed by Norbyte and has its own license.
