"""
Stage 5 — Continuous Update Cycle

When a new document arrives, this script:
  1. Reads the new document.
  2. Asks GPT-4.1 which existing wiki pages are relevant.
  3. For each relevant page, rewrites/merges it with new information
     (without erasing existing content).
  4. Creates new pages for genuinely new concepts.
  5. Rebuilds the index and re-runs a targeted cross-link pass.

Usage:
    python src/update.py "path/to/new_document.docx"
    python src/update.py  (prompts for path interactively)
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from src.ingest import ingest_documents, read_docx, read_text, extract_date_from_filename
from src.llm_client import call_llm
from src.generate_wiki import save_wiki_page, build_index, title_to_filename, load_processed, save_processed
from src.crosslink import load_all_pages, extract_titles, crosslink_page


# ── Prompts ───────────────────────────────────────────────────────────────────

RELEVANCE_SYSTEM = """You are a wiki knowledge manager. Given:
1. A new document's content.
2. A list of existing wiki page filenames.

IMPORTANT: In this wiki, filenames use Title Case with spaces (e.g. "AI Strategy.md",
"Multi-Agent AI Orchestration.md"). Match against these exact filenames.

Identify which existing pages should be UPDATED with information from the new document,
and which NEW pages should be created for genuinely new concepts not covered yet.

For new pages: the title must be Title Case with spaces. The filename is the title + ".md".
Example: title "Data Governance" => filename "Data Governance.md"
NEVER use hyphens or underscores to replace spaces in filenames.

Return ONLY valid JSON (no markdown fences):
{
  "update": ["Existing Page Title.md", "Another Page.md"],
  "create": [
    { "title": "New Concept Name", "type": "concept|entity|theme" }
  ]
}
"""

MERGE_SYSTEM = """You are a wiki editor merging new information into an existing wiki page.

Rules:
- Preserve ALL existing accurate content.
- Add new facts, claims, and relationships from the new document.
- If the new document contradicts existing content, keep both and note the discrepancy.
- Maintain the existing page template and frontmatter EXACTLY.
- CRITICAL: Preserve the "aliases" field in frontmatter. Do NOT remove or change it.
- Update the last_updated date to today's date.
- Add the new source document to the sources list.
- Use [[wikilinks]] for any referenced concepts. Wikilink text must exactly match
  existing page titles (Title Case with spaces, e.g. [[AI Strategy]], [[Brava Systems]]).
- Keep the index backlink at the bottom: *Part of the [[_index|FutureSense Knowledge Wiki]]*
- Return ONLY the complete updated Markdown page, nothing else.
"""

NEW_PAGE_SYSTEM = """You are a wiki knowledge curator. Create a new Markdown wiki page
for the specified concept, using information from the provided document.

IMPORTANT — Obsidian Naming Rules:
- The filename MUST be the exact page title with spaces preserved + ".md".
  Example: title "Data Governance" => filename "Data Governance.md"
- NEVER use hyphens or underscores to replace spaces.
- Use [[wikilinks]] with EXACT page titles (Title Case with spaces).

Use exactly this template (Obsidian frontmatter):

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
<1-3 sentence summary>

## Key Points
- <bullet points — at least 3>

## Related Concepts
<[[wikilinks]] to related concepts, comma-separated>

## Source Documents
- <source document filename>

---

*Part of the [[_index|FutureSense Knowledge Wiki]]*

Return ONLY the Markdown content, nothing else.
"""


def read_document(filepath: str) -> dict:
    """Read a single document file and return { filename, date, text }."""
    fname = os.path.basename(filepath)
    ext   = os.path.splitext(fname)[1].lower()
    date  = extract_date_from_filename(fname)

    if ext == ".docx":
        text = read_docx(filepath)
    elif ext in (".txt", ".md"):
        text = read_text(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    if len(text) > config.DOC_CHUNK_CHARS:
        text = text[: config.DOC_CHUNK_CHARS] + "\n...[truncated for length]"

    return {"filename": fname, "date": date, "text": text}


def find_relevant_pages(doc: dict, existing_filenames: list[str]) -> dict:
    """Ask GPT-4.1 which pages to update and what new pages to create."""
    fnames_list = "\n".join(f"- {f}" for f in sorted(existing_filenames))
    user_prompt = f"""New document: {doc['filename']} (date: {doc['date']})

Existing wiki pages:
{fnames_list}

---NEW DOCUMENT CONTENT---
{doc['text']}
"""
    raw = call_llm(RELEVANCE_SYSTEM, user_prompt, max_tokens=1024)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  [WARN] Could not parse relevance JSON. Treating as all-new.")
        return {"update": [], "create": []}


def merge_page(existing_content: str, doc: dict) -> str:
    """Ask GPT-4.1 to merge new document info into an existing page."""
    user_prompt = f"""Existing wiki page:
