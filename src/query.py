"""
Stage 7 — Wiki Query Interface (Antigravity AI Edition)

Lets you search and query the knowledge wiki directly from the terminal.
All AI answers are provided by the Antigravity IDE's built-in AI — no API keys needed.

Two modes:
  --search / -s  →  Pure keyword search — prints matching wiki pages instantly,
                    no AI required.
  (default)      →  Interactive mode — sends your question + relevant wiki pages
                    to the Antigravity AI chat pane, which replies with a
                    synthesised answer.

Usage:
    python main.py --query                         ← interactive AI query mode
    python main.py --query --search                ← pure keyword search (no AI)
    python src/query.py "What is Brava's strategy?" ← single-shot AI query
    python src/query.py -s "AI agents"              ← single-shot keyword search
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

# ── Settings ──────────────────────────────────────────────────────────────────
TOP_N         = 5     # pages to retrieve per query
MAX_HOPS      = 1     # link-traversal hops
PREVIEW_CHARS = 500   # characters to preview per page in search mode

# ── Page loading ──────────────────────────────────────────────────────────────

def load_wiki_pages() -> dict[str, str]:
    """Return { filename → content } for all non-index pages."""
    pages = {}
    if not os.path.isdir(config.WIKI_DIR):
        return pages
    for fname in os.listdir(config.WIKI_DIR):
        if fname.startswith("_") or not fname.endswith(".md"):
            continue
        fpath = os.path.join(config.WIKI_DIR, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            pages[fname] = f.read()
    return pages


def title_to_filename(title: str, pages: dict[str, str]) -> str | None:
    """Find the filename for a given [[wikilink]] title."""
    t = title.lower().replace(" ", "-")
    for fname in pages:
        if fname.lower().replace(".md", "") == t:
            return fname
        if fname.lower().startswith(t):
            return fname
    return None


# ── Scoring ───────────────────────────────────────────────────────────────────

STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "shall", "must",
    "of", "in", "on", "at", "to", "for", "by", "with", "about",
    "from", "into", "through", "and", "or", "but", "not", "what",
    "how", "why", "when", "where", "who", "which", "that", "this",
    "it", "its", "i", "you", "we", "they", "he", "she",
}


def tokenise(text: str) -> list[str]:
    return [
        w.lower()
        for w in re.findall(r'\b\w+\b', text)
        if w.lower() not in STOP_WORDS and len(w) > 2
    ]


def score_pages(query: str, pages: dict[str, str]) -> list[tuple[str, float]]:
    """Keyword-overlap scoring. Returns pages sorted by descending score."""
    keywords = tokenise(query)
    scored = []
    for fname, content in pages.items():
        body_lower = content.lower()
        score = sum(
            len(re.findall(r'\b' + re.escape(kw) + r'\b', body_lower))
            for kw in keywords
        )
        fname_lower = fname.lower()
        title_boost = sum(2 for kw in keywords if kw in fname_lower)
        scored.append((fname, score + title_boost))

    scored.sort(key=lambda x: -x[1])
    return scored


def extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilink]] titles from a page."""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


# ── Search mode (no AI) ───────────────────────────────────────────────────────

def search_mode(query: str, pages: dict[str, str]):
    """
    Pure keyword search — no LLM required.
    Prints matching wiki pages with a short preview and their wikilinks.
    """
    scored = score_pages(query, pages)
    results = [(f, s) for f, s in scored if s > 0][:TOP_N]

    if not results:
        print(f"\n  No pages matched '{query}'.\n")
        return

    print(f"\n  Found {len(results)} matching pages for: '{query}'\n")
    print("=" * 60)

    for i, (fname, score) in enumerate(results, 1):
        content = pages[fname]
        page_title = fname.replace(".md", "").replace("-", " ").title()
        links = extract_wikilinks(content)

        print(f"\n[{i}] {page_title}  (score: {score})")
        print(f"    File: wiki/{fname}")

        # Extract summary line (first non-empty, non-heading line)
        summary = ""
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("[["):
                summary = line[:PREVIEW_CHARS]
                break
        if summary:
            print(f"    Preview: {summary}")

        if links:
            print(f"    Links to: {', '.join(f'[[{l}]]' for l in links[:8])}")
            if len(links) > 8:
                print(f"              ... and {len(links) - 8} more")

        # Print the file path so user can open it directly
        fpath = os.path.join(config.WIKI_DIR, fname)
        print(f"    Full path: {fpath}")

    print("\n" + "=" * 60)
    print("\n  Tip: Open these .md files in Obsidian (wiki/ folder) for full navigation.")
    print("  Tip: For an AI-synthesised answer, run without the --search flag.\n")


