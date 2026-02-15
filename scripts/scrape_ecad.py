#!/usr/bin/env python3
"""Scrape Fusion ECAD/ULP documentation from Autodesk help site."""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from html.parser import HTMLParser

BASE_URL = "https://help.autodesk.com/cloudhelp/ENU/Fusion-ECAD/files/"
OUT_DIR = Path(__file__).parent.parent / "raw-docs" / "ECAD"


class ContentExtractor(HTMLParser):
    """Extract body content from Autodesk help HTML pages."""

    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self._in_body = False
        self._in_script = False
        self._in_style = False
        self.body_html = ""

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag == "body":
            self._in_body = True
            return
        if tag == "script":
            self._in_script = True
            return
        if tag == "style":
            self._in_style = True
            return
        if self._in_body and not self._in_script and not self._in_style:
            attrs_str = " ".join(f'{k}="{v}"' for k, v in attrs) if attrs else ""
            self.body_html += f"<{tag} {attrs_str}>" if attrs_str else f"<{tag}>"

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "body":
            self._in_body = False
        if tag == "script":
            self._in_script = False
            return
        if tag == "style":
            self._in_style = False
            return
        if self._in_body and not self._in_script and not self._in_style:
            self.body_html += f"</{tag}>"

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_body and not self._in_script and not self._in_style:
            self.body_html += data


def fetch_page(filename):
    """Fetch a single page from the Autodesk help site."""
    url = BASE_URL + filename
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Error fetching {filename}: {e}", file=sys.stderr)
        return None


def html_to_markdown(html_content):
    """Convert HTML body content to clean markdown."""
    body = html_content

    # Remove script/style tags
    body = re.sub(r'<script[^>]*>.*?</script>', '', body, flags=re.DOTALL)
    body = re.sub(r'<style[^>]*>.*?</style>', '', body, flags=re.DOTALL)

    # Remove navigation/footer cruft
    body = re.sub(r'<div[^>]*id="CopyrightNotice"[^>]*>.*?</div>', '', body, flags=re.DOTALL)

    # Convert headings
    body = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', body, flags=re.DOTALL)
    body = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', body, flags=re.DOTALL)
    body = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', body, flags=re.DOTALL)
    body = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', body, flags=re.DOTALL)

    # Convert code blocks
    def replace_pre(m):
        code = m.group(1)
        code = re.sub(r'<span[^>]*>', '', code)
        code = re.sub(r'</span>', '', code)
        code = re.sub(r'<br\s*/?>', '\n', code)
        code = re.sub(r'<[^>]+>', '', code)
        code = code.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        return f'\n```\n{code.strip()}\n```\n'

    body = re.sub(r'<pre[^>]*>(.*?)</pre>', replace_pre, body, flags=re.DOTALL)
    body = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', body, flags=re.DOTALL)

    # Convert tables to markdown
    def replace_table(m):
        table_html = m.group(0)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)
        if not rows:
            return ""
        result = []
        for i, row in enumerate(rows):
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.DOTALL)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&') for c in cells]
            if cells:
                result.append("| " + " | ".join(cells) + " |")
                if i == 0:
                    result.append("| " + " | ".join(["---"] * len(cells)) + " |")
        return "\n" + "\n".join(result) + "\n"

    body = re.sub(r'<table[^>]*>.*?</table>', replace_table, body, flags=re.DOTALL)

    # Convert lists
    body = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', body, flags=re.DOTALL)
    body = re.sub(r'</?[ou]l[^>]*>', '', body)

    # Convert links - keep text only
    body = re.sub(r'<a[^>]*>(.*?)</a>', r'\1', body, flags=re.DOTALL)

    # Convert bold/italic
    body = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', body, flags=re.DOTALL)
    body = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', body, flags=re.DOTALL)
    body = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', body, flags=re.DOTALL)
    body = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', body, flags=re.DOTALL)

    # Convert remaining HTML
    body = re.sub(r'<br\s*/?>', '\n', body)
    body = re.sub(r'<p[^>]*>', '\n', body)
    body = re.sub(r'</p>', '\n', body)
    body = re.sub(r'</?div[^>]*>', '', body)
    body = re.sub(r'<img[^>]*alt="([^"]*)"[^>]*>', r'[Image: \1]', body)
    body = re.sub(r'<img[^>]*>', '', body)
    body = re.sub(r'</?[^>]+>', '', body)

    # Decode entities
    body = body.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
    body = body.replace('&nbsp;', ' ').replace('&quot;', '"')

    # Clean up whitespace
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = re.sub(r' {2,}', ' ', body)
    return body.strip()


