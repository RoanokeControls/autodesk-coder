# Autodesk Fusion API Coding Assistant

## Project Purpose
This project provides Claude with deep knowledge of the Autodesk Fusion API via a local MCP server. Use the MCP tools to look up API classes, methods, properties, code samples, and guides before writing any Fusion scripts.

## User Context
- **User**: Steve Hall (WhiteHallEngineering)
- **Primary workflows**: PCB/schematic design (Electronics), CNC machining (CAM), 3D parametric modeling
- **CNC hardware**: WorkBee CNC (needs appropriate post-processor considerations)
- **Languages**: Both Python and C++ for Fusion API scripting; ULP for electronics automation
- **Fusion version**: Latest (January 2026 API)
- **Company library**: REC Standard Library (454 parts indexed — ESP32, capacitors, LEDs, connectors, headers, etc.)

## MCP Tools Available
When working on Fusion API tasks, always use these tools from the `fusion-api-docs` MCP server:

1. **search_api** - Full-text search across 18,500+ entries (Fusion API + ECAD/ULP + REC Library). Start here when exploring.
   - `query`: keywords or description of what you need
   - `type_filter`: "all", "class", "method", "property", "event", "sample", "guide", "ecad_object", "ecad_member", "ecad_command", "ecad_guide", "library_part", "library_variant", "library_footprint", "library_symbol"
   - `limit`: max results (default 20)

2. **get_class** - Get complete class reference with methods, properties, events.
   - `class_name`: e.g. "CAM", "Setup", "SketchCircle"
   - `include_details`: true for full syntax/params (verbose)

3. **get_member** - Get detailed info for a specific method/property/event.
   - `class_name` + `member_name`: e.g. "CAM" + "generateToolpath"

4. **list_namespace** - Browse all classes in a namespace.
   - Available: `adsk::core`, `adsk::fusion`, `adsk::cam`, `adsk::drawing`, `adsk::volume`

5. **get_sample** - Get full code samples (Python + C++) for a topic.
   - Use `search_api` with `type_filter: "sample"` first to find the sample ID.

6. **get_guide** - Get user manual topics covering concepts.
   - Use `search_api` with `type_filter: "guide"` first to find the guide ID.

7. **get_ecad** - Get ECAD/ULP electronics documentation.
   - ULP object types: "UL_SCHEMATIC", "UL_BOARD", "UL_NET", "UL_PIN", "UL_PART", "UL_SIGNAL", "UL_PAD", "UL_VIA", "UL_WIRE", etc. (49 object types)
   - ULP language refs: "ULP Builtin Functions", "ULP Statements", "ULP Dialogs", "ULP Data Types", "ULP Syntax"
   - ECAD commands: "Schematic Editor Commands", "Layout Editor Commands", "Routing Commands"

## Workflow Guidelines
- **Always look up the API** before writing Fusion scripts. Don't guess method names or signatures.
- **Check for RETIRED methods** — the API marks deprecated methods with **RETIRED**. Use the replacement.
- **Search for library parts** when writing electronics scripts — use `type_filter: "library_part"` to find real components from the REC Standard Library instead of inventing part names.
- **Python scripts** follow the pattern: `def run(context)` entry point, `adsk.core.Application.get()` for the app.
- **C++ add-ins** use `extern "C" XI_EXPORT bool run(const char* context)` entry point.
- **CAM operations** use templates and parameters — search for "CAMTemplate" and "CAMParameters" for the workflow.
- **WorkBee CNC**: When generating toolpaths or post-processing, consider appropriate feed rates and post-processor settings for a hobby CNC.

## Electronics / ECAD Guidelines
- Fusion Electronics uses **ULP (User Language Programming)** for schematic and PCB automation — a C-like language inherited from EAGLE.
- ULP scripts are NOT Python — they use C-like syntax with special object types (UL_SCHEMATIC, UL_NET, UL_PIN, etc.).
- Run ULPs from **Schematic Automate** or **PCB Automation** toolbars in Fusion.
- Key ULP patterns:
  - `schematic(SCH) { ... }` — access schematic context
  - `board(BRD) { ... }` — access board/PCB context
  - `SCH.sheets(SH) { SH.nets(N) { ... } }` — iterate sheets/nets
  - `output(filename) { ... }` — write output files
- Use `get_ecad("UL_SCHEMATIC")` to see available data members and loop members for any object type.
- **ULP gotchas**:
  - `UL_PIN` properties `direction`, `function`, `length`, `visible` are `int`, not `string` — use `%d` format.
  - `D.footprint` can be null if a device has no footprint — always check `if (D.footprint)` before accessing `.name`.
  - ULP has no Python-style string formatting — use `sprintf()` and C-style `printf()`.

## Project Structure
```
autodesk-coder/
  CLAUDE.md              — This file (project instructions for Claude)
  .mcp.json              — MCP server registration for Claude Code
  mcp-server/
    src/index.ts         — MCP server source (TypeScript, ESM)
    package.json         — Dependencies: @modelcontextprotocol/sdk, minisearch
    tsconfig.json        — TypeScript config (NodeNext module resolution)
    dist/                — Compiled JS output (run `npm run build` to regenerate)
  parsed-docs/
    search_corpus.json   — 18,500+ item search index (Fusion API + ECAD + library)
    index.json           — Class/namespace/sample/guide/ecad metadata
    classes/             — 1,409 class JSON files
    samples/             — 217 code sample JSON files
    guides/              — 43 guide JSON files
    ecad/                — 72 ECAD/ULP doc JSON files
    library/             — REC Standard Library part JSON files
  scripts/
    parse_docs.py        — Parse extracted CHM HTML into structured JSON
    scrape_ecad.py       — Scrape ECAD/ULP docs from help.autodesk.com
    index_ecad.py        — Index ECAD docs into search corpus
    index_library.py     — Index exported library JSON into search corpus
  ulp-scripts/
    export-library.ulp   — ULP script to export a Fusion Electronics library to JSON
  library-data/
    rec-library.json     — Exported REC Standard Library (454 parts, 175 footprints, 112 symbols)
  raw-docs/              — (gitignored) Extracted CHM HTML files (175MB)
```

## Rebuilding the MCP Server
If the source changes:
```bash
cd mcp-server && npm run build
```
Restart Claude Code to pick up the rebuilt server.

## Re-indexing Data
To regenerate the search corpus after updating source data:
```bash
# Parse CHM docs (requires raw-docs/ from CHM extraction)
python scripts/parse_docs.py

# Scrape latest ECAD docs from Autodesk
python scripts/scrape_ecad.py
python scripts/index_ecad.py

# Re-index a library export
python scripts/index_library.py library-data/rec-library.json
```

## API Namespaces Quick Reference
- `adsk::core` (337 classes) — Application, UI, geometry primitives, events, commands
- `adsk::fusion` (829 classes) — Design, sketches, features, BRep, components, joints
- `adsk::cam` (205 classes) — CAM, setups, operations, toolpaths, tools, post-processing
- `adsk::drawing` (6 classes) — Drawing views and sheets
- `adsk::volume` (30 classes) — Volume/lattice operations
- `ECAD/ULP` (49 object types) — Schematics, boards, nets, pins, pads, signals, routing
- `REC Library` (454 parts) — Company standard components (ESP32, passives, connectors, etc.)
