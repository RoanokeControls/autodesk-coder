#!/usr/bin/env python3
"""Index exported Fusion library data into the MCP server's search corpus.

Usage:
    python3 scripts/index_library.py [library-json-files...]

If no files are specified, processes all .json files in library-data/
"""

import json
import sys
from pathlib import Path

LIBRARY_DIR = Path(__file__).parent.parent / "library-data"
PARSED_DIR = Path(__file__).parent.parent / "parsed-docs"


def index_library(lib_path):
    """Parse a library JSON export and return search items + structured data."""
    with open(lib_path) as f:
        lib = json.load(f)

    raw_name = lib.get("library_name", lib_path.stem)
    # Sanitize: extract just the meaningful name from full paths
    # e.g. "/var/.../REC_Standard_Library v365.lbr" -> "REC_Standard_Library"
    import re as _re
    lib_name = raw_name.split("/")[-1]  # Get filename from path
    lib_name = _re.sub(r'\s*v\d+\.lbr$', '', lib_name)  # Strip version and .lbr
    lib_name = _re.sub(r'\.lbr$', '', lib_name)  # Strip .lbr if no version
    lib_name = lib_name.strip()
    if not lib_name:
        lib_name = lib_path.stem
    def safe_id(s):
        """Make a string safe for use as a file name / JSON key."""
        return _re.sub(r'[^a-zA-Z0-9_.-]', '_', s)

    print(f"  Library: {lib_name} (from: {raw_name})")
    print(f"    Devicesets: {len(lib.get('devicesets', []))}")
    print(f"    Footprints: {len(lib.get('footprints', []))}")
    print(f"    Symbols: {len(lib.get('symbols', []))}")

    search_items = []
    parts = {}

    # Index devicesets (these are the "components" users think of)
    for ds in lib.get("devicesets", []):
        ds_name = ds["name"]
        ds_id = safe_id(f"lib_{lib_name}_{ds_name}")

        # Collect all package variants
        variants = []
        for dev in ds.get("devices", []):
            variant_name = dev.get("name", "")
            full_name = ds_name + variant_name if variant_name else ds_name
            fp = dev.get("footprint", "")
            variants.append({
                "name": full_name,
                "footprint": fp,
                "technologies": dev.get("technologies", ""),
            })

        # Collect gate/symbol info
        gates = []
        for g in ds.get("gates", []):
            gates.append({
                "name": g["name"],
                "symbol": g["symbol"],
            })

        part_data = {
            "id": ds_id,
            "library": lib_name,
            "name": ds_name,
            "prefix": ds.get("prefix", ""),
            "description": ds.get("description", ""),
            "headline": ds.get("headline", ""),
            "value_on": ds.get("value", "") == "On",
            "variants": variants,
            "gates": gates,
        }
        parts[ds_id] = part_data

        # Build description for search
        variant_names = ", ".join(v["name"] for v in variants[:5])
        footprints = ", ".join(set(v["footprint"] for v in variants if v["footprint"]))
        desc = ds.get("description", "") or ds.get("headline", "")
        search_desc = f"{desc}. Prefix: {ds.get('prefix', '')}. Footprints: {footprints}. Variants: {variant_names}"

        search_items.append({
            "id": ds_id,
            "type": "library_part",
            "name": ds_name,
            "class_name": lib_name,
            "namespace": f"Library/{lib_name}",
            "description": search_desc[:300],
        })

        # Also index each variant as a separate searchable item
        for v in variants:
            if v["name"] != ds_name:  # Don't duplicate the base name
                search_items.append({
                    "id": safe_id(f"lib_{lib_name}_{v['name']}"),
                    "type": "library_variant",
                    "name": v["name"],
                    "class_name": lib_name,
                    "namespace": f"Library/{lib_name}",
                    "description": f"Variant of {ds_name}. Footprint: {v['footprint']}. {desc[:150]}",
                })

    # Index footprints
    for fp in lib.get("footprints", []):
        fp_name = fp["name"]
        pad_count = len(fp.get("pads", []))
        smd_count = len(fp.get("smds", []))
        desc = fp.get("description", "") or fp.get("headline", "")
        contact_desc = f"{pad_count} through-hole pads" if pad_count else ""
        if smd_count:
            contact_desc += (", " if contact_desc else "") + f"{smd_count} SMD pads"

        search_items.append({
            "id": safe_id(f"lib_{lib_name}_fp_{fp_name}"),
            "type": "library_footprint",
            "name": fp_name,
            "class_name": lib_name,
            "namespace": f"Library/{lib_name}",
            "description": f"Footprint. {contact_desc}. {desc[:200]}",
        })

    # Index symbols
    for sym in lib.get("symbols", []):
        sym_name = sym["name"]
        pin_count = len(sym.get("pins", []))
        pin_names = ", ".join(p["name"] for p in sym.get("pins", [])[:10])
        desc = sym.get("description", "") or sym.get("headline", "")

        search_items.append({
            "id": safe_id(f"lib_{lib_name}_sym_{sym_name}"),
            "type": "library_symbol",
            "name": sym_name,
            "class_name": lib_name,
            "namespace": f"Library/{lib_name}",
            "description": f"Symbol with {pin_count} pins: {pin_names}. {desc[:150]}",
        })

    return search_items, parts, lib_name


def main():
    # Determine which files to process
    if len(sys.argv) > 1:
        lib_files = [Path(f) for f in sys.argv[1:]]
    else:
        lib_files = sorted(LIBRARY_DIR.glob("*.json"))

    if not lib_files:
        print("No library JSON files found.")
        print(f"Export your library using the ULP script and save to: {LIBRARY_DIR}/")
        print("Then run this script again.")
        return

    print(f"Processing {len(lib_files)} library file(s)...")

    all_search_items = []
    all_parts = {}

    for lib_file in lib_files:
        print(f"\nProcessing {lib_file.name}...")
        items, parts, lib_name = index_library(lib_file)
        all_search_items.extend(items)
        all_parts.update(parts)

    print(f"\nGenerated {len(all_search_items)} search items from {len(all_parts)} parts")

    # Save structured parts data
    lib_out_dir = PARSED_DIR / "library"
    lib_out_dir.mkdir(exist_ok=True)
    for pid, part in all_parts.items():
        with open(lib_out_dir / f"{pid}.json", 'w') as f:
            json.dump(part, f, indent=2)

    # Save library index
    lib_index = {
        "parts": {pid: {"name": p["name"], "library": p["library"], "prefix": p["prefix"],
                         "description": p["description"][:200]}
                  for pid, p in all_parts.items()},
    }
    with open(lib_out_dir / "library_index.json", 'w') as f:
        json.dump(lib_index, f, indent=2)

    # Update search corpus
    corpus_path = PARSED_DIR / "search_corpus.json"
    with open(corpus_path) as f:
        corpus = json.load(f)

    # Remove previous library items
    corpus = [item for item in corpus if not item["id"].startswith("lib_")]

    corpus.extend(all_search_items)
    with open(corpus_path, 'w') as f:
        json.dump(corpus, f, indent=2)

    print(f"Updated search corpus: {len(corpus)} total items")

    # Update master index
    index_path = PARSED_DIR / "index.json"
    with open(index_path) as f:
        master_index = json.load(f)

    master_index["libraries"] = {
        "part_ids": list(all_parts.keys()),
        "library_names": list(set(p["library"] for p in all_parts.values())),
    }
    with open(index_path, 'w') as f:
        json.dump(master_index, f, indent=2)

    print("Done! Rebuild the MCP server to pick up the changes.")


if __name__ == "__main__":
    main()
