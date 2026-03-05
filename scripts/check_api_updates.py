#!/usr/bin/env python3
"""
Fusion API Documentation Update Checker

Checks Autodesk help URLs for changes to detect when the Fusion API docs
have been updated upstream. Uses HTTP HEAD requests for speed.

Modes:
  --init   Snapshot current upstream state (run once after scraping docs)
  --hook   Silent JSON output for Claude Code SessionStart hook
  --deep   Full fetch with version string extraction
  (default) Verbose manual check with human-readable output
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "update-check-state.json")

# URLs to monitor — a change to any of these signals an API docs update
URLS = {
    "whats_new": {
        "url": "https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WhatsNew.htm",
        "label": "What's New (API release notes)",
    },
    "application_class": {
        "url": "https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/Application.htm",
        "label": "Application class reference",
    },
    "ecad_ulp_objects": {
        "url": "https://help.autodesk.com/cloudhelp/ENU/Fusion-ECAD/files/ECD-ULP-OBJECT-TYPES.htm",
        "label": "ECAD/ULP object types",
    },
}

REQUEST_TIMEOUT = 10  # seconds per request


def fetch_headers(url):
    """Send HEAD request, return dict with last-modified and etag."""
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "FusionAPIUpdateChecker/1.0")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return {
                "status": resp.status,
                "last_modified": resp.headers.get("Last-Modified"),
                "etag": resp.headers.get("ETag"),
                "date": resp.headers.get("Date"),
            }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return {"error": str(e)}


def fetch_full(url):
    """GET request, return body text + headers."""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "FusionAPIUpdateChecker/1.0")
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "status": resp.status,
                "last_modified": resp.headers.get("Last-Modified"),
                "etag": resp.headers.get("ETag"),
                "body": body,
            }
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        return {"error": str(e)}


def extract_version_from_whatsnew(html):
    """Try to extract the latest release identifier from What's New page."""
    import re

    # Autodesk uses "What's New For the <Month> <Year> Release" format
    patterns = [
        r"What.s New\s+(?:For\s+)?(?:the\s+)?(\w+\s+\d{4})\s+Release",
        r"Help created:\s*\w+,\s*(\w+\s+\d+,\s*\d{4})",
        r"Version\s+([\d.]+\.\d+)",
        r"Fusion\s+(?:360\s+)?(?:API\s+)?(?:Version\s+)?(2\.\d+\.\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def load_state():
    """Load saved state from disk."""
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state):
    """Write state to disk."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def build_state_snapshot():
    """Fetch headers for all URLs and build a state dict."""
    state = {"checked_at": datetime.now(timezone.utc).isoformat(), "urls": {}}
    for key, info in URLS.items():
        headers = fetch_headers(info["url"])
        state["urls"][key] = {
            "url": info["url"],
            "label": info["label"],
            "last_modified": headers.get("last_modified"),
            "etag": headers.get("etag"),
        }
        if "error" in headers:
            state["urls"][key]["error"] = headers["error"]
    return state


def check_for_changes(saved_state):
    """Compare current headers against saved state. Returns list of changes."""
    changes = []
    for key, info in URLS.items():
        headers = fetch_headers(info["url"])
        if "error" in headers:
            changes.append({
                "key": key,
                "label": info["label"],
                "type": "error",
                "detail": headers["error"],
            })
            continue

        saved = saved_state.get("urls", {}).get(key, {})

        # Check Last-Modified change
        if headers.get("last_modified") and saved.get("last_modified"):
            if headers["last_modified"] != saved["last_modified"]:
                changes.append({
                    "key": key,
                    "label": info["label"],
                    "type": "last_modified",
                    "old": saved["last_modified"],
                    "new": headers["last_modified"],
                })
                continue

        # Check ETag change
        if headers.get("etag") and saved.get("etag"):
            if headers["etag"] != saved["etag"]:
                changes.append({
                    "key": key,
                    "label": info["label"],
                    "type": "etag",
                    "old": saved["etag"],
                    "new": headers["etag"],
                })
                continue

    return changes


def mode_init():
    """Snapshot current upstream state."""
    print("Initializing update check state...")
    state = build_state_snapshot()

    # Try to get version from What's New
    wn = fetch_full(URLS["whats_new"]["url"])
    if "body" in wn:
        version = extract_version_from_whatsnew(wn["body"])
        if version:
            state["api_version"] = version
            print(f"  Detected API version: {version}")

    save_state(state)
    print(f"  State saved to: {STATE_FILE}")
    print(f"  Checked at: {state['checked_at']}")
    for key, data in state["urls"].items():
        status = "error" if "error" in data else "ok"
        lm = data.get("last_modified", "n/a")
        print(f"  [{status}] {data['label']}: Last-Modified={lm}")
    print("\nDone. The SessionStart hook will now detect future changes.")


def mode_hook():
    """Silent check for Claude Code hook — only output JSON if changes found."""
    saved = load_state()
    if saved is None:
        # No state file yet — nothing to compare against
        sys.exit(0)

    changes = check_for_changes(saved)
    if not changes:
        sys.exit(0)

    # Filter out errors — only report actual content changes
    real_changes = [c for c in changes if c["type"] != "error"]
    if not real_changes:
        sys.exit(0)

    # Build notification message
    parts = ["**Fusion API docs may have been updated upstream.**\n"]
    parts.append("Detected changes since last check:")
    for c in real_changes:
        parts.append(f"- {c['label']}: {c['type']} changed ({c.get('old', '?')} → {c.get('new', '?')})")
    parts.append("")
    parts.append("Run `python3 scripts/check_api_updates.py --deep` for details.")
    parts.append("If docs are stale, re-run the scraping/parsing pipeline (see CLAUDE.md).")

    # Output as hook JSON
    hook_output = {"additionalContext": "\n".join(parts)}
    print(json.dumps(hook_output))


def mode_deep():
    """Full fetch with version extraction."""
    saved = load_state()
    print("Deep check — fetching full pages...\n")

    wn = fetch_full(URLS["whats_new"]["url"])
    if "body" in wn:
        version = extract_version_from_whatsnew(wn["body"])
        saved_version = saved.get("api_version") if saved else None
        print(f"  Current upstream API version: {version or 'unknown'}")
        print(f"  Last saved API version:       {saved_version or 'unknown'}")
        if version and saved_version and version != saved_version:
            print(f"\n  *** VERSION CHANGED: {saved_version} → {version} ***")
            print("  You should re-scrape the docs and rebuild the search index.")
        elif version and saved_version and version == saved_version:
            print("\n  Version unchanged.")
    else:
        print(f"  Error fetching What's New: {wn.get('error', 'unknown')}")

    # Also show header comparison
    if saved:
        print("\nHeader comparison:")
        changes = check_for_changes(saved)
        if changes:
            for c in changes:
                if c["type"] == "error":
                    print(f"  [{c['key']}] Error: {c['detail']}")
                else:
                    print(f"  [{c['key']}] {c['label']}: {c['type']} changed")
                    print(f"    Old: {c.get('old', '?')}")
                    print(f"    New: {c.get('new', '?')}")
        else:
            print("  No header changes detected.")

    # Offer to update state
    print("\nTo update saved state, run: python3 scripts/check_api_updates.py --init")


def mode_default():
    """Verbose manual check."""
    saved = load_state()
    if saved is None:
        print("No saved state found. Run with --init first to snapshot current state.")
        print(f"  python3 {os.path.basename(__file__)} --init")
        sys.exit(1)

    print(f"Last check: {saved.get('checked_at', 'unknown')}")
    if saved.get("api_version"):
        print(f"Saved API version: {saved['api_version']}")
    print()

    changes = check_for_changes(saved)
    if not changes:
        print("All up to date — no changes detected in upstream docs.")
        sys.exit(0)

    real_changes = [c for c in changes if c["type"] != "error"]
    errors = [c for c in changes if c["type"] == "error"]

    if real_changes:
        print("Changes detected:")
        for c in real_changes:
            print(f"  - {c['label']}: {c['type']} changed")
            print(f"    Old: {c.get('old', '?')}")
            print(f"    New: {c.get('new', '?')}")
        print()
        print("Run with --deep for version details, or --init to update saved state.")

    if errors:
        print("\nErrors (could not check):")
        for c in errors:
            print(f"  - {c['label']}: {c['detail']}")


def main():
    parser = argparse.ArgumentParser(
        description="Check for Fusion API documentation updates"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--init",
        action="store_true",
        help="Snapshot current upstream state",
    )
    group.add_argument(
        "--hook",
        action="store_true",
        help="Silent check for Claude Code hook (JSON output)",
    )
    group.add_argument(
        "--deep",
        action="store_true",
        help="Full fetch with version extraction",
    )
    args = parser.parse_args()

    if args.init:
        mode_init()
    elif args.hook:
        mode_hook()
    elif args.deep:
        mode_deep()
    else:
        mode_default()


if __name__ == "__main__":
    main()
