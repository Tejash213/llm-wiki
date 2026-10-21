"""
app.py — Web UI and API Server for Karpathy Knowledge Wiki
Supports:
  - Drag-and-drop document ingestion (.docx, .pdf, .txt, .md)
  - Natural-language Q&A powered by Azure OpenAI (gpt-5-mini-2)
  - Fast keyword search and multi-hop link traversal
  - Interactive Wiki Explorer and live ingestion logs
"""

import os
import sys
import json
import time
import queue
import threading
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
from src.query import run_query, load_wiki_pages, extract_wikilinks
from src.update import update_document
from src.llm_client import _USE_AZURE, _AZURE_DEPLOYMENT, _AZURE_ENDPOINT

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

app = Flask(__name__, static_folder="static", static_url_path="")

# Ensure uploads directory exists
UPLOAD_DIR = os.path.join(PROJECT_ROOT, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Ingestion state tracking
_INGEST_STATE = {
    "status": "idle",       # idle | running | completed | error
    "current_file": None,
    "current_stage": None,
    "progress_pct": 0,
    "logs": [],
    "summary": None,
    "start_time": None,
    "end_time": None,
}
_STATE_LOCK = threading.Lock()


def _add_log(message: str, level: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = {"time": timestamp, "message": message, "level": level}
    with _STATE_LOCK:
        _INGEST_STATE["logs"].append(entry)
        # Keep latest 500 logs
        if len(_INGEST_STATE["logs"]) > 500:
            _INGEST_STATE["logs"].pop(0)


# ── Static UI Route ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Health & Stats API ────────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def get_stats():
    pages = load_wiki_pages()
    total_pages = len(pages)

    # Classify page types
    types_count = {"entity": 0, "concept": 0, "theme": 0, "other": 0}
    for fname, content in pages.items():
        if "type: entity" in content.lower():
            types_count["entity"] += 1
        elif "type: concept" in content.lower():
            types_count["concept"] += 1
        elif "type: theme" in content.lower():
            types_count["theme"] += 1
        else:
            types_count["other"] += 1

    # Load processed docs count
    processed_count = 0
    if os.path.isfile(config.PROCESSED_LOG):
        try:
            with open(config.PROCESSED_LOG, "r", encoding="utf-8") as f:
                processed_count = len(json.load(f))
        except Exception:
            pass

    return jsonify({
        "status": "online",
        "total_pages": total_pages,
        "processed_docs": processed_count,
        "page_types": types_count,
        "azure_active": _USE_AZURE,
        "azure_deployment": _AZURE_DEPLOYMENT,
        "azure_endpoint": _AZURE_ENDPOINT.split("/api")[0] if _AZURE_ENDPOINT else "",
        "wiki_dir": config.WIKI_DIR,
    })


# ── Query API ────────────────────────────────────────────────────────────────

@app.route("/api/query", methods=["POST"])
def query_api():
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("query") or "").strip()
    mode = data.get("mode", "ai")

    if not question:
        return jsonify({"error": "Query cannot be empty"}), 400

    start = time.time()
    try:
        result = run_query(question, mode=mode)
        result["latency_seconds"] = round(time.time() - start, 2)
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "error": str(e),
            "query": question,
            "mode": mode,
            "latency_seconds": round(time.time() - start, 2)
        }), 500


# ── Wiki Explorer API ────────────────────────────────────────────────────────

@app.route("/api/pages", methods=["GET"])
def list_pages():
    pages = load_wiki_pages()
    query = request.args.get("q", "").lower().strip()
    page_type_filter = request.args.get("type", "").lower().strip()

    items = []
    for fname, content in pages.items():
        title = fname.replace(".md", "")
        if query and (query not in title.lower() and query not in content.lower()):
            continue

        # Extract type
        ptype = "concept"
        if "type: entity" in content.lower():
            ptype = "entity"
        elif "type: theme" in content.lower():
            ptype = "theme"

        if page_type_filter and page_type_filter != "all" and ptype != page_type_filter:
            continue

        # First preview line
        preview = ""
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("---") and not line.startswith("title:") and not line.startswith("aliases:"):
                preview = line[:180]
                break

        links = extract_wikilinks(content)
        items.append({
            "filename": fname,
            "title": title,
            "type": ptype,
            "preview": preview,
            "links_count": len(links),
        })

    items.sort(key=lambda x: x["title"].lower())
    return jsonify({"total": len(items), "pages": items})


@app.route("/api/page/<path:filename>", methods=["GET"])
def get_page(filename):
    if not filename.endswith(".md"):
        filename += ".md"
    fpath = os.path.join(config.WIKI_DIR, filename)
    if not os.path.isfile(fpath):
        return jsonify({"error": f"Page not found: {filename}"}), 404

    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    links = extract_wikilinks(content)

    # Find backlinks (other pages linking to this one)
    title = filename.replace(".md", "")
    all_pages = load_wiki_pages()
    backlinks = []
    for other_fname, other_content in all_pages.items():
        if other_fname == filename:
            continue
        if f"[[{title}]]" in other_content or f"[[{title}|" in other_content:
            backlinks.append(other_fname.replace(".md", ""))

    return jsonify({
        "filename": filename,
        "title": title,
        "content": content,
        "wikilinks": links,
        "backlinks": backlinks[:20],
    })


# ── Drag & Drop Upload & Ingestion API ────────────────────────────────────────