# ── Pages to fetch ──────────────────────────────────────────────────────────

# ULP Language Reference pages
ULP_PAGES = {
    # Core language
    "ECD-USER-LANG-REF.htm": "ULP Language Reference",
    "ECD-WRITE-ULP-REF.htm": "Writing a ULP",
    "ECD-EXECUTE-ULP-REF.htm": "Executing a ULP",
    "ECD-ULP-SYNTAX-REF.htm": "ULP Syntax",
    "ECD-ULP-DATA-TYPES-REF.htm": "ULP Data Types",
    "ECD-ULP-DEFINITIONS-REF.htm": "ULP Definitions",
    "ECD-ULP-OPERATORS-REF.htm": "ULP Operators",
    "ECD-ULP-EXPRESSIONS-REF.htm": "ULP Expressions",
    "ECD-ULP-STATEMENTS-REF.htm": "ULP Statements",
    "ECD-ULP-BUILTINS-REF.htm": "ULP Builtin Functions",
    "ECD-ULP-DIALOGS-REF.htm": "ULP Dialogs",
    "ECD-ULP-SUPP-HTML-REF.htm": "ULP Supported HTML Tags",
    "ECD-ULP-OBJECT-TYPES.htm": "ULP Object Types Overview",

    # Object types (54 types)
    "ECD-ULP-ARC.htm": "UL_ARC",
    "ECD-ULP-AREA.htm": "UL_AREA",
    "ECD-ULP-ATTRIBUTE.htm": "UL_ATTRIBUTE",
    "ECD-ULP-BOARD.htm": "UL_BOARD",
    "ECD-ULP-BUS.htm": "UL_BUS",
    "ECD-ULP-CIRCLE.htm": "UL_CIRCLE",
    "ECD-ULP-CLASS.htm": "UL_CLASS",
    "ECD-ULP-CONTACT.htm": "UL_CONTACT",
    "ECD-ULP-CONTACTREF.htm": "UL_CONTACTREF",
    "ECD-ULP-DEVICE.htm": "UL_DEVICE",
    "ECD-ULP-DEVICESET.htm": "UL_DEVICESET",
    "ECD-ULP-DIMENSION.htm": "UL_DIMENSION",
    "ECD-ULP-ELEMENT.htm": "UL_ELEMENT",
    "ECD-ULP-ERROR.htm": "UL_ERROR",
    "ECD-ULP-FOOTPRINT.htm": "UL_FOOTPRINT",
    "ECD-ULP-FRAME.htm": "UL_FRAME",
    "ECD-ULP-GATE.htm": "UL_GATE",
    "ECD-ULP-GRID.htm": "UL_GRID",
    "ECD-ULP-HOLE.htm": "UL_HOLE",
    "ECD-ULP-INSTANCE.htm": "UL_INSTANCE",
    "ECD-ULP-JUNCTION.htm": "UL_JUNCTION",
    "ECD-ULP-LABEL.htm": "UL_LABEL",
    "ECD-ULP-LAYER.htm": "UL_LAYER",
    "ECD-ULP-LIBRARY.htm": "UL_LIBRARY",
    "ECD-ULP-MODULE.htm": "UL_MODULE",
    "ECD-ULP-MODULEINST.htm": "UL_MODULEINST",
    "ECD-ULP-NET.htm": "UL_NET",
    "ECD-ULP-PACKAGE3D.htm": "UL_PACKAGE3D",
    "ECD-ULP-PAD.htm": "UL_PAD",
    "ECD-ULP-PART.htm": "UL_PART",
    "ECD-ULP-PIN.htm": "UL_PIN",
    "ECD-ULP-PINREF.htm": "UL_PINREF",
    "ECD-ULP-POLYCUTOUT.htm": "UL_POLYCUTOUT",
    "ECD-ULP-POLYPOUR.htm": "UL_POLYPOUR",
    "ECD-ULP-POLYSHAPE.htm": "UL_POLYSHAPE",
    "ECD-ULP-PORT.htm": "UL_PORT",
    "ECD-ULP-PORTREF.htm": "UL_PORTREF",
    "ECD-ULP-RECTANGLE.htm": "UL_RECTANGLE",
    "ECD-ULP-SCHEMATIC.htm": "UL_SCHEMATIC",
    "ECD-ULP-SEGMENT.htm": "UL_SEGMENT",
    "ECD-ULP-SHEET.htm": "UL_SHEET",
    "ECD-ULP-SIGNAL.htm": "UL_SIGNAL",
    "ECD-ULP-SMD.htm": "UL_SMD",
    "ECD-ULP-SYMBOL.htm": "UL_SYMBOL",
    "ECD-ULP-TEXT.htm": "UL_TEXT",
    "ECD-ULP-VARIANT.htm": "UL_VARIANT",
    "ECD-ULP-VARIANTDEF.htm": "UL_VARIANTDEF",
    "ECD-ULP-VIA.htm": "UL_VIA",
    "ECD-ULP-WIRE.htm": "UL_WIRE",
}

