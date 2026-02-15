import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { readFileSync, readdirSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import MiniSearch from "minisearch";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PARSED_DIR = join(__dirname, "..", "..", "parsed-docs");

// ── Load data ──────────────────────────────────────────────────────────────

interface SearchItem {
  id: string;
  type: string;
  name: string;
  class_name?: string;
  namespace?: string;
  description: string;
  parent_class?: string;
}

interface IndexData {
  classes: Record<
    string,
    {
      namespace: string;
      description: string;
      parent_class: string;
      method_count: number;
      property_count: number;
      event_count: number;
    }
  >;
  namespaces: Record<string, string[]>;
  sample_names: string[];
  guide_names: string[];
  ecad?: {
    object_types: string[];
    language_refs: string[];
    command_refs: string[];
    general: string[];
  };
}

function loadJSON<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8"));
}

console.error("Loading Fusion API data...");

const index = loadJSON<IndexData>(join(PARSED_DIR, "index.json"));
const searchCorpus = loadJSON<SearchItem[]>(
  join(PARSED_DIR, "search_corpus.json")
);

// Build full-text search index
const miniSearch = new MiniSearch<SearchItem>({
  fields: ["name", "description", "class_name", "namespace"],
  storeFields: ["name", "type", "class_name", "namespace", "description"],
  searchOptions: {
    boost: { name: 3, class_name: 2, description: 1 },
    fuzzy: 0.2,
    prefix: true,
  },
});

miniSearch.addAll(searchCorpus);
console.error(
  `Indexed ${searchCorpus.length} items across ${Object.keys(index.namespaces).length} namespaces`
);

// ── Helper functions ───────────────────────────────────────────────────────

function loadClass(name: string): Record<string, unknown> | null {
  const path = join(PARSED_DIR, "classes", `${name}.json`);
  if (!existsSync(path)) return null;
  return loadJSON(path);
}

function loadSample(name: string): Record<string, unknown> | null {
  const path = join(PARSED_DIR, "samples", `${name}.json`);
  if (!existsSync(path)) return null;
  return loadJSON(path);
}

function loadGuide(name: string): Record<string, unknown> | null {
  const path = join(PARSED_DIR, "guides", `${name}.json`);
  if (!existsSync(path)) return null;
  return loadJSON(path);
}

function loadEcad(name: string): Record<string, unknown> | null {
  const path = join(PARSED_DIR, "ecad", `${name}.json`);
  if (!existsSync(path)) return null;
  return loadJSON(path);
}

function formatClassSummary(cls: Record<string, unknown>): string {
  let out = `# ${cls.id as string}\n`;
  if (cls.namespace) out += `Namespace: ${cls.namespace}\n`;
  if (cls.parent_class) out += `Inherits: ${cls.parent_class}\n`;
  if (cls.header_file) out += `Header: ${cls.header_file}\n`;
  out += `\n${cls.description}\n`;

  const methods = cls.methods as Array<{ name: string; description: string }>;
  if (methods?.length) {
    out += `\n## Methods (${methods.length})\n`;
    for (const m of methods) {
      out += `- **${m.name}**: ${m.description}\n`;
    }
  }

  const props = cls.properties as Array<{ name: string; description: string }>;
  if (props?.length) {
    out += `\n## Properties (${props.length})\n`;
    for (const p of props) {
      out += `- **${p.name}**: ${p.description}\n`;
    }
  }

  const events = cls.events as Array<{ name: string; description: string }>;
  if (events?.length) {
    out += `\n## Events (${events.length})\n`;
    for (const e of events) {
      out += `- **${e.name}**: ${e.description}\n`;
    }
  }

  return out;
}

