#!/usr/bin/env python3
"""Parse Autodesk Fusion API CHM-extracted HTML into structured JSON for MCP server."""

import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HTML_DIR = Path(__file__).parent.parent / "raw-docs" / "HTML"
OUT_DIR = Path(__file__).parent.parent / "parsed-docs"


class TextExtractor(HTMLParser):
    """Extract visible text from HTML, stripping tags."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def get_text(self):
        return "".join(self.parts).strip()


class APIPageParser(HTMLParser):
    """Parse a Fusion API HTML page into structured data."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta = {}
        self.sections = {}  # section_name -> list of content chunks
        self._current_section = None
        self._in_h1 = False
        self._in_h2 = False
        self._in_title = False
        self._in_pre = False
        self._in_td = False
        self._in_a = False
        self._current_h2 = ""
        self._current_row = []
        self._current_cell = ""
        self._current_link = ""
        self._current_link_href = ""
        self._pre_content = ""
        self._pre_id = ""
        self._in_table = 0
        self._row_data = []
        self._body_text_parts = []
        self._skip_script = False
        self._div_id = ""
        self._current_tab = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)

        if tag == "script":
            self._skip_script = True
            return
        if tag == "style":
            self._skip_script = True
            return

        if tag == "meta":
            name = attrs_dict.get("name", "")
            content = attrs_dict.get("content", "")
            if name and content:
                self.meta[name] = content

        if tag == "title":
            self._in_title = True

        if tag == "h1":
            self._in_h1 = True
        if tag == "h2":
            self._in_h2 = True
            self._current_h2 = ""

        if tag == "div":
            div_id = attrs_dict.get("id", "")
            if div_id in ("Python", "C++"):
                self._current_tab = div_id

        if tag == "pre":
            self._in_pre = True
            self._pre_content = ""
            self._pre_id = attrs_dict.get("id", "")

        if tag == "table":
            self._in_table += 1
            self._row_data = []

        if tag == "tr" and self._in_table:
            self._current_row = []
            self._current_cell = ""

        if tag == "td" and self._in_table:
            self._in_td = True
            self._current_cell = ""

        if tag == "a":
            self._in_a = True
            self._current_link_href = attrs_dict.get("href", "")
            self._current_link = ""

        if tag == "br":
            if self._in_pre:
                self._pre_content += "\n"
            elif self._in_td:
                self._current_cell += " "

    def handle_endtag(self, tag):
        if tag == "script":
            self._skip_script = False
            return
        if tag == "style":
            self._skip_script = False
            return

        if tag == "title":
            self._in_title = False

        if tag == "h1":
            self._in_h1 = False

        if tag == "h2":
            self._in_h2 = False
            section = self._current_h2.strip()
            if section:
                self._current_section = section
                if section not in self.sections:
                    self.sections[section] = []

        if tag == "pre":
            self._in_pre = False
            if self._current_section and self._pre_content.strip():
                tab = self._current_tab or ""
                self.sections.setdefault(self._current_section, []).append(
                    {"type": "code", "language": tab, "content": self._pre_content.strip(), "id": self._pre_id}
                )

        if tag == "div":
            if self._current_tab:
                self._current_tab = ""

        if tag == "td" and self._in_table:
            self._in_td = False
            self._current_row.append(self._current_cell.strip())

        if tag == "tr" and self._in_table and self._current_row:
            self._row_data.append(self._current_row)

        if tag == "table" and self._in_table:
            self._in_table -= 1
            if self._current_section and self._row_data:
                self.sections.setdefault(self._current_section, []).append(
                    {"type": "table", "rows": self._row_data}
                )
            self._row_data = []

        if tag == "a":
            self._in_a = False
            if self._in_td and self._current_link_href:
                # Store link info in cell text
                link_text = self._current_link.strip()
                if link_text:
                    href = self._current_link_href.replace(".htm", "")
                    self._current_cell += link_text

        if tag == "p" and self._current_section:
            pass  # paragraphs handled via data

    def handle_data(self, data):
        if self._skip_script:
            return

        if self._in_title:
            self.title += data

        if self._in_h1:
            self.title = data.strip()

        if self._in_h2:
            self._current_h2 += data

        if self._in_pre:
            self._pre_content += data

        elif self._in_a:
            self._current_link += data
            if self._in_td:
                pass  # link text will be added in endtag handler

        elif self._in_td:
            self._current_cell += data

        elif self._current_section and not self._in_table:
            text = data.strip()
            if text:
                self.sections.setdefault(self._current_section, []).append(
                    {"type": "text", "content": text}
                )

    def handle_entityref(self, name):
        char_map = {"lt": "<", "gt": ">", "amp": "&", "nbsp": " ", "quot": '"'}
        char = char_map.get(name, f"&{name};")
        if self._in_pre:
            self._pre_content += char
        elif self._in_td:
            self._current_cell += char