# ── AI query mode ─────────────────────────────────────────────────────────────

QUERY_SYSTEM = """You are a knowledgeable assistant for an organization's internal knowledge wiki.
You have been given a set of relevant wiki pages as context.

Your job:
1. Read the provided wiki pages carefully.
2. Answer the user's question as accurately and completely as possible.
3. Cite the wiki pages you used (by their filename) in your answer.
4. If any [[wikilinks]] in the context would materially improve your answer but
   were not provided, list them at the end under "FOLLOW_LINKS:" (one per line).
5. If the answer cannot be found in the provided pages, say so clearly.

Format your response in clear Markdown with headers where appropriate.
"""


def extract_follow_links(answer: str) -> tuple[str, list[str]]:
    """Split the AI answer into main text and any FOLLOW_LINKS it requested."""
    parts = re.split(r'FOLLOW_LINKS:\s*', answer, flags=re.IGNORECASE)
    if len(parts) == 1:
        return answer, []
    main_text = parts[0].strip()
    links = [
        re.sub(r'[\[\]]', '', line.strip()).strip()
        for line in parts[1].strip().splitlines()
        if line.strip()
    ]
    return main_text, links


def answer_question(query: str, pages: dict[str, str], observer=None) -> str:
    """Retrieve relevant pages and send query + context to Antigravity AI."""
    from src.llm_client import call_llm_query

    if not pages:
        return "[ERROR] No wiki pages found. Run generate_wiki.py first."

    # Stage 1: retrieve top-N pages
    scored = score_pages(query, pages)
    top_pages   = [fname for fname, score in scored[:TOP_N] if score > 0]
    top_scores  = [score for fname, score in scored[:TOP_N] if score > 0]
    if not top_pages:
        top_pages  = [fname for fname, _ in scored[:TOP_N]]
        top_scores = [0.0] * len(top_pages)

    used_pages = set(top_pages)
    context_parts = [f"### Wiki Page: {fname}\n{pages[fname]}" for fname in top_pages]
    context = "\n\n---\n\n".join(context_parts)
    user_prompt = f"Question: {query}\n\n---\n\n{context}"

    print(f"\n  [Retrieval] Top pages: {', '.join(top_pages)}")

    # ── SkillOpt observation (silent) ─────────────────────────────────────────
    # Score the retrieved pages' structural quality and record the trace.
    # No interruption; the user sees nothing extra here.
    if observer is not None:
        retrieved = [(fname, pages[fname]) for fname in top_pages]
        observer.observe(query, retrieved, top_scores)

    # Stage 2: send to Antigravity AI
    answer = call_llm_query(QUERY_SYSTEM, user_prompt, max_tokens=config.MAX_TOKENS_QUERY)

    # Stage 3: follow links (one hop) if the AI requested them
    main_answer, follow_links = extract_follow_links(answer)

    if follow_links and MAX_HOPS > 0:
        extra_pages = []
        for link_title in follow_links[:3]:
            fname = title_to_filename(link_title, pages)
            if fname and fname not in used_pages:
                extra_pages.append(fname)
                used_pages.add(fname)

        if extra_pages:
            print(f"  [Link hop] Following: {', '.join(extra_pages)}")
            extra_context = "\n\n---\n\n".join(
                f"### Wiki Page: {fn}\n{pages[fn]}" for fn in extra_pages
            )
            followup_prompt = (
                f"Question: {query}\n\n"
                f"Initial context:\n{context}\n\n"
                f"Additional pages you requested:\n{extra_context}\n\n"
                "Now provide a complete, final answer."
            )
            main_answer = call_llm_query(
                QUERY_SYSTEM,
                followup_prompt,
                max_tokens=config.MAX_TOKENS_QUERY,
            )

    return main_answer


