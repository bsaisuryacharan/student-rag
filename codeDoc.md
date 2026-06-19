# Notebook LLM Clone — Production RAG System

A **Retrieval-Augmented Generation** system for students: upload any PDF / DOCX / image,
then ask natural-language questions and get grounded, cited answers.

Built with FastAPI · Qdrant Cloud · fastembed · OpenAI · Celery · Upstash Redis · Supabase Auth.

---

## 1. Architecture at a glance

```
Upload Flow (offline / async)
──────────────────────────────────────────────────────────
  Client
    │  POST /v1/documents  (SSE stream)
    ▼
  FastAPI  ──► Celery task ──► [parse → chunk → embed]
                  │
                  ▼
            Upstash Redis (broker)   ← tasks survive restarts
                  │
                  ▼
            Celery Worker
              ├─ ParsingService    (PDF/DOCX/image → pages)
              ├─ ChunkingService   (pages → semantic chunks)
              └─ EmbeddingService  (chunks → Qdrant upsert)

Query Flow (online / sync)
──────────────────────────────────────────────────────────
  Client
    │  POST /v1/ask
    ▼
  FastAPI
    ├─ RetrievalService  (embed query → hybrid search → top-K chunks)
    └─ GenerationService (chunks + question → grounded answer + citations)
```

---

## 2. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Web framework | FastAPI + Uvicorn (async) | async I/O, SSE support, auto-docs |
| Vector store | Qdrant Cloud (hybrid collection) | dense + sparse, RRF fusion, free tier |
| Dense embeddings | fastembed `sentence-transformers/all-MiniLM-L6-v2` (384-dim) | local CPU, 6-layer → ~2x faster than bge-small |
| Sparse embeddings | fastembed `Qdrant/bm25` | keyword recall, free |
| Task queue | Celery + Upstash Redis | durable queue, survives restarts |
| LLM (generation) | OpenAI `gpt-4o-mini` | fast, cheap, grounded prompting |
| Vision / OCR | OpenAI `gpt-4o-mini` multimodal | scanned PDFs and images |
| PDF parsing | PyMuPDF (`fitz`) | fast native text extraction |
| Tokenizer | `tiktoken` cl100k_base | chunk size in tokens |
| Auth | Supabase JWT (ES256 JWKS) | per-user document isolation |

---

## 3. Project structure

```
student-rag/
├── app/
│   ├── api/
│   │   ├── ingestion.py     POST/GET/DELETE /v1/documents  (SSE upload)
│   │   ├── search.py        POST /v1/search
│   │   ├── ask.py           POST /v1/ask
│   │   └── routes.py        router registry
│   │
│   ├── chunking/
│   │   ├── chunker.py       SemanticChunker  (structure-aware, token-based)
│   │   └── service.py       ChunkingService
│   │
│   ├── embedding/
│   │   ├── dense.py         DenseEncoder  (fastembed TextEmbedding)
│   │   ├── sparse.py        SparseEncoder (fastembed BM25)
│   │   └── service.py       EmbeddingService  (upsert to Qdrant)
│   │
│   ├── generation/
│   │   └── service.py       GenerationService (grounded answer + citations)
│   │
│   ├── ingestion/
│   │   └── service.py       IngestionService (validate → store → record)
│   │
│   ├── parsing/
│   │   ├── parsers.py       PDF / DOCX / TXT / image parsers
│   │   ├── vision.py        GPT-4o-mini OCR for scanned pages
│   │   └── service.py       ParsingService (route by file type)
│   │
│   ├── retrieval/
│   │   └── service.py       RetrievalService (embed query → hybrid search)
│   │
│   ├── store/
│   │   └── qdrant_store.py  VectorStore (collection, upsert, hybrid_search)
│   │
│   ├── worker/
│   │   ├── celery_app.py    Celery app + Upstash Redis config
│   │   └── tasks.py         process_document task (parse→chunk→embed)
│   │
│   ├── auth.py              JWT verify (Bearer header + ?token= query param)
│   ├── clients.py           build_qdrant_client, build_openai_client
│   ├── config.py            Settings (pydantic-settings, all env vars)
│   ├── errors.py            IngestionError, FileTooLargeError, etc.
│   ├── logging_config.py    structured logging setup
│   ├── main.py              FastAPI app, lifespan, router mounts
│   ├── schemas.py           all shared data models
│   └── storage.py           QdrantStorage (document blob + record store)
│
├── scripts/
│   └── reset_data.py        admin: wipe all docs + recreate collections
│
├── test-docs/               sample PDFs for manual testing
├── load_test.py             concurrent upload load tester
├── start_workers.sh         start N Celery workers
├── requirements.txt
└── .env                     all secrets (never commit)
```

