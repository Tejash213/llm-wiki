# FutureSense Knowledge Wiki (Karpathy Wiki)

An AI-powered, Obsidian-compatible Markdown wiki built from FutureSense documents using **GPT-4.1** via Azure OpenAI.

Every concept gets a page. Pages link to each other with `[[wikilinks]]`. You can query the knowledge base in natural language.

---

## Quick Start

### 1. Install dependencies

```powershell
cd C:\Users\TrevorSingaladevi\Downloads\llm-wiki
pip install -r requirements.txt
```

### 2. Run the full pipeline

```powershell
python main.py
```

This will:
- **Stage 1** — Read all 31 FutureSense documents (`.docx`, `.txt`, `.md`)
- **Stage 2+3** — Call GPT-4.1 to generate structured Markdown wiki pages
- **Stage 4** — Add `[[wikilinks]]` across all pages (knowledge graph)
- **Stage 7** — Drop into an interactive query session

Wiki pages are written to the `wiki/` folder inside this project.

---

## Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Full pipeline + interactive query |
| `python main.py --generate-only` | Only generate/update wiki pages (Stage 2+3) |
| `python main.py --crosslink-only` | Only run cross-linking (Stage 4) |
| `python main.py --query` | Interactive query session only |
| `python main.py --update "path/to/doc.docx"` | Add a new document (Stage 5) |
| `python src/ingest.py` | Test document ingestion |

---

## Pipeline Stages

| Stage | Script | Description |
|-------|--------|-------------|
| 1 | `src/ingest.py` | Extract text from `.docx`, `.txt`, `.md` |
| 2+3 | `src/generate_wiki.py` | GPT-4.1 generates structured wiki pages |
| 4 | `src/crosslink.py` | GPT-4.1 adds `[[wikilinks]]` across pages |
| 5 | `src/update.py` | Merge new documents into existing wiki |
| ~~6~~ | *(skipped)* | Optional vector index over wiki pages |
| 7 | `src/query.py` | Natural language query interface |

---

## Opening in Obsidian

1. Open **Obsidian**
2. Click **Open folder as vault**
3. Select: `C:\Users\TrevorSingaladevi\Downloads\llm-wiki\wiki`
4. Go to **Graph View** to see the interconnected knowledge graph

---

## Wiki Page Template

Each generated page uses this Obsidian-compatible template:

```markdown
---
title: AI Agents
type: concept
tags: []
last_updated: 2026-02-25
sources: []
---

## Summary
Brief description of the concept.

## Key Points
- Key claim or fact
- Another important point

## Related Concepts
[[Enterprise Transformation]], [[Multi-Agent Orchestration]], [[Brava Systems]]

## Source Documents
- AI Strategy for Department Heads 2026-03-25.docx
```

---

## Project Structure

```
llm-wiki/
├── main.py              ← Master runner
├── config.py            ← API keys, paths, model settings
├── requirements.txt
├── src/
│   ├── ingest.py        ← Stage 1: document text extraction
│   ├── llm_client.py    ← Shared Azure OpenAI helper
│   ├── generate_wiki.py ← Stage 2+3: initial wiki generation
│   ├── crosslink.py     ← Stage 4: cross-linking pass
│   ├── update.py        ← Stage 5: continuous update
│   └── query.py         ← Stage 7: query interface
└── wiki/                ← Generated wiki (open in Obsidian)
    ├── _index.md        ← Master table of contents
    ├── _processed.json  ← Tracks processed documents
    └── *.md             ← Generated wiki pages
```

---

## Configuration

Edit `config.py` to change:
- `DOCUMENTS_DIR` — path to source documents
- `WIKI_DIR` — where wiki pages are written
- `DOC_CHUNK_CHARS` — max characters sent to LLM per document (default: 12,000)
- `MAX_TOKENS_GENERATE` — GPT output limit for page generation (default: 4,096)
