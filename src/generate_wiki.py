"""
Stage 2 + 3 — Initial Wiki Generation (one-time batch)

For each ingested document, asks GPT-4.1 to:
  • Extract all distinct concepts, entities, themes, and ideas
  • Write a Markdown wiki page for each (with Obsidian [[wikilinks]])

Also generates:
  • _index.md   — master index of all pages
  • _processed.json — tracks which docs have been done (allows safe re-run)

Usage:
    python src/generate_wiki.py
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from src.ingest import ingest_documents
from src.llm_client import call_llm

# ── Prompts ───────────────────────────────────────────────────────────────────────────
#
# Obsidian Compatibility Rules (from official Obsidian docs):
#   1. Obsidian resolves [[Wikilink]] by FILENAME (without .md), NOT by frontmatter title.
#   2. Resolution is case-insensitive but filename must match the link text exactly.
#   3. Spaces in filenames are natively supported by Obsidian wikilinks.
#   4. aliases: [...] in YAML frontmatter provides alternative names for resolution.
#   5. YAML frontmatter must be at the very top of the file between --- lines.
#   6. Illegal Windows filename characters: / \ : * ? " < > |
#
# Therefore: filename MUST equal the page title (with .md extension).
#            [[AI Strategy]] resolves to "AI Strategy.md"
#

SYSTEM_PROMPT = """You are a knowledge curator building a structured Markdown wiki
for an organization. Your task is to read a document and produce wiki pages in
valid Obsidian-compatible Markdown.

IMPORTANT — Obsidian Naming Rules:
- Obsidian resolves [[Wikilink]] by matching against the FILENAME on disk.
- Therefore, the filename MUST be the exact page title with spaces preserved.
  Example: title "AI Strategy" => filename "AI Strategy.md"
  Example: title "Multi-Agent AI Orchestration" => filename "Multi-Agent AI Orchestration.md"
- NEVER convert spaces to hyphens or underscores in filenames.
- If the title contains / or \\ or : or * or ? or " or < or > or |, replace them
  with a space-dash-space " - " (e.g. "General/Coordinator" => "General - Coordinator").

IMPORTANT — Wikilink Rules:
- Use [[Double Bracket]] Obsidian wikilinks to reference related concepts.
- Wikilink text must be the EXACT page title (Title Case with spaces).
  e.g. [[AI Agents]], [[Enterprise Transformation]], [[Brava Systems]]
- Be consistent: always use the same spelling for the same concept.
- Do NOT wrap wikilinks in backticks or code blocks.

Rules:
- Write clear, factual prose — no speculation.
- Extract EVERY distinct concept, entity, and theme comprehensively.
- Every page must use exactly this template (no deviations):

---
title: <Page Title>
aliases:
  - <Page Title>
type: <entity|concept|theme>
tags: []
last_updated: <YYYY-MM-DD>
sources: []
---

## Summary
<1-3 sentence summary — clear and factual>

## Key Points
- <bullet points of important claims or facts>
- <each bullet should be independently meaningful>
- <at least 3 bullet points>

## Related Concepts
<comma-separated list of [[wikilinks]] to related pages>

## Source Documents
- <source document filename>

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*

Output ONLY valid JSON in this exact shape (nothing else, no markdown fences):
{
  "pages": [
    {
      "title": "Page Title",
      "type": "concept|entity|theme",
      "filename": "Page Title.md",
      "content": "... full markdown content using the template above ..."
    }
  ]
}
"""

USER_TEMPLATE = """Document filename: {filename}
Document date: {date}

---BEGIN DOCUMENT---
{text}
---END DOCUMENT---

Extract ALL distinct concepts, entities (companies, products, people), and themes
from this document. For EACH one write a complete wiki page using the template.

REMINDER:
- filename = exact page title with .md extension (spaces preserved, Title Case).
  Example: "AI Strategy.md", NOT "ai-strategy.md"
- Wikilink text must exactly match a page title.
- Include the aliases field in frontmatter.
- End every page with: *Part of the [[_index|FutureSense Knowledge Wiki]]*