---

## 4. Configuration (`Settings`)

All config lives in `app/config.py` via `pydantic-settings`.
Values come from `.env` — missing required values fail at startup, not at runtime.

Key settings:

| Variable | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | — | required |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant Cloud URL in prod |
| `QDRANT_API_KEY` | — | optional for local Qdrant |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | set to Upstash `rediss://` URL |
| `SUPABASE_URL` | — | drives JWKS endpoint for auth |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | fastembed local model (384-dim) |
| `GENERATION_MODEL` | `gpt-4o-mini` | OpenAI chat model |
| `MAX_UPLOAD_MB` | `25` | file size cap |
| `CHUNK_TARGET_TOKENS` | `512` | target chunk size |
| `RETRIEVAL_TOP_K` | `5` | chunks returned per query |
| `ADMIN_EMAILS` | `""` | comma-separated, get admin role |

---

## 5. Data model (`schemas.py`)

```
DocumentRecord
  document_id    str          UUID
  document_name  str          original filename
  user_id        str | None   JWT sub — scopes all queries
  status         DocumentStatus  uploaded → parsed → chunked → embedded | failed
  error          str | None   set on failure

Chunk
  chunk_id       str
  document_id    str
  text           str
  metadata       ChunkMetadata  (page, subject, chapter…)

RetrievedChunk
  chunk_id, document_id, text, score, metadata

AnswerResponse
  answer         str
  citations      list[Citation]
  chunks_used    int
```

---

## 6. API endpoints

### System

| Method | Path | Description |
|---|---|---|
| GET | `/docs` | Swagger UI |
| GET | `/redoc` | ReDoc UI |

### Documents (`/v1/documents`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/documents` | user | Upload file → SSE stream (uploaded + embedded/failed) |
| GET | `/v1/documents` | user | List your documents |
| GET | `/v1/documents/{id}` | user | Get document record |
| GET | `/v1/documents/{id}/status-stream` | user | SSE stream of processing status |
| DELETE | `/v1/documents` | admin | Wipe all docs + recreate collections |

Upload SSE events:
```json
{"status": "uploaded", "document_id": "...", "stream_url": "...?token=..."}
{"status": "embedded"}   // or {"status": "failed", "error": "..."}
```

### Search & Ask

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/search` | user | Hybrid vector search, returns ranked chunks |
| POST | `/v1/ask` | user | Retrieve → generate grounded answer with citations |

`/v1/ask` request:
```json
{"query": "What is covered in Part A?", "top_k": 5}
```

`/v1/ask` response:
```json
{
  "answer": "Part A covers...",
  "citations": [{"chunk_id": "...", "document_name": "...", "page": 1}],
  "chunks_used": 3
}
```

---

## 7. Document lifecycle & on-disk layout

```
Status transitions:
  uploaded → parsed → chunked → embedded
                                     └── failed (at any step)
