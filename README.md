# Autodesk Fusion API - Claude Code MCP Server

A local MCP (Model Context Protocol) server that gives Claude Code deep knowledge of the Autodesk Fusion API, ECAD/ULP electronics docs, and your company's component library. Instead of guessing API method names or signatures, Claude looks them up in real time across 19,800+ indexed entries (Fusion API synced to the May 2026 release).

## What It Does

When you ask Claude to write a Fusion script, it queries the MCP server to:

- **Look up exact API signatures** — methods, properties, events, return types, parameters for all 1,526 Fusion API classes
- **Find code samples** — 217 working examples in both Python and C++ covering CAM, sketches, features, UI commands, and more
- **Reference ECAD/ULP docs** — 49 ULP object types, language reference, and editor commands for schematic and PCB automation
- **Search your parts library** — finds real components from your indexed Fusion Electronics library by name, footprint, or description

## Architecture

```
Claude Code  <--stdio-->  MCP Server (Node.js/TypeScript)
                              |
                              +-- MiniSearch (full-text search, 19,800+ items)
                              +-- parsed-docs/ (structured JSON from API docs)
                              +-- library data (indexed component library)
```

The MCP server exposes 7 tools:

| Tool | Purpose |
|------|---------|
| `search_api` | Full-text search across all docs and library parts |
| `get_class` | Complete class reference (methods, properties, events) |
| `get_member` | Detailed method/property syntax for Python and C++ |
| `list_namespace` | Browse all classes in a namespace |
| `get_sample` | Full code samples in Python and C++ |
| `get_guide` | Conceptual guides (CAM intro, attributes, custom features, etc.) |
| `get_ecad` | ULP object types, language reference, editor commands |

## Data Sources

### Fusion API (18,100+ items)
Originally extracted from the official `FusionAPI.chm` help file; incrementally synced to the May 2026 release via `scripts/scrape_api_update.py`. Covers six namespaces:

- `adsk::core` (337 classes) — Application, UI, geometry, events, commands
- `adsk::fusion` (838 classes) — Design, sketches, features, BRep, components
- `adsk::cam` (209 classes) — CAM setups, operations, toolpaths, post-processing
- `adsk::electron` (104 classes) — Read-only Electronics Python API (schematics, boards, libraries) — new in May 2026
- `adsk::drawing` (6 classes) — Drawing views and sheets
- `adsk::volume` (30 classes) — Volume/lattice operations

### ECAD / ULP (521 items)
Scraped from [Autodesk Fusion ECAD Help](https://help.autodesk.com/cloudhelp/ENU/Fusion-ECAD/). Covers:

- 49 ULP object types (UL_SCHEMATIC, UL_BOARD, UL_NET, UL_PIN, UL_PART, etc.)
- ULP language reference (builtins, statements, dialogs, data types, syntax)
- Editor command reference (schematic, layout, routing)

### REC Standard Library (1,232 items)
Exported from our Fusion Team Library using a custom ULP script. Indexed components are searchable by name, description, footprint, or symbol.

- 454 device sets (ESP32-WROVER, capacitors, resistors, LEDs, connectors, headers, etc.)
- 175 footprints (0402, 0603, 0805, SOT-23, QFN, through-hole, etc.)
- 112 symbols

Claude uses these when writing electronics scripts so it references real parts from your library instead of inventing component names.

## Setup

### Prerequisites
- Node.js 18+
- Claude Code CLI

### Install and Build
```bash
cd mcp-server
npm install
npm run build
```

### Configure Claude Code
The `.mcp.json` in the project root registers the server automatically when you open Claude Code in this directory. If you need to set it up manually, add to your Claude Code MCP config:

```json
{
  "mcpServers": {
    "fusion-api-docs": {
      "command": "node",
      "args": ["/path/to/autodesk-coder/mcp-server/dist/index.js"]
    }
  }
}
```

Restart Claude Code after any changes.

## Updating the Library

When your Fusion Electronics library changes, re-export and re-index:

1. **Export** — Open the library in Fusion Electronics and run `ulp-scripts/export-library.ulp`. Save the JSON output to `library-data/`.

2. **Index** — Run the indexer to merge library parts into the search corpus:
   ```bash
   python scripts/index_library.py library-data/rec-library.json
   ```

3. **Rebuild** — Rebuild the MCP server and restart Claude Code:
   ```bash
   cd mcp-server && npm run build
   ```

## Updating API Docs

To refresh the Fusion API docs from a new CHM file:

```bash
# Extract the CHM (macOS — install extract_chmLib via Homebrew)
mkdir -p raw-docs/FusionAPI
extract_chmLib FusionAPI.chm raw-docs/FusionAPI

# Parse into structured JSON
python scripts/parse_docs.py

# Scrape latest ECAD/ULP docs
python scripts/scrape_ecad.py
python scripts/index_ecad.py

# Rebuild
cd mcp-server && npm run build
```

## Usage Examples

Once the MCP server is running, Claude will automatically use it when you ask for Fusion scripting help:

- *"Write a Python script to create a 2D adaptive toolpath for my WorkBee CNC"* — Claude looks up CAM.generateToolpath, Setup, OperationInput, and post-processing APIs
- *"Write a ULP to export a BOM from my schematic"* — Claude fetches UL_SCHEMATIC, UL_PART, and UL_DEVICE object docs
- *"Add an ESP32-WROVER to my schematic script"* — Claude searches the REC Library and finds the exact part name, package, and available variants
- *"Create a sketch with fillets on a new component"* — Claude looks up SketchCircle, SketchLine, FilletFeature with exact Python/C++ syntax