def strip_html(html_str):
    """Remove HTML tags and return plain text."""
    extractor = TextExtractor()
    try:
        extractor.feed(html_str)
    except Exception:
        pass
    return extractor.get_text()


def clean_code(code_str):
    """Clean up code content - remove HTML color spans etc."""
    # Remove <span style="color:blue"> tags (used for comments)
    code = re.sub(r'<span[^>]*>', '', code_str)
    code = re.sub(r'</span>', '', code)
    code = re.sub(r'<br\s*/?>', '\n', code)
    code = re.sub(r'<[^>]+>', '', code)
    # Decode HTML entities
    code = code.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    return code.strip()


def extract_guide_content(html_content):
    """Extract rich text content from guide/UM pages using regex-based approach."""
    # Extract body content
    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL)
    if not body_match:
        return ""
    body = body_match.group(1)

    # Remove script tags
    body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL)
    # Remove style/link tags
    body = re.sub(r'<link[^>]*>', '', body)
    body = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL)
    # Remove copyright div
    body = re.sub(r'<div id="CopyrightNotice".*?</div>', '', body, flags=re.DOTALL)
    # Remove img tags but keep alt text
    body = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r'[Image: \1]', body)
    body = re.sub(r'<img[^>]*>', '', body)

    # Convert headings
    body = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', body, flags=re.DOTALL)
    body = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', body, flags=re.DOTALL)
    body = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', body, flags=re.DOTALL)

    # Convert code blocks
    def replace_pre(m):
        code = m.group(1)
        code = clean_code(code)
        return f'\n```\n{code}\n```\n'
    body = re.sub(r'<pre[^>]*>(.*?)</pre>', replace_pre, body, flags=re.DOTALL)

    # Convert links
    body = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'\2', body, flags=re.DOTALL)

    # Convert remaining HTML
    body = re.sub(r'<br\s*/?>', '\n', body)
    body = re.sub(r'<p[^>]*>', '\n', body)
    body = re.sub(r'</p>', '\n', body)
    body = re.sub(r'<div[^>]*>', '', body)
    body = re.sub(r'</div>', '', body)
    body = re.sub(r'</?[^>]+>', '', body)

    # Decode entities
    body = body.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&nbsp;', ' ')

    # Clean up whitespace
    body = re.sub(r'\n{3,}', '\n\n', body)
    return body.strip()