```

Documents are stored in **Qdrant Cloud** (not local disk):
- `study_docs` collection — document records + raw file blobs (payload store)
- `study_chunks_hybrid` collection — dense + sparse vectors per chunk

Each chunk payload in Qdrant contains:
```json
{
  "text": "...",
  "document_id": "...",
  "user_id": "...",
  "page": 1,
  "subject": "...",
  "chunk_index": 0
}
```

`user_id` is stored on every chunk so hybrid_search can filter strictly per user.

---

## 8. Pipeline internals

**Parsing** (`ParsingService`)
- PDF: PyMuPDF extracts text per page; pages below `pdf_text_min_chars` (20 chars) → GPT-4o-mini vision OCR
- DOCX: python-docx paragraph extraction
- TXT: direct read
- Images (PNG/JPG): GPT-4o-mini multimodal description

**Chunking** (`SemanticChunker`)
- Structure-aware: respects paragraph/heading boundaries
- Token-based: target `chunk_target_tokens` (512) with `chunk_overlap_pct` (12%) overlap
- Tokenizer: `tiktoken` cl100k_base

**Embedding** (`EmbeddingService`)
- Dense: `fastembed TextEmbedding` → 384-dim float vectors
- Sparse: `fastembed BM25` → sparse token weight vectors
- Both upserted together to `study_chunks_hybrid`

**Retrieval** (`RetrievalService`)
- Query embedded with same dense + sparse encoders
- `VectorStore.hybrid_search` runs both branches, fuses with **Reciprocal Rank Fusion (RRF)**
- Filtered by `user_id` — users never see each other's documents

**Generation** (`GenerationService`)
- Top-K chunks assembled into a context block (capped at `max_context_chars`)
- Grounded prompt: "Answer only from the context below; if not found, say so"
- Returns answer + chunk citations

---

## 9. Qdrant internals (how vectors are stored & searched)

Collection `study_chunks_hybrid` has two vector spaces:

```
dense:   384-dim float  (sentence-transformers/all-MiniLM-L6-v2, cosine)
sparse:  variable-dim   (BM25, IDF modifier)
```

**Hybrid Search with RRF:**
1. Dense ANN search → top `hybrid_prefetch_limit` (20) candidates
2. Sparse BM25 search → top `hybrid_prefetch_limit` (20) candidates
3. RRF fusion: `score = Σ 1 / (rank + 60)` — rank-based, not cosine
4. Top-K of merged results returned

RRF scores are rank-based (not cosine similarity), so `retrieval_min_score` is not applied to hybrid results.

---

## 10. Running locally

```bash
# 1. Clone and create venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Copy and fill in .env
cp .env.example .env   # add OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY, SUPABASE_URL

# 3. Start the API server
PYTHONPATH=. uvicorn app.main:app --reload --port 8000

# 4. Start a Celery worker (separate terminal)
PYTHONPATH=. celery -A app.worker.celery_app worker \
  --loglevel=info --concurrency=1 \
  --without-mingle --without-gossip

# 5. Open Swagger
open http://localhost:8000/docs
```

Admin reset (wipe all docs + recreate collections):
```bash
PYTHONPATH=. python scripts/reset_data.py --confirm
```

Load test (concurrent uploads):
```bash
python load_test.py --token <JWT> --docs 10 --concurrency 4 --dir test-docs/
```

---

## 11. Production hardening / roadmap (deferred)

| Item | Status | Notes |
|---|---|---|
| Redis broker (Upstash) | ✅ done | tasks survive restarts |
| Soft time limit (30 min) | ✅ done | `failed` status on timeout |
| Multiple uvicorn workers | pending | `--workers 4` or gunicorn |
| Queue backpressure | pending | HTTP 429 when queue > N |
| Per-user rate limiting | pending | max uploads/hour |
| Health endpoint | pending | `/health` → worker count + queue depth |
| Retry with backoff | pending | OpenAI + Qdrant transient errors |
| GPU embedding | future | 50–100× speedup over CPU fastembed |
| Horizontal Celery workers | future | multiple machines, same Redis |
