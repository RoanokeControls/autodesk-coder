# Changelog & Handoff

Maintenance log for the Fusion API MCP server. Newest first. See `CLAUDE.md` for
how the pipeline works and `README.md` for an overview.

## Current state (handoff)

- **Fusion API docs:** synced to the **May 2026** release.
- **Index size:** 1,526 classes, 19,891 search-corpus items, 7 namespaces
  (`adsk::core`, `adsk::fusion`, `adsk::cam`, `adsk::electron`, `adsk::drawing`,
  `adsk::volume`, plus a small uncategorized bucket).
- **Dependencies:** `mcp-server` reports **0 npm-audit vulnerabilities**;
  `@modelcontextprotocol/sdk` on `^1.29.0`.
- **Update checker:** `scripts/update-check-state.json` pinned to **May 2026**,
  so the SessionStart hook will now warn when the *next* release ships.

### On pickup — do this first
1. **Restart Claude Code** so the MCP server reloads the new `parsed-docs/`
   (the server reads JSON at startup; data-only changes need a restart, not a rebuild).
2. **Fresh clone?** The checker state is gitignored — run
   `python3 scripts/check_api_updates.py --init` once so the hook has a baseline.

### Open follow-ups
- **Electronics member detail (low priority):** every `adsk::electron` class has
  full method/property *tables* (via `get_class`), but per-member `get_member`
  syntax was only fetched for the ~35 members Autodesk flagged as new. To deep-fetch
  the rest, extend `scripts/scrape_api_update.py` to also enumerate each electronics
  class's members. Until then, fall back to `get_class` for those descriptions.
- **GitHub Dependabot tab** clears automatically once it re-scans the pushed
  lockfile (push `0158185`).

---

## 2026-06-11 — May 2026 API sync + dependency patch

**Synced Fusion API docs January 2026 → May 2026** without re-extracting the
offline-help CHM, using a new incremental updater.

- Added `scripts/scrape_api_update.py`: fetches only the new/changed pages listed
  on a release's "What's New" page and merges them into `parsed-docs/`, preserving
  existing API/ECAD/library data and original per-member detail pages.
- **+117 classes, +256 methods, +942 properties** (corpus 18,576 → 19,891).
- New **`adsk::electron`** namespace (104 classes): initial **read-only Electronics
  Python API** — `EcadDesign`, `Schematic`, `Board`, `Net`, `Pin`, `Symbol`,
  `Package`, `Device`/`DeviceSet`, `Gate`, `Signal`, `Via`, `Pad`/`Smd`, etc.
  First time schematic/board/library data is reachable from Python instead of ULP.
- Also landed: sheet-metal (`BRepBody.convertToSheetMetal`), User Coordinate
  Systems, volumetric model features, mesh ray intersection
  (`Component.findMeshUsingRay`), `STLExportOptions.unitType`.
- Initialized `scripts/update-check-state.json` (previously never created, so the
  SessionStart update hook had been silently no-op'ing) and pinned it to May 2026.
- Updated `CLAUDE.md` and `README.md` (version, namespace table, Electronics API
  guidance, incremental-update workflow).

**Patched all Dependabot vulnerabilities in `mcp-server`.** All 23 alerts
(3 high / 19 moderate / 1 low; 7 deduped locally) were transitive deps of
`@modelcontextprotocol/sdk`, all in its unused HTTP/SSE transport stack — this
server uses stdio, so real exploitability was nil. Bumped the SDK to `^1.29.0`
and ran `npm audit fix`: hono 4.11.9→4.12.25, @hono/node-server 1.19.9→1.19.14,
path-to-regexp 8.3.0→8.4.2, fast-uri 3.1.0→3.1.2, qs 6.15.0→6.15.2,
ip-address 10.0.1→10.2.0. Rebuilt and smoke-tested (MCP handshake OK, all 7
tools list, 19,891-item corpus loads).

Commits: `2a36ba2`, `429cf05`, `0158185`.
