#!/usr/bin/env python3
"""Incremental Fusion API doc updater.

Unlike parse_docs.py (which rebuilds EVERYTHING from a local raw-docs/HTML CHM
extraction), this script fetches ONLY the pages that the upstream "What's New"
page lists as new or changed, parses them with the exact same parser as
parse_docs.py, and MERGES the results into the existing parsed-docs/ data.

It preserves all existing API classes, ECAD/ULP docs, REC library entries, and
the per-member detail pages that were captured from the original CHM parse.

Use this to bring the local index up to a newer release without re-downloading
the full offline-help CHM.

Usage:
  python3 scripts/scrape_api_update.py            # fetch + merge
  python3 scripts/scrape_api_update.py --dry-run  # list target pages, fetch nothing
  python3 scripts/scrape_api_update.py --limit 20 # cap pages fetched (testing)
"""

import argparse
import importlib.util
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ROOT = SCRIPT_DIR.parent
PARSED = ROOT / "parsed-docs"
CLASSES_DIR = PARSED / "classes"
WORK_DIR = ROOT / "raw-docs" / "update-fetch"  # transient HTML cache

BASE = "https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/"
WHATSNEW_URL = BASE + "WhatsNew.htm"
USER_AGENT = "FusionAPIUpdateChecker/1.0"
THROTTLE_S = 0.3   # politeness delay between fetches
TIMEOUT_S = 20

# Reuse the exact parser from parse_docs.py (no duplication, no drift).
_spec = importlib.util.spec_from_file_location("parse_docs", SCRIPT_DIR / "parse_docs.py")
parse_docs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(parse_docs)