# Command reference pages
CMD_PAGES = {
    "ECD-CMD-CTRL-CPT.htm": "Command Line Control Overview",
    "ECD-CMD-LINE-CMDS.htm": "Electronics Command Line Reference",
    "ECAD-COMPNT-EDIT-REF.htm": "Library Component Edit Commands",
    "ECD-SCHEMATIC-ED-CMDS-REF.htm": "Schematic Editor Commands",
    "ECD-LAYOUT-EDITOR-REF.htm": "Layout Editor Commands",
    "ECD-ROUTING-CMDS-REF.htm": "Routing Commands",
    "ECD-PRINT-SCHEM-LAYOUT-TSK.htm": "Print Schematic and Layout",
    "ECD-TEXT-VARIABLES-REF.htm": "Text Variables",
}

# General ECAD pages
GENERAL_PAGES = {
    "ECD-AUTOMATION-CPT.htm": "Automation Scripts Overview",
    "ECD-ULP-SCRIPT-ABOUT.htm": "About ULPs and Scripts",
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_pages = {}
    all_pages.update(ULP_PAGES)
    all_pages.update(CMD_PAGES)
    all_pages.update(GENERAL_PAGES)

    total = len(all_pages)
    print(f"Fetching {total} ECAD documentation pages...")

    results = {}
    for i, (filename, title) in enumerate(all_pages.items()):
        print(f"  [{i+1}/{total}] {title} ({filename})")
        html = fetch_page(filename)
        if html:
            parser = ContentExtractor()
            try:
                parser.feed(html)
            except Exception as e:
                print(f"    Parse error: {e}", file=sys.stderr)
                continue

            page_title = parser.title.strip() or title
            markdown = html_to_markdown(parser.body_html)

            if markdown:
                page_id = filename.replace(".htm", "")
                results[page_id] = {
                    "id": page_id,
                    "title": page_title,
                    "content": markdown,
                    "source_file": filename,
                    "category": "ulp_object" if filename.startswith("ECD-ULP-") and title.startswith("UL_") else
                               "ulp_language" if filename.startswith("ECD-ULP-") else
                               "ecad_command" if filename in CMD_PAGES else
                               "ecad_general",
                }

        # Be polite to the server
        if (i + 1) % 10 == 0:
            time.sleep(0.5)

    print(f"\nFetched {len(results)} pages successfully")

    # Save all pages
    with open(OUT_DIR / "ecad_docs.json", 'w') as f:
        json.dump(results, f, indent=2)

    # Also save individual files for easy loading
    for pid, page in results.items():
        with open(OUT_DIR / f"{pid}.json", 'w') as f:
            json.dump(page, f, indent=2)

    print(f"Saved to {OUT_DIR}")

    # Print stats
    categories = {}
    for page in results.values():
        cat = page["category"]
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count} pages")


if __name__ == "__main__":
    main()
