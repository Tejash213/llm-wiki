"""
Stage 1 — Document Ingestion
Reads .docx, .txt, and .md files from DOCUMENTS_DIR.
Returns a list of dicts: { filename, date, text }
"""

import os
import re
import sys

# Add project root to path so config is importable regardless of cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def extract_date_from_filename(filename: str) -> str:
    """
    Try to pull a date from the filename.
    Handles formats like:
      - '02-27 Briefing_...'         → '2026-02-27'
      - '2026-05-05 Customer...'     → '2026-05-05'
      - '2025-09-11.docx'            → '2025-09-11'
    Falls back to 'Unknown'.
    """
    # Full ISO date: 2026-02-25
    m = re.search(r'(20\d{2})[.\-_](\d{2})[.\-_](\d{2})', filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # MM-DD at start (assume 2026 year since that's the folder date)
    m = re.match(r'^(\d{2})-(\d{2})\s', filename)
    if m:
        return f"2026-{m.group(1)}-{m.group(2)}"

    return "Unknown"


def read_docx(filepath: str) -> str:
    """Extract plain text from a .docx file."""
    try:
        from docx import Document
        doc = Document(filepath)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception as e:
        print(f"  [WARN] Could not read {filepath}: {e}")
        return ""


def read_text(filepath: str) -> str:
    """Read a plain text or markdown file."""
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    return ""


def ingest_documents(documents_dir: str = None) -> list[dict]:
    """
    Walk DOCUMENTS_DIR and return a list of document records.
    Each record: { 'filename': str, 'date': str, 'text': str }
    """
    documents_dir = documents_dir or config.DOCUMENTS_DIR
    supported = {".docx", ".txt", ".md"}
    records = []

    if not os.path.isdir(documents_dir):
        print(f"[ERROR] Documents directory not found: {documents_dir}")
        return records

    files = sorted(os.listdir(documents_dir))
    print(f"[Stage 1] Found {len(files)} files in {documents_dir}")

    for fname in files:
        ext = os.path.splitext(fname)[1].lower()
        if ext not in supported:
            print(f"  [SKIP] {fname} (unsupported extension {ext})")
            continue

        filepath = os.path.join(documents_dir, fname)
        date = extract_date_from_filename(fname)

        if ext == ".docx":
            text = read_docx(filepath)
        else:
            text = read_text(filepath)

        if not text.strip():
            print(f"  [WARN] Empty text extracted from {fname}")
            continue

        records.append({
            "filename": fname,
            "date": date,
            "text": text,
        })
        print(f"  [OK]   {fname} ({date}) — {len(text):,} chars")

    print(f"[Stage 1] Ingested {len(records)} documents.\n")
    return records


if __name__ == "__main__":
    docs = ingest_documents()
    print(f"\nTotal documents ready: {len(docs)}")
