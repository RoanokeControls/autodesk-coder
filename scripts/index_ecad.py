#!/usr/bin/env python3
"""Index ECAD/ULP docs and merge into the MCP server's search corpus."""

import json
import re
from pathlib import Path

ECAD_DIR = Path(__file__).parent.parent / "raw-docs" / "ECAD"
PARSED_DIR = Path(__file__).parent.parent / "parsed-docs"


def extract_members_from_content(content):
    """Extract data members and loop members from ULP object content."""
    data_members = []
    loop_members = []

    # Find data members table
    in_data = False
    in_loop = False
    for line in content.split("\n"):
        if "## Data members" in line:
            in_data = True
            in_loop = False
            continue
        if "## Loop members" in line:
            in_loop = True
            in_data = False
            continue
        if line.startswith("## ") and "members" not in line.lower():
            in_data = False
            in_loop = False
            continue

        # Parse table rows
        if line.startswith("|") and "---" not in line:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 2 and cells[0]:
                name = cells[0].strip()
                type_info = cells[1].strip()
                if name and not name.startswith("---"):
                    if in_data:
                        data_members.append({"name": name, "type": type_info})
                    elif in_loop:
                        loop_members.append({"name": name, "type": type_info})

    return data_members, loop_members


def parse_ulp_object(page):
    """Parse a ULP object type page into structured data."""
    content = page["content"]
    title = page["title"]

    data_members, loop_members = extract_members_from_content(content)

    # Extract description (text between title and first ## section)
    desc = ""
    lines = content.split("\n")
    collecting = False
    for line in lines:
        if line.startswith("# ") and not collecting:
            collecting = True
            continue
        if collecting:
            if line.startswith("## "):
                break
            desc += line.strip() + " "
    desc = desc.strip()

    return {
        "id": page["id"],
        "title": title,
        "type": "ulp_object",
        "description": desc,
        "data_members": data_members,
        "loop_members": loop_members,
        "content": content,
    }


def parse_ecad_page(page):
    """Parse a general ECAD page."""
    content = page["content"]
    # Extract first meaningful paragraph as description
    desc = ""
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("|") and not line.startswith("```") and len(line) > 20:
            desc = line[:300]
            break

    return {
        "id": page["id"],
        "title": page["title"],
        "type": page["category"],
        "description": desc,
        "content": content,
    }


def main():
    # Load all ECAD docs
    ecad_docs_path = ECAD_DIR / "ecad_docs.json"
    with open(ecad_docs_path) as f:
        all_pages = json.load(f)

    print(f"Processing {len(all_pages)} ECAD pages...")

    # Parse into structured data
    ecad_entries = {}
    for pid, page in all_pages.items():
        if page["category"] == "ulp_object":
            ecad_entries[pid] = parse_ulp_object(page)
        else:
            ecad_entries[pid] = parse_ecad_page(page)

    # Save structured ECAD data
    ecad_out_dir = PARSED_DIR / "ecad"
    ecad_out_dir.mkdir(exist_ok=True)
    for pid, entry in ecad_entries.items():
        with open(ecad_out_dir / f"{pid}.json", 'w') as f:
            json.dump(entry, f, indent=2)

    # Build search items for ECAD
    ecad_search_items = []

    for pid, entry in ecad_entries.items():
        if entry["type"] == "ulp_object":
            # Add the object itself
            ecad_search_items.append({
                "id": f"ecad_{pid}",
                "type": "ecad_object",
                "name": entry["title"],
                "namespace": "ECAD/ULP",
                "description": entry.get("description", ""),
            })
            # Add individual data members
            for m in entry.get("data_members", []):
                ecad_search_items.append({
                    "id": f"ecad_{pid}_{m['name']}",
                    "type": "ecad_member",
                    "name": m["name"],
                    "class_name": entry["title"],
                    "namespace": "ECAD/ULP",
                    "description": f"{entry['title']} data member. Type: {m['type']}",
                })
            # Add loop members
            for m in entry.get("loop_members", []):
                ecad_search_items.append({
                    "id": f"ecad_{pid}_{m['name']}",
                    "type": "ecad_loop",
                    "name": m["name"],
                    "class_name": entry["title"],
                    "namespace": "ECAD/ULP",
                    "description": f"{entry['title']} loop member. Returns: {m['type']}",
                })
        elif entry["type"] == "ulp_language":
            ecad_search_items.append({
                "id": f"ecad_{pid}",
                "type": "ecad_guide",
                "name": entry["title"],
                "namespace": "ECAD/ULP",
                "description": entry.get("description", ""),
            })
        elif entry["type"] == "ecad_command":
            ecad_search_items.append({
                "id": f"ecad_{pid}",
                "type": "ecad_command",
                "name": entry["title"],
                "namespace": "ECAD/Commands",
                "description": entry.get("description", ""),
            })
        else:
            ecad_search_items.append({
                "id": f"ecad_{pid}",
                "type": "ecad_guide",
                "name": entry["title"],
                "namespace": "ECAD",
                "description": entry.get("description", ""),
            })

    print(f"Generated {len(ecad_search_items)} ECAD search items")

    # Load existing search corpus and merge
    corpus_path = PARSED_DIR / "search_corpus.json"
    with open(corpus_path) as f:
        existing_corpus = json.load(f)

    # Remove any previous ECAD items
    existing_corpus = [item for item in existing_corpus if not item["id"].startswith("ecad_")]

    # Merge
    merged_corpus = existing_corpus + ecad_search_items
    with open(corpus_path, 'w') as f:
        json.dump(merged_corpus, f, indent=2)

    print(f"Merged search corpus: {len(existing_corpus)} existing + {len(ecad_search_items)} ECAD = {len(merged_corpus)} total")

    # Update the master index
    index_path = PARSED_DIR / "index.json"
    with open(index_path) as f:
        master_index = json.load(f)

    # Add ECAD section
    master_index["ecad"] = {
        "object_types": [pid for pid, e in ecad_entries.items() if e["type"] == "ulp_object"],
        "language_refs": [pid for pid, e in ecad_entries.items() if e["type"] == "ulp_language"],
        "command_refs": [pid for pid, e in ecad_entries.items() if e["type"] == "ecad_command"],
        "general": [pid for pid, e in ecad_entries.items() if e["type"] in ("ecad_general",)],
    }

    with open(index_path, 'w') as f:
        json.dump(master_index, f, indent=2)

    print(f"Updated master index with ECAD section")
    print("Done!")


if __name__ == "__main__":
    main()