def _run_ingest_worker(file_paths, force):
    global _INGEST_STATE
    total_files = len(file_paths)
    processed_files = []
    total_updated = []
    total_created = []

    with _STATE_LOCK:
        _INGEST_STATE["status"] = "running"
        _INGEST_STATE["progress_pct"] = 0
        _INGEST_STATE["start_time"] = datetime.now().isoformat()
        _INGEST_STATE["summary"] = None

    _add_log(f"Starting ingestion pipeline for {total_files} document(s)...", "stage")

    try:
        for idx, fpath in enumerate(file_paths):
            fname = os.path.basename(fpath)
            with _STATE_LOCK:
                _INGEST_STATE["current_file"] = fname
                _INGEST_STATE["progress_pct"] = int((idx / total_files) * 100)

            _add_log(f"Processing ({idx+1}/{total_files}): {fname}", "info")

            def callback_logger(msg, level="info"):
                _add_log(msg, level)

            res = update_document(fpath, force=force, callback=callback_logger)
            processed_files.append(res)
            if res.get("updated"):
                total_updated.extend(res["updated"])
            if res.get("created"):
                total_created.extend(res["created"])

        with _STATE_LOCK:
            _INGEST_STATE["status"] = "completed"
            _INGEST_STATE["progress_pct"] = 100
            _INGEST_STATE["current_file"] = None
            _INGEST_STATE["end_time"] = datetime.now().isoformat()
            _INGEST_STATE["summary"] = {
                "total_documents": total_files,
                "pages_updated": len(set(total_updated)),
                "pages_created": len(set(total_created)),
                "details": processed_files,
            }
        _add_log(
            f"Ingestion batch completed successfully! Updated: {len(set(total_updated))}, Created: {len(set(total_created))}",
            "success"
        )
    except Exception as e:
        with _STATE_LOCK:
            _INGEST_STATE["status"] = "error"
            _INGEST_STATE["current_file"] = None
        _add_log(f"Ingestion failed with error: {str(e)}", "error")


@app.route("/api/upload", methods=["POST"])
def upload_files():
    if "files" not in request.files:
        return jsonify({"error": "No files provided in request"}), 400

    uploaded = request.files.getlist("files")
    if not uploaded or uploaded[0].filename == "":
        return jsonify({"error": "No selected files"}), 400

    force = request.form.get("force", "false").lower() in ("true", "1", "yes")

    allowed_exts = {".docx", ".pdf", ".txt", ".md"}
    saved_paths = []

    for f in uploaded:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in allowed_exts:
            return jsonify({"error": f"File type '{ext}' not supported. Allowed: .docx, .pdf, .txt, .md"}), 400

        # Save to uploads dir
        safe_name = os.path.basename(f.filename)
        dest_path = os.path.join(UPLOAD_DIR, safe_name)
        f.save(dest_path)
        saved_paths.append(dest_path)

    # Check if pipeline already busy
    with _STATE_LOCK:
        if _INGEST_STATE["status"] == "running":
            return jsonify({"error": "An ingestion job is already running. Please wait for it to complete."}), 409

        _INGEST_STATE["logs"] = []

    # Launch ingestion in background thread
    t = threading.Thread(target=_run_ingest_worker, args=(saved_paths, force), daemon=True)
    t.start()

    return jsonify({
        "status": "started",
        "files_count": len(saved_paths),
        "files": [os.path.basename(p) for p in saved_paths],
        "message": "Ingestion job queued and running in background."
    })


@app.route("/api/ingest-status", methods=["GET"])
def ingest_status():
    with _STATE_LOCK:
        return jsonify(_INGEST_STATE)


@app.route("/api/ingest-clear", methods=["POST"])
def ingest_clear():
    with _STATE_LOCK:
        if _INGEST_STATE["status"] != "running":
            _INGEST_STATE["status"] = "idle"
            _INGEST_STATE["logs"] = []
            _INGEST_STATE["summary"] = None
            _INGEST_STATE["progress_pct"] = 0
    return jsonify({"status": "cleared"})


# ── SkillOpt Status API ──────────────────────────────────────────────────────

@app.route("/api/skillopt", methods=["GET"])
def skillopt_api():
    log_data = []
    if os.path.isfile(config.SKILLOPT_LOG):
        try:
            with open(config.SKILLOPT_LOG, "r", encoding="utf-8") as f:
                log_data = json.load(f)
        except Exception:
            pass

    skill_content = ""
    if os.path.isfile(config.SKILL_PATH):
        try:
            with open(config.SKILL_PATH, "r", encoding="utf-8") as f:
                skill_content = f.read()
        except Exception:
            pass

    return jsonify({
        "skill_path": config.SKILL_PATH,
        "has_skill": bool(skill_content),
        "skill_preview": skill_content[:1500] if skill_content else "No custom skill file generated yet.",
        "log_entries_count": len(log_data) if isinstance(log_data, list) else 0,
        "logs": log_data[-10:] if isinstance(log_data, list) else [],
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 65)
    print(f"[SERVER] Karpathy Wiki UI Server starting at: http://localhost:{port}")
    print(f"   Model Backend: {_AZURE_DEPLOYMENT} ({'ACTIVE' if _USE_AZURE else 'FALLBACK'})")
    print(f"   Wiki Directory: {config.WIKI_DIR}")
    print("=" * 65)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