def parse_file(filepath):
    """Parse a single HTML file and return structured data."""
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    parser = APIPageParser()
    try:
        parser.feed(content)
    except Exception as e:
        return None

    filename = os.path.basename(filepath).replace('.htm', '')

    # Extract namespace and header from body text
    namespace = ""
    header_file = ""
    ns_match = re.search(r'namespace\s+"([^"]+)"', content)
    if ns_match:
        namespace = ns_match.group(1)
    hdr_match = re.search(r'header file is &lt;([^&]+)&gt;', content)
    if hdr_match:
        header_file = hdr_match.group(1)

    # Determine parent/inheritance
    parent_class = ""
    derived_match = re.search(r'Derived from:\s*<a[^>]*>([^<]+)</a>', content)
    if derived_match:
        parent_class = derived_match.group(1).strip()
    parent_match = re.search(r'Parent Object:\s*<a[^>]*>([^<]+)</a>', content)
    if parent_match:
        parent_class = parent_match.group(1).strip()

    # Extract description
    description = ""
    desc_sections = parser.sections.get("Description", [])
    for item in desc_sections:
        if item["type"] == "text":
            description += item["content"] + " "
    description = description.strip()

    # Clean trailing section names from descriptions (e.g. "... Methods" or "... Code Samples")
    description = re.sub(r'\s+(Methods|Properties|Events|Code Samples|Samples|Syntax)\s*$', '', description)

    # Determine page type from filename and content
    page_type = "class"
    if "_UM" in filename:
        page_type = "guide"
    elif "_Sample" in filename:
        page_type = "sample"
    elif "_" in filename and not filename.startswith("_"):
        parts = filename.split("_", 1)
        if len(parts) == 2:
            member_name = parts[1]
            if "Method" in parser.title:
                page_type = "method"
            elif "Property" in parser.title:
                page_type = "property"
            elif "Event" in parser.title:
                page_type = "event"
            else:
                # Check content for clues
                if "Return Value" in parser.sections or "Parameters" in parser.sections:
                    page_type = "method"
                elif "Property Value" in parser.sections:
                    page_type = "property"
                else:
                    page_type = "member"

    result = {
        "id": filename,
        "title": parser.title.strip(),
        "type": page_type,
        "namespace": namespace,
        "header_file": header_file,
        "description": description,
        "parent_class": parent_class,
    }

    # For guide pages, extract the full rich body content
    if page_type == "guide":
        guide_content = extract_guide_content(content)
        if guide_content:
            result["content"] = guide_content

    # Extract syntax (Python & C++)
    syntax_section = parser.sections.get("Syntax", [])
    python_syntax = ""
    cpp_syntax = ""
    for item in syntax_section:
        if item["type"] == "code":
            code = clean_code(item["content"])
            if item.get("language") == "Python" or "Python" in item.get("id", ""):
                python_syntax = code
            elif item.get("language") == "C++" or "C++" in item.get("id", ""):
                cpp_syntax = code

    if python_syntax or cpp_syntax:
        result["syntax"] = {}
        if python_syntax:
            result["syntax"]["python"] = python_syntax
        if cpp_syntax:
            result["syntax"]["cpp"] = cpp_syntax

    # Extract return value
    rv_section = parser.sections.get("Return Value", [])
    for item in rv_section:
        if item["type"] == "table" and item["rows"]:
            for row in item["rows"]:
                if len(row) >= 2 and row[0] not in ("Type", "Name"):
                    result["return_type"] = row[0]
                    result["return_description"] = row[1]
                    break

    # Extract property value
    pv_section = parser.sections.get("Property Value", [])
    for item in pv_section:
        if item["type"] == "text":
            result["property_value"] = item["content"]

    # Extract parameters
    params_section = parser.sections.get("Parameters", [])
    params = []
    for item in params_section:
        if item["type"] == "table":
            for row in item["rows"]:
                if len(row) >= 3 and row[0] not in ("Name", ""):
                    params.append({
                        "name": row[0],
                        "type": row[1],
                        "description": row[2]
                    })
                elif len(row) >= 2 and row[0] not in ("Name", ""):
                    params.append({
                        "name": row[0],
                        "type": row[1] if len(row) > 1 else "",
                        "description": row[2] if len(row) > 2 else ""
                    })
    if params:
        result["parameters"] = params

    # Extract methods table (for class pages)
    methods_section = parser.sections.get("Methods", [])
    methods = []
    for item in methods_section:
        if item["type"] == "table":
            for row in item["rows"]:
                if len(row) >= 2 and row[0] not in ("Name", ""):
                    methods.append({"name": row[0], "description": row[1]})
    if methods:
        result["methods"] = methods

    # Extract properties table (for class pages)
    props_section = parser.sections.get("Properties", [])
    props = []
    for item in props_section:
        if item["type"] == "table":
            for row in item["rows"]:
                if len(row) >= 2 and row[0] not in ("Name", ""):
                    props.append({"name": row[0], "description": row[1]})
    if props:
        result["properties"] = props

    # Extract events table (for class pages)
    events_section = parser.sections.get("Events", [])
    events = []
    for item in events_section:
        if item["type"] == "table":
            for row in item["rows"]:
                if len(row) >= 2 and row[0] not in ("Name", ""):
                    events.append({"name": row[0], "description": row[1]})
    if events:
        result["events"] = events

    # Extract code samples
    code_section = parser.sections.get("Code Samples", [])
    code_samples = {}
    for item in code_section:
        if item["type"] == "code":
            code = clean_code(item["content"])
            lang = item.get("language", "")
            if not lang:
                pid = item.get("id", "")
                if "Python" in pid:
                    lang = "Python"
                elif "C++" in pid:
                    lang = "C++"
            if lang and code:
                code_samples[lang.lower().replace("++", "pp")] = code
    if code_samples:
        result["code_samples"] = code_samples

    # Extract linked samples
    samples_section = parser.sections.get("Samples", [])
    samples = []
    for item in samples_section:
        if item["type"] == "table":
            for row in item["rows"]:
                if len(row) >= 2 and row[0] not in ("Name", ""):
                    samples.append({"name": row[0], "description": row[1]})
    if samples:
        result["related_samples"] = samples

    # Extract version
    version_section = parser.sections.get("Version", [])
    for item in version_section:
        if item["type"] == "text" and "Introduced" in item["content"]:
            result["version"] = item["content"].strip()

    return result


