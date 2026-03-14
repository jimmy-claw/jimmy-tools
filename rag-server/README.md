# RAG Memory Server

Semantic search across memory files and repos using ChromaDB + nomic-embed-text on K11.

## Setup
```bash
pip install chromadb fastapi uvicorn requests
ollama pull nomic-embed-text
python3 rag-server.py  # port 8766
```

## Endpoints
- `GET /search?q=query&top_k=5&collection=all` — semantic search
- `GET /index?source=all` — re-index everything
- `GET /collections` — list collections
- `GET /health` — health check