function formatMemberDetail(
  className: string,
  memberName: string,
  detail: Record<string, unknown>
): string {
  let out = `# ${className}.${memberName}\n`;
  out += `Type: ${detail.type}\n`;
  if (detail.description) out += `\n${detail.description}\n`;

  const syntax = detail.syntax as
    | { python?: string; cpp?: string }
    | undefined;
  if (syntax) {
    if (syntax.python) {
      out += `\n## Python Syntax\n\`\`\`python\n${syntax.python}\n\`\`\`\n`;
    }
    if (syntax.cpp) {
      out += `\n## C++ Syntax\n\`\`\`cpp\n${syntax.cpp}\n\`\`\`\n`;
    }
  }

  const params = detail.parameters as Array<{
    name: string;
    type: string;
    description: string;
  }>;
  if (params?.length) {
    out += `\n## Parameters\n`;
    for (const p of params) {
      out += `- **${p.name}** (${p.type}): ${p.description}\n`;
    }
  }

  if (detail.return_type) {
    out += `\n## Returns\n${detail.return_type}: ${detail.return_description || ""}\n`;
  }
  if (detail.property_value) {
    out += `\n## Value\n${detail.property_value}\n`;
  }

  return out;
}

function formatSample(sample: Record<string, unknown>): string {
  let out = `# ${sample.title || sample.id}\n`;
  if (sample.description) out += `\n${sample.description}\n`;

  const codeSamples = sample.code_samples as
    | Record<string, string>
    | undefined;
  if (codeSamples) {
    for (const [lang, code] of Object.entries(codeSamples)) {
      const langName = lang === "cpp" ? "C++" : "Python";
      const ext = lang === "cpp" ? "cpp" : "python";
      out += `\n## ${langName}\n\`\`\`${ext}\n${code}\n\`\`\`\n`;
    }
  }

  return out;
}

// ── MCP Server ─────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "fusion-api-docs",
  version: "1.0.0",
});