---
{existing_content}
---

New document to integrate ({doc['filename']}, {doc['date']}):
---
{doc['text']}
---

Return the complete updated wiki page."""
    return call_llm(MERGE_SYSTEM, user_prompt, max_tokens=config.MAX_TOKENS_GENERATE)


def create_new_page(concept: dict, doc: dict) -> str:
    """Ask GPT-4.1 to create a new page for a concept from the document."""
    user_prompt = f"""Create a wiki page for the concept: "{concept['title']}" (type: {concept.get('type','concept')})

Extract information from this document ({doc['filename']}, {doc['date']}):
---
{doc['text']}
---
"""
    return call_llm(NEW_PAGE_SYSTEM, user_prompt, max_tokens=config.MAX_TOKENS_GENERATE)


def run(doc_path: str = None):
    print("=" * 60)
    print("Stage 5 — Continuous Update Cycle")
    print("=" * 60)

    if not doc_path:
        doc_path = input("Enter path to new document: ").strip().strip('"')

    if not os.path.isfile(doc_path):
        print(f"[ERROR] File not found: {doc_path}")
        return

    # Check if already processed
    processed = load_processed()
    fname = os.path.basename(doc_path)
    if fname in processed:
        print(f"[WARN] This document has already been processed: {fname}")
        ans = input("Re-process anyway? (y/N): ").strip().lower()
        if ans != "y":
            return

    print(f"\n[Reading] {doc_path}")
    doc = read_document(doc_path)
    print(f"  -> {len(doc['text']):,} characters extracted")

    # Load current wiki
    pages = load_all_pages()
    existing_filenames = list(pages.keys())

    if not existing_filenames:
        print("[WARN] No existing wiki pages found. Run generate_wiki.py first for initial batch.")

    print(f"\n[Relevance] Asking GPT-4.1 which pages to update...")
    plan = find_relevant_pages(doc, existing_filenames)

    to_update = plan.get("update", [])
    to_create = plan.get("create", [])
    print(f"  -> Pages to update: {len(to_update)}")
    print(f"  -> New pages to create: {len(to_create)}\n")

    created_pages = []

    # Merge into existing pages
    for page_fname in to_update:
        if page_fname not in pages:
            print(f"  [SKIP] Page not found in wiki: {page_fname}")
            continue
        print(f"  [MERGE] {page_fname}")
        try:
            updated = merge_page(pages[page_fname], doc)
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            continue

        if updated.strip():
            fpath = os.path.join(config.WIKI_DIR, page_fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"    -> Updated")
        time.sleep(0.5)

    # Create new pages
    for concept in to_create:
        title    = concept.get("title", "Untitled")
        filename = concept.get("filename") or title_to_filename(title)
        print(f"  [NEW]   {title} -> {filename}")
        try:
            content = create_new_page(concept, doc)
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            continue

        if content.strip():
            save_wiki_page(title, filename, content)
            created_pages.append({"title": title, "filename": filename})
            print(f"    -> Created")
        time.sleep(0.5)

    # Mark as processed
    processed[fname] = {
        "date": doc["date"],
        "updated_pages": to_update,
        "created_pages": [p["filename"] for p in created_pages],
    }
    save_processed(processed)

    # Rebuild index
    print("\n[Index] Rebuilding _index.md ...")
    all_pages_content = load_all_pages()
    titles_map = extract_titles(all_pages_content)
    index_data = {}
    for title, f in titles_map.items():
        content = all_pages_content.get(f, "")
        m = re.search(r'^type:\s*(.+)$', content, re.MULTILINE)
        ptype = m.group(1).strip() if m else "unknown"
        index_data[title] = {"type": ptype, "filename": f}
    build_index(index_data)

    # Targeted cross-link pass for modified/new pages
    affected = set(to_update) | {p["filename"] for p in created_pages}
    if affected:
        print(f"\n[Cross-link] Enriching {len(affected)} affected pages...")
        all_titles = list(titles_map.keys())
        for page_fname in affected:
            fpath = os.path.join(config.WIKI_DIR, page_fname)
            if not os.path.isfile(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            print(f"  [LLM]  {page_fname}")
            try:
                updated = crosslink_page(content, all_titles)
            except RuntimeError as e:
                print(f"  [ERROR] {e}")
                continue
            if updated.strip() and updated.strip() != content.strip():
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(updated)
                print(f"    -> Links added")
            time.sleep(0.5)

    print(f"\n[Done] Update complete.")
    print(f"  Updated: {len(to_update)} pages")
    print(f"  Created: {len(created_pages)} new pages\n")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    run(path)