Return only the JSON object described."""


def title_to_filename(title: str) -> str:
    """
    Convert a page title to an Obsidian-compatible filename.

    Obsidian convention: filename = exact title + ".md" with spaces preserved.
    Only illegal Windows filename characters are replaced.
    """
    name = title
    # Replace characters illegal in Windows filenames
    name = name.replace("/", " - ")
    name = name.replace("\\", " - ")
    name = name.replace(":", " -")
    name = name.replace("*", "")
    name = name.replace("?", "")
    name = name.replace('"', "'")
    name = name.replace("<", "")
    name = name.replace(">", "")
    name = name.replace("|", " - ")
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = "Untitled"
    return name + ".md"


def slugify(title: str) -> str:
    """DEPRECATED: Use title_to_filename() instead. Kept for backward compat."""
    return title_to_filename(title)


def load_processed() -> dict:
    if os.path.isfile(config.PROCESSED_LOG):
        with open(config.PROCESSED_LOG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_processed(processed: dict) -> None:
    os.makedirs(config.WIKI_DIR, exist_ok=True)
    with open(config.PROCESSED_LOG, "w", encoding="utf-8") as f:
        json.dump(processed, f, indent=2)


def save_wiki_page(title: str, filename: str, content: str) -> str:
    """
    Write a wiki page to WIKI_DIR; returns the path written.

    Obsidian convention: filename = title with spaces + ".md".
    This function also ensures:
    - The filename uses the title (not a slug) as the name.
    - aliases are present in YAML frontmatter for extra resolution robustness.
    - The page has a backlink to _index at the bottom.
    """
    os.makedirs(config.WIKI_DIR, exist_ok=True)

    # Always derive filename from title for Obsidian compatibility
    safe_filename = title_to_filename(title)
    path = os.path.join(config.WIKI_DIR, safe_filename)

    # Ensure content has aliases in frontmatter (safety net if LLM omits it)
    content = _ensure_aliases(title, content)

    # Ensure content has index backlink at the bottom
    content = _ensure_index_backlink(content)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return path


def _ensure_aliases(title: str, content: str) -> str:
    """Ensure the YAML frontmatter contains aliases for Obsidian resolution."""
    if re.search(r'^aliases:', content, re.MULTILINE):
        return content  # already has aliases
    # Insert aliases right after the title line
    title_pattern = re.compile(r'^(title:\s*.+)$', re.MULTILINE)
    m = title_pattern.search(content)
    if m:
        insert_pos = m.end()
        alias_line = f'\naliases:\n  - "{title}"'
        content = content[:insert_pos] + alias_line + content[insert_pos:]
    return content


def _ensure_index_backlink(content: str) -> str:
    """Ensure the page has a backlink to [[_index]] at the bottom."""
    if "[[_index" in content:
        return content  # already has backlink
    if not content.endswith("\n"):
        content += "\n"
    content += "\n---\n\n*Part of the [[_index|FutureSense Knowledge Wiki]]*\n"
    return content


def _sanitise_json(raw: str) -> str:
    """
    Clean common issues in LLM JSON output:
    - Strip markdown fences
    - Replace literal control characters inside JSON strings (\n, \t, etc.)
      that cause json.JSONDecodeError 'Invalid control character'
    """
    raw = raw.strip()
    # Remove markdown code fences
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    raw = raw.strip()

    # Replace literal control chars inside JSON string values.
    # We do this by scanning char-by-char tracking whether we're inside a string.
    result = []
    in_string = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\\' and in_string:
            # Escaped char — keep both backslash and next char as-is
            result.append(ch)
            i += 1
            if i < len(raw):
                result.append(raw[i])
                i += 1
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ord(ch) < 0x20:
            # Literal control character inside a string — escape it
            escapes = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}
            result.append(escapes.get(ch, f"\\u{ord(ch):04x}"))
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def generate_wiki_from_document(doc: dict, skill_override: str = None) -> list[dict]:
    """
    Ask the LLM to extract concepts from one document and produce wiki pages.
    Returns list of { title, filename, content, path } for pages created.
    Retries on transient 503 errors with exponential backoff.

    Args:
        doc:            { filename, date, text } dict from ingest.
        skill_override: If provided, replaces SYSTEM_PROMPT with the given skill text.
                        Used by SkillOpt to inject the current optimized skill.
    """
    # Truncate very long docs to avoid context overflow
    text = doc["text"]
    if len(text) > config.DOC_CHUNK_CHARS:
        text = text[: config.DOC_CHUNK_CHARS] + "\n...[truncated for length]"

    user_prompt = USER_TEMPLATE.format(
        filename=doc["filename"],
        date=doc["date"],
        text=text,
    )

    active_system_prompt = skill_override.strip() if skill_override else SYSTEM_PROMPT

    print(f"  [LLM]  Generating wiki pages for: {doc['filename']}")

    # Retry loop for transient errors (503, 429)
    raw = None
    for attempt in range(1, 4):   # up to 3 attempts
        try:
            raw = call_llm(active_system_prompt, user_prompt, max_tokens=config.MAX_TOKENS_GENERATE)
            break
        except RuntimeError as e:
            err_str = str(e)
            if ("503" in err_str or "429" in err_str) and attempt < 3:
                wait = 15 * attempt
                print(f"  [RETRY] Transient error (attempt {attempt}/3), waiting {wait}s: {err_str[:80]}")
                time.sleep(wait)
            else:
                print(f"  [ERROR] LLM call failed after {attempt} attempt(s): {e}")
                return []

    if raw is None:
        return []

    # Clean and parse JSON
    raw = _sanitise_json(raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [WARN] JSON parse error for {doc['filename']}: {e}")
        print(f"         Raw response (first 300 chars): {raw[:300]}")
        return []

    created = []
    for page in data.get("pages", []):
        title    = page.get("title", "Untitled")
        # Always use title_to_filename — ignore LLM-suggested filename (may be slug)
        filename = title_to_filename(title)
        content  = page.get("content", "")

        if not content.strip():
            continue

        path = save_wiki_page(title, filename, content)
        created.append({
            "title":    title,
            "filename": filename,
            "content":  content,
            "path":     path,
        })
        print(f"    -> Saved: {filename}")

    return created


def build_index(all_pages: dict) -> None:
    """
    Write _index.md — a master table of contents linking every wiki page.

    Every wiki page title is listed as a [[wikilink]], which Obsidian resolves
    by matching against the filename (which equals the title).
    """
    os.makedirs(config.WIKI_DIR, exist_ok=True)

    # Categorise pages
    entities  = []
    concepts  = []
    themes    = []
    uncategorised = []

    for title, meta in sorted(all_pages.items()):
        ptype = meta.get("type", "").lower()
        entry = f"- [[{title}]]"
        if ptype == "entity":
            entities.append(entry)
        elif ptype == "concept":
            concepts.append(entry)
        elif ptype == "theme":
            themes.append(entry)
        else:
            uncategorised.append(entry)

    lines = [
        "---",
        "title: Wiki Index",
        "type: index",
        "---",
        "",
        "# FutureSense Knowledge Wiki",
        "",
        "> Auto-generated from FutureSense documents using GPT-4.1.  ",
        "> Open this folder in [Obsidian](https://obsidian.md) to explore the knowledge graph.",
        "",
        "---",
        "",
    ]

    if entities:
        lines += ["## Entities", ""] + entities + [""]
    if concepts:
        lines += ["## Concepts", ""] + concepts + [""]
    if themes:
        lines += ["## Themes", ""] + themes + [""]
    if uncategorised:
        lines += ["## Other", ""] + uncategorised + [""]

    path = os.path.join(config.WIKI_DIR, "_index.md")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print(f"\n[Index] Written: {path}")


def run():
    print("=" * 60)
    print("Stage 2+3 — Initial Wiki Generation")
    print("=" * 60)

    os.makedirs(config.WIKI_DIR, exist_ok=True)

    # Load ingested documents
    docs = ingest_documents()
    if not docs:
        print("[ERROR] No documents found. Check DOCUMENTS_DIR in config.py")
        return

    # Load progress tracking
    processed = load_processed()
    print(f"[Progress] {len(processed)} documents already processed.\n")

    # Master registry of all pages: { title -> { type, filename } }
    # We'll rebuild this from existing pages + new ones
    all_pages = {}

    # Scan existing .md files to populate all_pages registry
    for fname in os.listdir(config.WIKI_DIR):
        if fname.startswith("_") or not fname.endswith(".md"):
            continue
        fpath = os.path.join(config.WIKI_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            first_lines = "".join([f.readline() for _ in range(10)])
        title_m = re.search(r'^title:\s*(.+)$', first_lines, re.MULTILINE)
        type_m  = re.search(r'^type:\s*(.+)$',  first_lines, re.MULTILINE)
        if title_m:
            title = title_m.group(1).strip()
            ptype = type_m.group(1).strip() if type_m else "unknown"
            all_pages[title] = {"type": ptype, "filename": fname}

    # Process each document
    for doc in docs:
        if doc["filename"] in processed:
            print(f"  [SKIP] Already processed: {doc['filename']}")
            continue

        pages = generate_wiki_from_document(doc)

        for page in pages:
            all_pages[page["title"]] = {
                "type": "unknown",  # will be refined on re-read
                "filename": page["filename"],
            }
            # Re-read to get the type from frontmatter
            fpath = os.path.join(config.WIKI_DIR, page["filename"])
            if os.path.isfile(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    head = "".join([f.readline() for _ in range(10)])
                type_m = re.search(r'^type:\s*(.+)$', head, re.MULTILINE)
                if type_m:
                    all_pages[page["title"]]["type"] = type_m.group(1).strip()

        processed[doc["filename"]] = {
            "date": doc["date"],
            "pages_created": [p["filename"] for p in pages],
        }
        save_processed(processed)

        # Small delay to avoid rate-limiting
        time.sleep(1)

    # Rebuild index
    build_index(all_pages)

    total_pages = len([f for f in os.listdir(config.WIKI_DIR)
                       if f.endswith(".md") and not f.startswith("_")])
    print(f"\n[Done] Wiki contains {total_pages} pages.")
    print(f"       Open '{config.WIKI_DIR}' in Obsidian to explore.\n")


if __name__ == "__main__":
    run()