def run_query(query: str, mode: str = "ai") -> dict:
    """
    Programmatic entry point for queries (used by Web UI and APIs).
    mode can be 'ai' (Azure LLM synthesis) or 'search' (keyword matching).
    """
    pages = load_wiki_pages()
    scored = score_pages(query, pages)
    top_results = []
    for fname, score in scored[:10]:
        if score > 0:
            content = pages.get(fname, "")
            summary = ""
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("[[") and not line.startswith("---") and not line.startswith("title:") and not line.startswith("aliases:"):
                    summary = line[:300]
                    break
            top_results.append({
                "filename": fname,
                "title": fname.replace(".md", ""),
                "score": float(score),
                "preview": summary,
                "wikilinks": extract_wikilinks(content)[:8]
            })

    if mode == "search":
        return {
            "query": query,
            "mode": "search",
            "results": top_results,
            "answer": None,
            "total_matches": len(top_results)
        }

    # AI Mode
    answer = answer_question(query, pages)
    main_answer, follow_links = extract_follow_links(answer)
    return {
        "query": query,
        "mode": "ai",
        "answer": main_answer,
        "follow_links": follow_links,
        "retrieved": top_results[:5],
        "total_matches": len(top_results)
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

BANNER = """
+===========================================================+
|   FutureSense Knowledge Wiki  --  Query Interface        |
|   Powered by Antigravity AI   |  No API keys required    |
+-----------------------------------------------------------+
|  Commands:                                                |
|    <question>          -> AI answers via Antigravity chat |
|    search: <keywords>  -> instant keyword search (no AI)  |
|    links: <page-name>  -> show links for a specific page  |
|    exit / quit         -> quit                            |
+===========================================================+
"""


def show_page_links(query: str, pages: dict[str, str]):
    """Show all wikilinks for pages matching a name."""
    q = query.lower().replace(" ", "-")
    found = False
    for fname, content in pages.items():
        if q in fname.lower():
            found = True
            links = extract_wikilinks(content)
            title = fname.replace(".md", "").replace("-", " ").title()
            print(f"\n  [{title}] links to:")
            for link in links:
                print(f"    -> [[{link}]]")
            if not links:
                print("    (no wikilinks found)")
    if not found:
        print(f"  No page found matching '{query}'")
    print()


def interactive_loop(
    pages: dict[str, str],
    search_only: bool = False,
    observer=None,
):
    print(BANNER)
    print(f"  Wiki: {len(pages)} pages loaded from {config.WIKI_DIR}")
    if observer is not None:
        print(f"  SkillOpt: ON  — skill will be refined at end of session "
              f"(triggers after {observer.n_trigger} queries).")
    print()

    if search_only:
        print("  Running in SEARCH MODE (keyword search only, no AI).\n")

    while True:
        try:
            prompt = "> " if not search_only else "> search: "
            query = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            _handle_session_end(observer)
            print("\n[Bye!]")
            break

        if not query:
            continue
        if query.lower() in ("exit", "quit", "q"):
            _handle_session_end(observer)
            print("[Bye!]")
            break

        # search: prefix → keyword search
        if query.lower().startswith("search:"):
            kw = query[7:].strip()
            search_mode(kw, pages)
            continue

        # links: prefix → show wikilinks for a page
        if query.lower().startswith("links:"):
            page_name = query[6:].strip()
            show_page_links(page_name, pages)
            continue

        if search_only:
            search_mode(query, pages)
            continue

        # AI query
        print("\n  [Sending to Antigravity AI...]\n")
        try:
            answer = answer_question(query, pages, observer=observer)
        except RuntimeError as e:
            print(f"\n[ERROR] {e}")
            print("  Tip: Use 'search: <keywords>' for keyword-only search.\n")
            continue

        print("\n" + "-" * 60)
        print(answer)
        print("-" * 60 + "\n")


def _handle_session_end(observer) -> None:
    """Called when the query session exits.  Triggers SkillOpt reflection if ready."""
    if observer is None:
        return
    observer.print_summary()
    if observer.has_evidence():
        try:
            observer.reflect_and_update()
        except Exception as e:
            print(f"  [SkillOpt] Reflection failed: {e}")
    else:
        print("  [SkillOpt] Not enough queries this session to trigger skill refinement.")
        remaining = observer.n_trigger - len(observer.traces)
        print(f"             (need {remaining} more)")


def run(query: str = None, search_only: bool = False, observer=None):
    pages = load_wiki_pages()
    if not pages:
        print("[ERROR] No wiki pages found in:", config.WIKI_DIR)
        print("        Run 'python main.py' to generate the wiki first.")
        return

    if query:
        # Single-shot mode
        if search_only:
            search_mode(query, pages)
        else:
            print(f"\n[Query] {query}\n")
            try:
                answer = answer_question(query, pages, observer=observer)
            except RuntimeError as e:
                print(f"[ERROR] {e}")
                return
            print("\n" + "-" * 60)
            print(answer)
            print("-" * 60 + "\n")
    else:
        interactive_loop(pages, search_only=search_only, observer=observer)


if __name__ == "__main__":
    args = sys.argv[1:]
    search_flag = "-s" in args or "--search" in args
    remaining = [a for a in args if a not in ("-s", "--search")]
    q = " ".join(remaining) if remaining else None
    run(q, search_only=search_flag)
