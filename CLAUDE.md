# Autodesk Fusion API Coding Assistant

## Project Purpose
This project provides Claude with deep knowledge of the Autodesk Fusion API via a local MCP server. Use the MCP tools to look up API classes, methods, properties, code samples, and guides before writing any Fusion scripts.

## User Context
- **User**: Steve Hall
- **Primary workflows**: PCB/schematic design (Electronics), CNC machining (CAM), 3D parametric modeling
- **CNC hardware**: WorkBee CNC (needs appropriate post-processor considerations)
- **Languages**: Both Python and C++ for Fusion API scripting; ULP for electronics automation
- **Fusion version**: Latest (January 2026 API)

## MCP Tools Available
When working on Fusion API tasks, always use these tools from the `fusion-api-docs` MCP server:

1. **search_api** - Full-text search across 17,300+ entries (Fusion API + ECAD/ULP). Start here when exploring.
   - `query`: keywords or description of what you need
   - `type_filter`: "class", "method", "property", "event", "sample", "guide", "ecad_object", "ecad_member", "ecad_command", "ecad_guide", or "all"
   - `limit`: max results (default 20)

2. **get_class** - Get complete class reference with methods, properties, events.
   - `class_name`: e.g. "CAM", "Setup", "SketchCircle"
   - `include_details`: true for full syntax/params (verbose)

3. **get_member** - Get detailed info for a specific method/property/event.
   - `class_name` + `member_name`: e.g. "CAM" + "generateToolpath"

4. **list_namespace** - Browse all classes in a namespace.
   - Available: `adsk::core`, `adsk::fusion`, `adsk::cam`, `adsk::drawing`, `adsk::volume`

5. **get_sample** - Get full code samples (Python + C++) for a topic.

6. **get_guide** - Get user manual topics covering concepts.

7. **get_ecad** - Get ECAD/ULP electronics documentation.
   - ULP object types: "UL_SCHEMATIC", "UL_BOARD", "UL_NET", "UL_PIN", "UL_PART", "UL_SIGNAL", "UL_PAD", "UL_VIA", "UL_WIRE", etc. (49 object types)
   - ULP language refs: "ULP Builtin Functions", "ULP Statements", "ULP Dialogs", "ULP Data Types", "ULP Syntax"
   - ECAD commands: "Schematic Editor Commands", "Layout Editor Commands", "Routing Commands"

## Workflow Guidelines
- **Always look up the API** before writing Fusion scripts. Don't guess method names or signatures.
- **Check for RETIRED methods** — the API marks deprecated methods with **RETIRED**. Use the replacement.
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

## API Namespaces Quick Reference
- `adsk::core` (337 classes) — Application, UI, geometry primitives, events, commands
- `adsk::fusion` (829 classes) — Design, sketches, features, BRep, components, joints
- `adsk::cam` (205 classes) — CAM, setups, operations, toolpaths, tools, post-processing
- `adsk::drawing` (6 classes) — Drawing views and sheets
- `adsk::volume` (30 classes) — Volume/lattice operations
- `ECAD/ULP` (49 object types) — Schematics, boards, nets, pins, pads, signals, routing