def build_class_index(all_pages):
    """Build a consolidated class index with members embedded."""
    classes = {}
    members = {}
    samples = {}
    guides = {}

    for page in all_pages:
        if page is None:
            continue
        pid = page["id"]
        ptype = page["type"]

        if ptype == "sample":
            samples[pid] = page
        elif ptype == "class":
            classes[pid] = page
        elif ptype in ("method", "property", "event", "member"):
            members[pid] = page
        elif "_UM" in pid:
            guides[pid] = page

    # Embed member details into class pages
    for mid, member in members.items():
        parts = mid.split("_", 1)
        if len(parts) == 2:
            class_name = parts[0]
            member_name = parts[1]
            if class_name in classes:
                cls = classes[class_name]
                key = "method_details" if member["type"] == "method" else \
                      "property_details" if member["type"] == "property" else \
                      "event_details" if member["type"] == "event" else "member_details"
                if key not in cls:
                    cls[key] = {}
                cls[key][member_name] = member

    return classes, samples, guides


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    htm_files = sorted(HTML_DIR.glob("*.htm"))
    print(f"Parsing {len(htm_files)} HTML files...")

    all_pages = []
    errors = 0
    for i, f in enumerate(htm_files):
        if (i + 1) % 1000 == 0:
            print(f"  Processed {i + 1}/{len(htm_files)}...")
        try:
            page = parse_file(f)
            if page:
                all_pages.append(page)
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  Error parsing {f.name}: {e}")

    print(f"Parsed {len(all_pages)} pages ({errors} errors)")

    classes, samples, guides = build_class_index(all_pages)
    print(f"Found {len(classes)} classes, {len(samples)} samples, {len(guides)} guides")

    # Build namespace index
    namespaces = {}
    for cname, cls in classes.items():
        ns = cls.get("namespace", "unknown")
        if ns not in namespaces:
            namespaces[ns] = []
        namespaces[ns].append(cname)

    # Write consolidated class data (one file per class for efficient loading)
    classes_dir = OUT_DIR / "classes"
    classes_dir.mkdir(exist_ok=True)
    for cname, cls in classes.items():
        with open(classes_dir / f"{cname}.json", 'w') as f:
            json.dump(cls, f, indent=2)

    # Write samples
    samples_dir = OUT_DIR / "samples"
    samples_dir.mkdir(exist_ok=True)
    for sname, sample in samples.items():
        with open(samples_dir / f"{sname}.json", 'w') as f:
            json.dump(sample, f, indent=2)

    # Write guides
    guides_dir = OUT_DIR / "guides"
    guides_dir.mkdir(exist_ok=True)
    for gname, guide in guides.items():
        with open(guides_dir / f"{gname}.json", 'w') as f:
            json.dump(guide, f, indent=2)

    # Write the master index (lightweight - just names, namespaces, descriptions)
    index = {
        "classes": {},
        "namespaces": namespaces,
        "sample_names": list(samples.keys()),
        "guide_names": list(guides.keys()),
    }
    for cname, cls in classes.items():
        index["classes"][cname] = {
            "namespace": cls.get("namespace", ""),
            "description": cls.get("description", "")[:200],
            "parent_class": cls.get("parent_class", ""),
            "method_count": len(cls.get("methods", [])),
            "property_count": len(cls.get("properties", [])),
            "event_count": len(cls.get("events", [])),
        }

    with open(OUT_DIR / "index.json", 'w') as f:
        json.dump(index, f, indent=2)

    # Write search corpus - one line per searchable item for full-text indexing
    search_items = []
    for cname, cls in classes.items():
        # Class entry
        search_items.append({
            "id": cname,
            "type": "class",
            "name": cname,
            "namespace": cls.get("namespace", ""),
            "description": cls.get("description", ""),
            "parent_class": cls.get("parent_class", ""),
        })
        # Method entries
        for m in cls.get("methods", []):
            search_items.append({
                "id": f"{cname}_{m['name']}",
                "type": "method",
                "class_name": cname,
                "name": m["name"],
                "namespace": cls.get("namespace", ""),
                "description": m.get("description", ""),
            })
        # Property entries
        for p in cls.get("properties", []):
            search_items.append({
                "id": f"{cname}_{p['name']}",
                "type": "property",
                "class_name": cname,
                "name": p["name"],
                "namespace": cls.get("namespace", ""),
                "description": p.get("description", ""),
            })
        # Event entries
        for e in cls.get("events", []):
            search_items.append({
                "id": f"{cname}_{e['name']}",
                "type": "event",
                "class_name": cname,
                "name": e["name"],
                "namespace": cls.get("namespace", ""),
                "description": e.get("description", ""),
            })

    # Sample entries
    for sname, sample in samples.items():
        search_items.append({
            "id": sname,
            "type": "sample",
            "name": sample.get("title", sname),
            "description": sample.get("description", ""),
        })

    # Guide entries
    for gname, guide in guides.items():
        search_items.append({
            "id": gname,
            "type": "guide",
            "name": guide.get("title", gname),
            "description": guide.get("description", ""),
        })

    with open(OUT_DIR / "search_corpus.json", 'w') as f:
        json.dump(search_items, f, indent=2)

    print(f"Written {len(search_items)} searchable items to search_corpus.json")
    print(f"Output directory: {OUT_DIR}")
    print("Done!")


if __name__ == "__main__":
    main()