// Tool: search_api - Full-text search across all API docs
server.tool(
  "search_api",
  "Search the Fusion API documentation. Returns matching classes, methods, properties, events, samples, and guides. Also searches ECAD/ULP electronics documentation (object types, commands, builtins). Use this to find relevant API elements by keyword or description.",
  {
    query: z
      .string()
      .describe(
        "Search query - can be keywords, class names, or descriptions of functionality"
      ),
    type_filter: z
      .enum(["all", "class", "method", "property", "event", "sample", "guide", "ecad_object", "ecad_member", "ecad_command", "ecad_guide", "library_part", "library_variant", "library_footprint", "library_symbol"])
      .optional()
      .describe("Filter results by type"),
    limit: z
      .number()
      .optional()
      .default(20)
      .describe("Maximum number of results (default 20)"),
  },
  async ({ query, type_filter, limit }) => {
    let results = miniSearch.search(query, {
      boost: { name: 3, class_name: 2, description: 1 },
      fuzzy: 0.2,
      prefix: true,
    });

    if (type_filter && type_filter !== "all") {
      results = results.filter((r) => r.type === type_filter);
    }

    results = results.slice(0, limit || 20);

    if (results.length === 0) {
      return {
        content: [
          {
            type: "text" as const,
            text: `No results found for "${query}". Try broader search terms or different keywords.`,
          },
        ],
      };
    }

    let output = `## Search results for "${query}" (${results.length} results)\n\n`;
    for (const r of results) {
      const score = r.score.toFixed(1);
      if (r.type === "class") {
        output += `- **[class] ${r.name}** (${r.namespace || "?"}) — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "method" || r.type === "property" || r.type === "event") {
        output += `- **[${r.type}] ${r.class_name}.${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "sample") {
        output += `- **[sample] ${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "guide") {
        output += `- **[guide] ${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "ecad_object") {
        output += `- **[ECAD object] ${r.name}** (${r.namespace || "ECAD/ULP"}) — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "ecad_member" || r.type === "ecad_loop") {
        output += `- **[ECAD ${r.type === "ecad_loop" ? "loop" : "member"}] ${r.class_name}.${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "ecad_command") {
        output += `- **[ECAD cmd] ${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "ecad_guide") {
        output += `- **[ECAD ref] ${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      } else if (r.type === "library_part") {
        output += `- **[part] ${r.name}** (${r.class_name || "library"}) — ${(r.description || "").slice(0, 150)}\n`;
      } else if (r.type === "library_variant" || r.type === "library_footprint" || r.type === "library_symbol") {
        const tag = r.type.replace("library_", "");
        output += `- **[${tag}] ${r.name}** (${r.class_name || "library"}) — ${(r.description || "").slice(0, 150)}\n`;
      } else {
        output += `- **[${r.type}] ${r.name}** — ${(r.description || "").slice(0, 120)}\n`;
      }
    }

    output += `\nUse get_class, get_member, get_sample, or get_ecad for full details.`;

    return { content: [{ type: "text" as const, text: output }] };
  }
);

// Tool: get_class - Get full class reference
server.tool(
  "get_class",
  "Get the complete reference for a Fusion API class, including all methods, properties, events, and their descriptions. Use this after search_api identifies a relevant class.",
  {
    class_name: z
      .string()
      .describe('The class name (e.g. "CAM", "Setup", "SketchCircle")'),
    include_details: z
      .boolean()
      .optional()
      .default(false)
      .describe(
        "Include full method/property details with syntax and parameters (verbose)"
      ),
  },
  async ({ class_name, include_details }) => {
    const cls = loadClass(class_name);
    if (!cls) {
      // Try case-insensitive search
      const allClasses = Object.keys(index.classes);
      const match = allClasses.find(
        (c) => c.toLowerCase() === class_name.toLowerCase()
      );
      if (match) {
        const matched = loadClass(match);
        if (matched)
          return {
            content: [
              { type: "text" as const, text: formatClassSummary(matched) },
            ],
          };
      }
      return {
        content: [
          {
            type: "text" as const,
            text: `Class "${class_name}" not found. Use search_api to find the correct name.`,
          },
        ],
      };
    }

    let output = formatClassSummary(cls);

    if (include_details) {
      const details = [
        "method_details",
        "property_details",
        "event_details",
      ] as const;
      for (const key of details) {
        const section = cls[key] as
          | Record<string, Record<string, unknown>>
          | undefined;
        if (section) {
          for (const [name, detail] of Object.entries(section)) {
            output +=
              "\n---\n" +
              formatMemberDetail(class_name, name, detail) +
              "\n";
          }
        }
      }
    }

    return { content: [{ type: "text" as const, text: output }] };
  }
);

// Tool: get_member - Get detailed info for a specific class member
server.tool(
  "get_member",
  "Get detailed information about a specific method, property, or event of a Fusion API class, including syntax for both Python and C++, parameters, and return types.",
  {
    class_name: z.string().describe("The class name"),
    member_name: z.string().describe("The method, property, or event name"),
  },
  async ({ class_name, member_name }) => {
    const cls = loadClass(class_name);
    if (!cls) {
      return {
        content: [
          { type: "text" as const, text: `Class "${class_name}" not found.` },
        ],
      };
    }

    for (const key of [
      "method_details",
      "property_details",
      "event_details",
      "member_details",
    ] as const) {
      const section = cls[key] as
        | Record<string, Record<string, unknown>>
        | undefined;
      if (section && member_name in section) {
        const detail = section[member_name];
        const output = formatMemberDetail(class_name, member_name, detail);
        return { content: [{ type: "text" as const, text: output }] };
      }
    }

    return {
      content: [
        {
          type: "text" as const,
          text: `Member "${member_name}" not found in class "${class_name}". Available members:\n${
            ((cls.methods as Array<{ name: string }>) || [])
              .map((m) => `  method: ${m.name}`)
              .join("\n") +
            "\n" +
            ((cls.properties as Array<{ name: string }>) || [])
              .map((p) => `  property: ${p.name}`)
              .join("\n")
          }`,
        },
      ],
    };
  }
);

// Tool: list_namespace - Browse classes in a namespace
server.tool(
  "list_namespace",
  "List all classes in a Fusion API namespace. Available namespaces: adsk::core, adsk::fusion, adsk::cam, adsk::drawing, adsk::volume.",
  {
    namespace: z
      .string()
      .describe(
        'Namespace to list (e.g. "adsk::cam", "adsk::fusion", "adsk::core")'
      ),
  },
  async ({ namespace }) => {
    const classes = index.namespaces[namespace];
    if (!classes) {
      const available = Object.keys(index.namespaces)
        .filter((n) => n)
        .join(", ");
      return {
        content: [
          {
            type: "text" as const,
            text: `Namespace "${namespace}" not found. Available: ${available}`,
          },
        ],
      };
    }

    let output = `## ${namespace} (${classes.length} classes)\n\n`;
    for (const cname of classes.sort()) {
      const info = index.classes[cname];
      output += `- **${cname}**: ${info?.description || ""}\n`;
    }

    return { content: [{ type: "text" as const, text: output }] };
  }
);

// Tool: get_sample - Get a code sample
server.tool(
  "get_sample",
  "Get a specific Fusion API code sample with full Python and C++ source code. Use search_api with type_filter='sample' to find available samples.",
  {
    sample_name: z
      .string()
      .describe("The sample name/ID (from search results)"),
  },
  async ({ sample_name }) => {
    let sample = loadSample(sample_name);
    if (!sample) {
      // Try fuzzy match
      const match = index.sample_names.find(
        (s) =>
          s.toLowerCase().includes(sample_name.toLowerCase()) ||
          sample_name.toLowerCase().includes(s.toLowerCase().replace("_sample", ""))
      );
      if (match) sample = loadSample(match);
    }

    if (!sample) {
      return {
        content: [
          {
            type: "text" as const,
            text: `Sample "${sample_name}" not found. Use search_api with type_filter="sample" to find samples.`,
          },
        ],
      };
    }

    return {
      content: [{ type: "text" as const, text: formatSample(sample) }],
    };
  }
);

// Tool: get_guide - Get a user manual / guide topic
server.tool(
  "get_guide",
  "Get a Fusion API user manual topic / guide page. These cover concepts like CAM introduction, attributes, custom features, etc.",
  {
    guide_name: z
      .string()
      .describe(
        'The guide name/ID (e.g. "CAMIntroduction_UM", "BasicConcepts_UM")'
      ),
  },
  async ({ guide_name }) => {
    let guide = loadGuide(guide_name);
    if (!guide) {
      const match = index.guide_names.find(
        (g) =>
          g.toLowerCase().includes(guide_name.toLowerCase()) ||
          guide_name.toLowerCase().includes(g.toLowerCase().replace("_um", ""))
      );
      if (match) guide = loadGuide(match);
    }

    if (!guide) {
      const available = index.guide_names.join(", ");
      return {
        content: [
          {
            type: "text" as const,
            text: `Guide "${guide_name}" not found. Available guides: ${available}`,
          },
        ],
      };
    }

    // Guides have a 'content' field with full markdown-like body
    if (guide.content) {
      return { content: [{ type: "text" as const, text: guide.content as string }] };
    }

    let output = `# ${guide.title || guide.id}\n\n${guide.description || ""}`;

    const codeSamples = guide.code_samples as
      | Record<string, string>
      | undefined;
    if (codeSamples) {
      for (const [lang, code] of Object.entries(codeSamples)) {
        output += `\n\n## ${lang}\n\`\`\`\n${code}\n\`\`\``;
      }
    }

    return { content: [{ type: "text" as const, text: output }] };
  }
);

// Tool: get_ecad - Get ECAD/ULP documentation
server.tool(
  "get_ecad",
  "Get Fusion ECAD/ULP electronics documentation. Can retrieve ULP object types (UL_SCHEMATIC, UL_NET, UL_PIN, etc.), ULP language reference (syntax, builtins, data types, dialogs), or ECAD command reference (schematic editor, layout editor, routing commands).",
  {
    name: z
      .string()
      .describe(
        'The page name - e.g. "UL_SCHEMATIC", "UL_NET", "UL_PIN", "ULP Builtin Functions", "Schematic Editor Commands"'
      ),
  },
  async ({ name }) => {
    // Try direct ID match (e.g. "ECD-ULP-SCHEMATIC")
    let doc = loadEcad(name);

    // Try mapping from friendly name to file ID
    if (!doc) {
      const ecadSection = index.ecad;
      if (ecadSection) {
        const allIds = [
          ...ecadSection.object_types,
          ...ecadSection.language_refs,
          ...ecadSection.command_refs,
          ...ecadSection.general,
        ];

        // Match by UL_ prefix (e.g. "UL_NET" -> "ECD-ULP-NET")
        if (name.startsWith("UL_")) {
          const suffix = name.replace("UL_", "");
          const match = allIds.find((id) => id === `ECD-ULP-${suffix}`);
          if (match) doc = loadEcad(match);
        }

        // Fuzzy match by title and ID (bidirectional, scored)
        if (!doc) {
          const nameLower = name.toLowerCase();
          const nameWords = nameLower.split(/[\s_-]+/).filter((w) => w.length > 2);
          let bestMatch: string | null = null;
          let bestScore = 0;

          for (const id of allIds) {
            const loaded = loadEcad(id);
            if (!loaded) continue;
            const titleLower = ((loaded.title as string) || "").toLowerCase();
            const idLower = id.toLowerCase().replace(/ecd-/g, "").replace(/-/g, " ");
            const searchable = titleLower + " " + idLower;

            // Exact containment
            if (searchable.includes(nameLower) || nameLower.includes(titleLower)) {
              bestMatch = id;
              bestScore = 100;
              break;
            }

            // Word overlap scoring
            let score = 0;
            for (const word of nameWords) {
              if (searchable.includes(word)) score += 1;
              // Partial/stem match (e.g. "builtin" matches "builtins")
              else if (
                searchable.split(/\s+/).some(
                  (sw) => sw.startsWith(word) || word.startsWith(sw)
                )
              ) {
                score += 0.7;
              }
            }
            if (nameWords.length > 0 && score / nameWords.length > bestScore / Math.max(nameWords.length, 1)) {
              bestScore = score;
              bestMatch = id;
            }
          }

          if (bestMatch && bestScore >= 1) {
            doc = loadEcad(bestMatch);
          }
        }

        // Substring match on ID
        if (!doc) {
          const normalized = name
            .toLowerCase()
            .replace(/[_ ]/g, "-");
          const match = allIds.find(
            (id) =>
              id.toLowerCase().includes(normalized) ||
              normalized.includes(id.toLowerCase().replace("ecd-", ""))
          );
          if (match) doc = loadEcad(match);
        }
      }
    }

    if (!doc) {
      const ecadSection = index.ecad;
      const objects = ecadSection?.object_types || [];
      return {
        content: [
          {
            type: "text" as const,
            text: `ECAD doc "${name}" not found.\n\nAvailable ULP object types: ${objects.map((o) => o.replace("ECD-ULP-", "UL_")).join(", ")}\n\nAlso try: "ULP Builtin Functions", "ULP Statements", "ULP Dialogs", "Schematic Editor Commands", "Layout Editor Commands", "Routing Commands"`,
          },
        ],
      };
    }

    // Return the full content
    const content = doc.content as string;
    if (content) {
      return { content: [{ type: "text" as const, text: content }] };
    }

    return {
      content: [
        {
          type: "text" as const,
          text: `# ${doc.title}\n\n${doc.description || "No content available."}`,
        },
      ],
    };
  }
);

// ── Start server ───────────────────────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Fusion API MCP server running on stdio");
}

main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