def fetch(url, retries=3):
    """GET a URL, return text or None (404 / persistent error)."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return r.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, OSError):
            time.sleep(1.5 * (attempt + 1))
    return None


def extract_targets(whatsnew_html):
    """From the What's New page, return (class_pages, member_pages).

    class_pages  -> {"Board", "EcadDesign", ...}            (Name.htm, no underscore)
    member_pages -> {"BRepBody_convertToSheetMetal", ...}   (Class_member.htm)
    Guides (_UM) and the page itself are excluded.
    """
    hrefs = re.findall(r'href="([A-Za-z0-9_]+\.htm)"', whatsnew_html)
    classes, members = set(), set()
    for h in hrefs:
        name = h[:-4]  # strip .htm
        if name == "WhatsNew" or name.endswith("_UM") or name.endswith("_Sample"):
            continue
        if "_" in name:
            members.add(name)
        else:
            classes.add(name)
    # Every member's parent class page is also (re)fetched so its
    # methods/properties tables reflect the new members.
    for m in members:
        classes.add(m.split("_", 1)[0])
    return classes, members


def fetch_pages(names, work_dir, limit=None):
    """Fetch each <name>.htm into work_dir, return list of parsed page dicts."""
    work_dir.mkdir(parents=True, exist_ok=True)
    pages, missing = [], []
    names = sorted(names)
    if limit:
        names = names[:limit]
    total = len(names)
    for i, name in enumerate(names, 1):
        html = fetch(BASE + name + ".htm")
        if html is None:
            missing.append(name)
            continue
        path = work_dir / f"{name}.htm"
        path.write_text(html, encoding="utf-8")
        page = parse_docs.parse_file(path)
        if page:
            pages.append(page)
        if i % 25 == 0 or i == total:
            print(f"  fetched {i}/{total} ...")
        time.sleep(THROTTLE_S)
    return pages, missing


def corpus_entries_for_class(cname, cls):
    """Build search_corpus entries for one class (mirrors parse_docs.main)."""
    items = [{
        "id": cname,
        "type": "class",
        "name": cname,
        "namespace": cls.get("namespace", ""),
        "description": cls.get("description", ""),
        "parent_class": cls.get("parent_class", ""),
    }]
    for m in cls.get("methods", []):
        items.append({
            "id": f"{cname}_{m['name']}", "type": "method", "class_name": cname,
            "name": m["name"], "namespace": cls.get("namespace", ""),
            "description": m.get("description", ""),
        })
    for p in cls.get("properties", []):
        items.append({
            "id": f"{cname}_{p['name']}", "type": "property", "class_name": cname,
            "name": p["name"], "namespace": cls.get("namespace", ""),
            "description": p.get("description", ""),
        })
    for e in cls.get("events", []):
        items.append({
            "id": f"{cname}_{e['name']}", "type": "event", "class_name": cname,
            "name": e["name"], "namespace": cls.get("namespace", ""),
            "description": e.get("description", ""),
        })
    return items


def merge_class(cname, fresh):
    """Merge a freshly-parsed class dict into the on-disk class JSON.

    New class  -> write fresh wholesale.
    Existing   -> update scalar fields + member tables from the fresh page,
                  and ADD new member-detail entries while preserving the
                  detail pages captured in the original CHM parse.
    Returns the merged dict.
    """
    path = CLASSES_DIR / f"{cname}.json"
    if not path.exists():
        return fresh
    existing = json.loads(path.read_text())
    for k in ("title", "namespace", "header_file", "description", "parent_class",
              "methods", "properties", "events", "syntax", "version"):
        if k in fresh:
            existing[k] = fresh[k]
    for dk in ("method_details", "property_details", "event_details", "member_details"):
        if dk in fresh:
            existing.setdefault(dk, {}).update(fresh[dk])
    return existing


def main():
    ap = argparse.ArgumentParser(description="Incrementally update Fusion API docs from cloudhelp")
    ap.add_argument("--dry-run", action="store_true", help="list target pages, fetch nothing")
    ap.add_argument("--limit", type=int, default=None, help="cap number of pages fetched (testing)")
    args = ap.parse_args()

    print("Fetching What's New ...")
    wn = fetch(WHATSNEW_URL)
    if not wn:
        print("ERROR: could not fetch What's New page.")
        sys.exit(1)

    version = parse_docs and None
    m = re.search(r"What.s New\s+(?:For\s+)?(?:the\s+)?(\w+\s+\d{4})\s+Release", wn, re.IGNORECASE)
    version = m.group(1) if m else "unknown"
    class_pages, member_pages = extract_targets(wn)
    print(f"Upstream release: {version}")
    print(f"Targets: {len(class_pages)} class pages, {len(member_pages)} member pages")

    if args.dry_run:
        print("\n-- class pages --")
        print("  " + ", ".join(sorted(class_pages)))
        print("\n-- member pages --")
        print("  " + ", ".join(sorted(member_pages)))
        return

    # Fetch class pages first (needed so members can embed into them), then members.
    print("\nFetching class pages ...")
    class_parsed, miss_c = fetch_pages(class_pages, WORK_DIR, args.limit)
    print("Fetching member pages ...")
    member_parsed, miss_m = fetch_pages(member_pages, WORK_DIR, args.limit)

    all_pages = class_parsed + member_parsed
    # build_class_index embeds member detail pages into their parent class dicts.
    classes, samples, guides = parse_docs.build_class_index(all_pages)
    print(f"\nParsed {len(classes)} classes "
          f"({len(class_parsed)} class pages, {len(member_parsed)} member pages)")

    # --- Load existing index + corpus ---
    index = json.loads((PARSED / "index.json").read_text())
    corpus = json.loads((PARSED / "search_corpus.json").read_text())

    changed = set(classes.keys())
    new_classes = sorted(c for c in changed if not (CLASSES_DIR / f"{c}.json").exists())

    # --- Merge each class to disk + refresh index entry + namespaces ---
    ns_added = {}
    for cname, fresh in classes.items():
        merged = merge_class(cname, fresh)
        (CLASSES_DIR / f"{cname}.json").write_text(json.dumps(merged, indent=2))

        index["classes"][cname] = {
            "namespace": merged.get("namespace", ""),
            "description": merged.get("description", "")[:200],
            "parent_class": merged.get("parent_class", ""),
            "method_count": len(merged.get("methods", [])),
            "property_count": len(merged.get("properties", [])),
            "event_count": len(merged.get("events", [])),
        }
        ns = merged.get("namespace", "") or "unknown"
        bucket = index["namespaces"].setdefault(ns, [])
        if cname not in bucket:
            bucket.append(cname)
            ns_added[ns] = ns_added.get(ns, 0) + 1

    for ns in index["namespaces"]:
        index["namespaces"][ns] = sorted(set(index["namespaces"][ns]))

    # --- Rebuild corpus: drop stale entries for changed classes, append fresh ---
    def stale(item):
        return ((item.get("type") == "class" and item.get("id") in changed)
                or item.get("class_name") in changed)

    new_corpus = [it for it in corpus if not stale(it)]
    for cname in classes:
        merged = json.loads((CLASSES_DIR / f"{cname}.json").read_text())
        new_corpus.extend(corpus_entries_for_class(cname, merged))

    (PARSED / "index.json").write_text(json.dumps(index, indent=2))
    (PARSED / "search_corpus.json").write_text(json.dumps(new_corpus, indent=2))

    # --- Report ---
    print("\n=== MERGE COMPLETE ===")
    print(f"  classes written/updated : {len(classes)}")
    print(f"  brand-new classes       : {len(new_classes)}")
    print(f"  corpus items            : {len(corpus)} -> {len(new_corpus)}")
    if ns_added:
        print("  classes added per namespace:")
        for ns, n in sorted(ns_added.items()):
            print(f"    {ns}: +{n}")
    if miss_c or miss_m:
        print(f"  pages not found (404)   : {len(miss_c) + len(miss_m)}")
        if miss_c:
            print("    classes:", ", ".join(miss_c[:20]) + (" ..." if len(miss_c) > 20 else ""))
        if miss_m:
            print("    members:", ", ".join(miss_m[:20]) + (" ..." if len(miss_m) > 20 else ""))
    print(f"\n  New classes: {', '.join(new_classes)}")
    print("\nRestart Claude Code to reload the MCP server with the new data.")


if __name__ == "__main__":
    main()
