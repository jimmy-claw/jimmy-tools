#!/usr/bin/env python3
"""Jimmy's RAG Memory Server - runs on K11, indexes repos + memory files"""

import os
import json
import hashlib
import requests
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import chromadb
import uvicorn

app = FastAPI(title="Jimmy RAG Memory")
OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
CHROMA_DIR = os.path.expanduser("~/.jimmy-rag")
CHUNK_SIZE = 500  # chars per chunk
CHUNK_OVERLAP = 100

# Initialize ChromaDB
client = chromadb.PersistentClient(path=CHROMA_DIR)

def get_or_create_collection(name):
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"}
    )

def get_embedding(text):
    """Get embedding from ollama"""
    r = requests.post(f"{OLLAMA_URL}/api/embed", json={
        "model": EMBED_MODEL,
        "input": text
    })
    data = r.json()
    return data.get("embeddings", [data.get("embedding", [])])[0]

def chunk_text(text, path="", chunk_size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    """Split text into overlapping chunks"""
    chunks = []
    lines = text.split("\n")
    current = ""
    line_num = 1
    chunk_start = 1
    
    for i, line in enumerate(lines, 1):
        if len(current) + len(line) > chunk_size and current:
            chunks.append({
                "text": current.strip(),
                "path": path,
                "line_start": chunk_start,
                "line_end": i - 1
            })
            # Overlap: keep last few lines
            overlap_lines = current.split("\n")[-3:]
            current = "\n".join(overlap_lines) + "\n"
            chunk_start = max(1, i - len(overlap_lines))
        current += line + "\n"
    
    if current.strip():
        chunks.append({
            "text": current.strip(),
            "path": path,
            "line_start": chunk_start,
            "line_end": len(lines)
        })
    return chunks

def index_file(collection, filepath, prefix=""):
    """Index a single file into the collection"""
    try:
        with open(filepath, "r", errors="ignore") as f:
            content = f.read()
    except:
        return 0
    
    if not content.strip() or len(content) < 20:
        return 0
    
    rel_path = prefix + str(filepath) if not prefix else prefix
    chunks = chunk_text(content, path=rel_path)
    
    if not chunks:
        return 0
    
    ids = []
    documents = []
    metadatas = []
    embeddings = []
    
    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{rel_path}:{i}:{chunk['text'][:50]}".encode()).hexdigest()
        ids.append(chunk_id)
        documents.append(chunk["text"])
        metadatas.append({
            "path": chunk["path"],
            "line_start": chunk["line_start"],
            "line_end": chunk["line_end"]
        })
        embeddings.append(get_embedding(chunk["text"]))
    
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return len(chunks)

def index_directory(collection, dirpath, extensions=None, prefix=""):
    """Recursively index a directory"""
    if extensions is None:
        extensions = {".md", ".rs", ".cpp", ".h", ".qml", ".py", ".toml", ".yaml", ".yml", ".json", ".txt"}
    
    total = 0
    dirpath = Path(dirpath)
    if not dirpath.exists():
        return 0
    
    for filepath in sorted(dirpath.rglob("*")):
        if filepath.is_file() and filepath.suffix in extensions:
            # Skip large files, build artifacts, .git
            if any(skip in str(filepath) for skip in [".git/", "target/", "node_modules/", "build/", "__pycache__"]):
                continue
            if filepath.stat().st_size > 100000:  # skip files > 100KB
                continue
            rel = str(filepath.relative_to(dirpath))
            n = index_file(collection, filepath, prefix=f"{prefix}{rel}")
            if n > 0:
                print(f"  Indexed {rel}: {n} chunks")
                total += n
    return total

@app.get("/search")
def search(
    q: str = Query(..., description="Search query"),
    top_k: int = Query(5, description="Number of results"),
    collection: str = Query("all", description="Collection to search: all, memory, repos")
):
    """Semantic search across indexed content"""
    embedding = get_embedding(q)
    
    collections_to_search = []
    if collection == "all":
        collections_to_search = [c.name for c in client.list_collections()]
    else:
        collections_to_search = [collection]
    
    results = []
    for col_name in collections_to_search:
        try:
            col = client.get_collection(col_name)
            r = col.query(query_embeddings=[embedding], n_results=min(top_k, col.count() or 1))
            if r and r["documents"]:
                for i, doc in enumerate(r["documents"][0]):
                    results.append({
                        "text": doc,
                        "path": r["metadatas"][0][i].get("path", ""),
                        "line_start": r["metadatas"][0][i].get("line_start", 0),
                        "line_end": r["metadatas"][0][i].get("line_end", 0),
                        "distance": r["distances"][0][i] if r.get("distances") else 0,
                        "collection": col_name
                    })
        except Exception as e:
            print(f"Error searching {col_name}: {e}")
    
    # Sort by distance (lower = more similar for cosine)
    results.sort(key=lambda x: x["distance"])
    return {"query": q, "results": results[:top_k]}

@app.get("/index")
def trigger_index(source: str = Query("all", description="What to index: all, memory, repos")):
    """Trigger re-indexing"""
    stats = {}
    
    if source in ("all", "memory"):
        print("Indexing memory files...")
        col = get_or_create_collection("memory")
        # Memory files on Pi5 workspace (mounted or synced)
        n = index_directory(col, "/home/jimmy/workspace/memory", prefix="memory/")
        n += index_file(col, "/home/jimmy/workspace/MEMORY.md", prefix="MEMORY.md")
        n += index_file(col, "/home/jimmy/workspace/TOOLS.md", prefix="TOOLS.md")
        n += index_file(col, "/home/jimmy/workspace/USER.md", prefix="USER.md")
        stats["memory"] = n
    
    if source in ("all", "repos"):
        print("Indexing repos...")
        repos = {
            "scala": "/home/jimmy/scala",
            "lmao": "/home/jimmy/lmao",
            "spel": "/home/jimmy/spel",
            "spelbook": "/home/jimmy/spelbook",
            "music-escrow": "/home/jimmy/music-escrow",
            "dev-skills": "/home/jimmy/dev-skills",
            "logos-chess": "/home/jimmy/logos-chess",
            "logos-timer": "/home/jimmy/logos-timer",
            "logos-notes": "/home/jimmy/logos-notes",
            "logos-contacts": "/home/jimmy/logos-contacts",
            "lssa": "/home/jimmy/lssa",
            "logos-workspace": "/home/jimmy/logos-workspace",
            "logos-roadmap": "/home/jimmy/workspace/logos-roadmap",
        }
        for name, path in repos.items():
            if Path(path).exists():
                print(f"Indexing {name}...")
                col = get_or_create_collection(f"repo-{name}")
                n = index_directory(col, path, prefix=f"{name}/")
                stats[name] = n
    
    return {"indexed": stats}

@app.get("/collections")
def list_collections():
    """List all collections and their sizes"""
    return {
        "collections": [
            {"name": c.name, "count": c.count()}
            for c in client.list_collections()
        ]
    }

@app.get("/health")
def health():
    return {"status": "ok", "collections": len(client.list_collections())}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8766)
