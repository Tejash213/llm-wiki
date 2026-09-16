"""
Stage 4 — Backlinks + Cross-Linking

Scans all wiki pages in WIKI_DIR, collects every page title, then
asks GPT-4.1 to enrich each page by adding [[wikilinks]] wherever
another concept is mentioned but not yet linked.

This makes the wiki navigable as a knowledge graph in Obsidian.

Usage:
    python src/crosslink.py
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from src.llm_client import call_llm_crosslink


def load_all_pages() -> dict[str, str]:
    """Return { filename → content } for all non-index wiki pages."""
    pages = {}
    for fname in sorted(os.listdir(config.WIKI_DIR)):
        if fname.startswith("_") or not fname.endswith(".md"):
            continue
        fpath = os.path.join(config.WIKI_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            pages[fname] = f.read()
    return pages


def extract_titles(pages: dict[str, str]) -> dict[str, str]:
    """
    Returns { title → filename } extracted from frontmatter of each page.
    Falls back to filename-derived title if no frontmatter title found.
    """
    titles = {}
    for fname, content in pages.items():
        m = re.search(r'^title:\s*(.+)$', content, re.MULTILINE)
        if m:
            title = m.group(1).strip()
        else:
            title = fname.replace(".md", "").replace("-", " ").title()
        titles[title] = fname
    return titles


SYSTEM_PROMPT = """You are a wiki editor. You will receive:
1. A list of ALL existing wiki page titles.
2. The Markdown content of ONE wiki page.

Your task: Add [[wikilinks]] around any mentions of the listed page titles
that appear in the page body (not the frontmatter) but are NOT yet linked.

IMPORTANT — Obsidian Wikilink Rules:
- Wikilink text MUST exactly match the page title (Title Case with spaces).
  Example: [[AI Strategy]], [[Brava Systems]], [[Multi-Agent AI Orchestration]]
- Do NOT use hyphens or underscores as substitutes for spaces in wikilink text.
- Only link the FIRST mention of each concept per section.
- Do NOT change any other content — preserve all existing text, formatting, and frontmatter exactly.
- Do NOT modify or remove the aliases field in frontmatter.
- Do NOT modify or remove the index backlink at the bottom.
- If a concept is already written as [[Concept]], leave it alone.
- Return ONLY the updated Markdown content of the page, nothing else.
- If no changes are needed, return the page content unchanged.
"""



def crosslink_page(content: str, all_titles: list[str]) -> str:
    """Ask GPT-4.1 to add wikilinks to a single page. Returns updated content."""
    titles_list = "\n".join(f"- {t}" for t in sorted(all_titles))
    user_prompt = f"""All wiki page titles:
{titles_list}

---PAGE CONTENT TO ENRICH---
{content}
"""
    return call_llm_crosslink(SYSTEM_PROMPT, user_prompt, max_tokens=config.MAX_TOKENS_GENERATE)


def run():
    print("=" * 60)
    print("Stage 4 — Cross-Linking Pass")
    print("=" * 60)

    if not os.path.isdir(config.WIKI_DIR):
        print("[ERROR] Wiki directory not found. Run generate_wiki.py first.")
        return

    pages = load_all_pages()
    if not pages:
        print("[ERROR] No wiki pages found. Run generate_wiki.py first.")
        return

    titles_map = extract_titles(pages)
    all_titles = list(titles_map.keys())
    print(f"[Stage 4] {len(pages)} pages found. {len(all_titles)} titles collected.\n")

    enriched = 0
    for fname, content in pages.items():
        print(f"  [LLM]  Cross-linking: {fname}")
        try:
            updated = crosslink_page(content, all_titles)
        except RuntimeError as e:
            print(f"  [ERROR] {e}")
            continue

        if updated.strip() and updated.strip() != content.strip():
            fpath = os.path.join(config.WIKI_DIR, fname)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(updated)
            print(f"    -> Updated with new links")
            enriched += 1
        else:
            print(f"    -> No changes needed")

        time.sleep(0.5)

    print(f"\n[Done] Cross-linking complete. {enriched}/{len(pages)} pages enriched.\n")


if __name__ == "__main__":
    run()
