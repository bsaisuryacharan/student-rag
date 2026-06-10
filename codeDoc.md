# Notebook LLM Clone — Production RAG System

A Retrieval-Augmented Generation (RAG) service that lets students upload study material
(PDFs, DOCX, TXT, images, scanned/handwritten notes) and ask questions that are answered
**strictly from their own documents, with citations**.

> **Scope of this document:** It reflects the codebase as built through the guided
> implementation (Steps 1–7) plus the hybrid-search upgrade. Any uncommitted local
> changes made outside that build are not reflected here.

---

## 1. Architecture at a glance

Two flows share one vector store:

**Ingestion (offline, per document)**

```
Upload → Parse (text layer / OCR vision) → Semantic chunk (+metadata)
       → Embed (dense + sparse) → Upsert into Qdrant
```

**Query (online, per question)**

```
Question → Embed (dense + sparse) → Hybrid search in Qdrant (RRF fusion)
         → Top-k chunks → LLM (grounded prompt) → Answer + citations
```

Each pipeline stage lives behind its own service/interface so implementations can be
swapped (e.g., parser backend, vector store) without touching callers.

---

## 2. Tech stack

| Concern | Choice |
|---|---|
| Language / runtime | Python 3.11+ |
| Web framework | FastAPI + Uvicorn (async) |
| Embeddings (dense) | OpenAI `text-embedding-3-small` (1536-dim, cosine) |
| Embeddings (sparse) | `fastembed` BM25 (`Qdrant/bm25`) |
| Vector store | Qdrant (named dense + sparse vectors, RRF hybrid) |
| Generation LLM | OpenAI `gpt-4o-mini` |
| Vision / OCR | OpenAI multimodal (`gpt-4o-mini` vision) for scans/handwriting |
| PDF parsing | PyMuPDF (`fitz`) |
| DOCX parsing | `python-docx` |
| Tokenization | `tiktoken` (`cl100k_base`) |
| Async file I/O | `aiofiles` |
| Config | `pydantic-settings` |

**Dependencies:** `fastapi`, `uvicorn[standard]`, `openai`, `qdrant-client`, `pydantic`,
`pydantic-settings`, `python-dotenv`, `aiofiles`, `pymupdf`, `pillow`, `python-docx`,
`tiktoken`, `fastembed`.

---

## 3. Project structure

```
notebook-rag/
├── app/
│   ├── main.py                 # app factory, lifespan (clients), middleware, routers
│   ├── config.py               # typed Settings (env-driven, fail-fast on secrets)
│   ├── logging_config.py       # structured logging + per-request id
│   ├── schemas.py              # all Pydantic models (the data contracts)
│   ├── clients.py              # AsyncOpenAI + AsyncQdrantClient factories
│   ├── errors.py               # typed ingestion errors
│   ├── storage.py              # Storage protocol + LocalStorage (streamed writes)
│   ├── ingestion/
│   │   └── service.py          # IngestionService: validate → store → manifest
│   ├── parsing/
│   │   ├── vision.py           # ocr_image(): multimodal OCR helper
│   │   ├── parsers.py          # parse_txt / parse_docx / parse_pdf / parse_image
│   │   └── service.py          # ParsingService: route by type, persist parsed.json
│   ├── chunking/
│   │   ├── chunker.py          # SemanticChunker (structure-aware, token-based)
│   │   └── service.py          # ChunkingService: parsed.json → chunks.json
│   ├── embedding/
│   │   ├── sparse.py           # SparseEncoder (BM25 via fastembed)
│   │   └── service.py          # EmbeddingService: dense+sparse → Qdrant upsert
│   ├── store/
│   │   └── qdrant_store.py     # VectorStore: collection, upsert, hybrid_search, count
│   ├── retrieval/
│   │   └── service.py          # RetrievalService: embed query → hybrid search
│   ├── generation/
│   │   └── service.py          # GenerationService: grounded answer + citations
│   └── api/
│       ├── routes.py           # /health, /ready
│       ├── ingestion.py        # /documents/* (upload, parse, chunk, embed, fetch)
│       ├── search.py           # /search
│       └── ask.py              # /ask
├── data/raw/<document_id>/     # per-document artifacts (see §7)
├── qdrant_storage/             # Qdrant Docker volume (persisted vectors)
├── .env                        # real secrets/overrides (git-ignored)
├── .env.example                # template (committed)
└── requirements.txt
```

All routers are mounted under the `/v1` prefix.

---

## 4. Configuration (`Settings`)

Loaded from environment / `.env`. Secrets have **no defaults** — the app refuses to start
if they're missing. Precedence: real env vars → `.env` → defaults below.

| Setting | Env var | Default | Notes |
|---|---|---|---|
| `environment` | `ENVIRONMENT` | `dev` | `dev` \| `prod` (controls CORS, log level) |
| `openai_api_key` | `OPENAI_API_KEY` | — (required) | fail-fast if absent |
| `qdrant_api_key` | `QDRANT_API_KEY` | `None` | leave blank for local |
| `qdrant_url` | `QDRANT_URL` | `http://localhost:6333` | |
| `collection_name` | `COLLECTION_NAME` | `study_chunks` | set to `study_chunks_hybrid` for hybrid |
| `embedding_model` | `EMBEDDING_MODEL` | `text-embedding-3-small` | |
| `generation_model` | `GENERATION_MODEL` | `gpt-4o-mini` | |
| `vision_model` | `VISION_MODEL` | `gpt-4o-mini` | OCR for scans/handwriting |
| `sparse_model` | `SPARSE_MODEL` | `Qdrant/bm25` | BM25 sparse encoder |
| `embedding_dim` | `EMBEDDING_DIM` | `1536` | must match the embedding model |
| `embed_batch_size` | `EMBED_BATCH_SIZE` | `100` | dense embedding batch |
| `chunk_target_tokens` | `CHUNK_TARGET_TOKENS` | `512` | semantic chunk size |
| `chunk_overlap_pct` | `CHUNK_OVERLAP_PCT` | `12` | ~10–15% overlap |
| `pdf_text_min_chars` | `PDF_TEXT_MIN_CHARS` | `20` | below this/page → OCR via vision |
| `data_dir` | `DATA_DIR` | `data` | raw storage root |
| `max_upload_mb` | `MAX_UPLOAD_MB` | `25` | upload size cap |
| `allowed_extensions` | — | pdf/docx/doc/txt/png/jpg/jpeg | upload allowlist |
| `retrieval_top_k` | `RETRIEVAL_TOP_K` | `5` | results returned |
| `retrieval_min_score` | `RETRIEVAL_MIN_SCORE` | `None` | dense-only cutoff (not used in hybrid) |
| `generation_temperature` | `GENERATION_TEMPERATURE` | `0.1` | low for faithful answers |
| `max_context_chars` | `MAX_CONTEXT_CHARS` | `16000` | prompt-size safety cap |

---

## 5. Data model (`schemas.py`)

| Model | Fields | Used for |
|---|---|---|
| `ChunkMetadata` | `document_name`, `subject?`, `chapter?`, `page?`, `upload_date` | per-chunk metadata |
| `Chunk` | `chunk_id`, `text`, `metadata: ChunkMetadata` | the unit threaded through the pipeline |
| `DocumentStatus` | enum: `uploaded`/`parsed`/`chunked`/`embedded`/`failed` | lifecycle state |
| `DocumentRecord` | `document_id`, `document_name`, `subject?`, `content_type?`, `size_bytes`, `sha256`, `storage_path`, `status`, `upload_date` | the per-document manifest |
| `UploadResponse` | `document_id`, `document_name`, `status`, `size_bytes` | upload result |
| `PageUnit` | `page`, `text`, `chapter_hint?` | one parsed page/block |
| `ParsedDocument` | `document_id`, `document_name`, `subject?`, `pages: [PageUnit]` | parser output |
| `ChunkedDocument` | `document_id`, `document_name`, `subject?`, `chunks: [Chunk]` | chunker output |
| `RetrievedChunk` | `chunk_id?`, `text`, `score`, `document_id?`, `document_name?`, `subject?`, `chapter?`, `page?` | a search hit |
| `SearchRequest` | `query`, `top_k?`, `subject?`, `document_id?`, `chapter?` | search input |
| `SearchResponse` | `query`, `results: [RetrievedChunk]` | search output |
| `AskRequest` | `question`, `top_k?`, `subject?`, `document_id?`, `chapter?` | ask input |
| `Citation` | `index`, `document_name?`, `page?`, `chapter?`, `document_id?`, `chunk_id?`, `score` | answer provenance |
| `AnswerResponse` | `question`, `answer`, `citations: [Citation]` | ask output |

---

## 6. API endpoints

All paths are prefixed with `/v1`. Interactive docs at `/docs`.

### System

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | **Liveness** — process is up; no external calls; instant. |
| GET | `/v1/ready` | **Readiness** — pings Qdrant + checks OpenAI key; `503` if a dependency is down. |

`/ready` body: `{"status": "ready"|"not_ready", "checks": {"openai_key": bool, "qdrant": bool}}`

### Documents (`/v1/documents`)

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| POST | `/v1/documents` | Upload a file (multipart: `file`, optional `subject`). Streams to disk, validates type/size, writes `manifest.json`. | `201` `UploadResponse` | `415` bad type, `413` too large |
| GET | `/v1/documents/{id}` | Fetch the document record/status. | `200` `DocumentRecord` | `404` |
| POST | `/v1/documents/{id}/parse` | Parse raw file → `parsed.json`; status → `parsed`. | `200` `{pages, chars}` | `404` |
| GET | `/v1/documents/{id}/parsed` | Fetch parsed pages. | `200` `ParsedDocument` | `404` |
| POST | `/v1/documents/{id}/chunk` | Chunk parsed text → `chunks.json`; status → `chunked`. | `200` `{chunks}` | `404`, `409` not parsed |
| GET | `/v1/documents/{id}/chunks` | Fetch chunks. | `200` `ChunkedDocument` | `404` |
| POST | `/v1/documents/{id}/embed` | Embed (dense+sparse) + upsert to Qdrant; status → `embedded`. | `200` `{chunks_embedded}` | `404`, `409` not chunked |
| GET | `/v1/documents/{id}/vector-count` | Count this document's points in Qdrant. | `200` `{vectors}` | — |

### Search & Ask

| Method | Path | Purpose | Body | Returns |
|---|---|---|---|---|
| POST | `/v1/search` | Hybrid retrieval only (no LLM). | `SearchRequest` | `SearchResponse` |
| POST | `/v1/ask` | Retrieve → grounded LLM answer with citations. | `AskRequest` | `AnswerResponse` |

**`/ask` behavior:** answers **only** from retrieved context; if the answer isn't present
it returns exactly `"I couldn't find that in your documents."`. Citations `[n]` in the
answer map to the `citations` array (document + page).

Example:

```bash
curl -X POST http://localhost:8000/v1/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the invoice date?"}'
```

```json
{
  "question": "What is the invoice date?",
  "answer": "The invoice date is 20/05/2026 [1].",
  "citations": [
    {"index": 1, "document_name": "Buds Invoice.pdf", "page": 1, "score": 0.5, "...": "..."}
  ]
}
```

---

## 7. Document lifecycle & on-disk layout

A document moves through statuses, each set by the corresponding endpoint:

```
uploaded ──parse──► parsed ──chunk──► chunked ──embed──► embedded
   │                                                        
   └────────────── (any stage error) ──────────► failed
```

Per-document artifacts live under `data/raw/<document_id>/`:

| File | Created by | Contents |
|---|---|---|
| `<original-filename>` | upload | the raw bytes (streamed) |
| `manifest.json` | upload / each stage | the `DocumentRecord` (status advances here) |
| `parsed.json` | parse | `ParsedDocument` (per-page text) |
| `chunks.json` | chunk | `ChunkedDocument` (the chunks) |

> The `manifest.json` is a stand-in for a metadata DB; vectors themselves live only in Qdrant.

---

## 8. Pipeline internals

**Parsing (`parsing/`).** Routes by extension: `.txt` → direct read; `.docx` →
`python-docx` (headings → chapter hints, tables flattened); `.pdf` → PyMuPDF per page —
if a page has a real text layer it's extracted directly, otherwise the page is rasterized
and sent to the vision model (`ocr_image`); `.png/.jpg` → vision model. Output is a list of
`PageUnit`s and status → `parsed`.

**Chunking (`chunking/chunker.py`).** `SemanticChunker` is structure-aware + token-based:
splits on headings/paragraphs (tracking `chapter`), packs segments up to
`chunk_target_tokens` (counted with `tiktoken`), hard-splits oversized segments, then
prepends `chunk_overlap_pct` worth of the previous chunk's tokens. Each chunk carries
`document_name`, `subject`, `chapter`, `page`, `chunk_id`, `upload_date`.

**Embedding (`embedding/`).** Dense vectors via OpenAI (batched), sparse BM25 vectors via
`fastembed`. Both are upserted per point.

**Storage / Qdrant (`store/qdrant_store.py`).** See §9.

**Retrieval (`retrieval/`).** Embeds the query (dense + sparse) and runs hybrid search.

**Generation (`generation/`).** Builds numbered, source-labeled context, calls the LLM with
a strict grounding system prompt, returns answer + citations.

---

## 9. Qdrant internals (how vectors are stored & searched)

**Point** = `{ id, vector, payload }` — the atomic record; one per chunk.
- `id`: deterministic `uuid5(NAMESPACE_URL, chunk_id)` → re-embedding overwrites cleanly.
- `vector`: **named** — `dense` (1536-dim, cosine) and `sparse` (BM25 with IDF modifier).
- `payload`: `text`, `document_id`, `chunk_id`, `document_name`, `subject`, `chapter`, `page`, `upload_date`.

**Collection** (`study_chunks_hybrid`): created once on first embed via `ensure_collection()`,
with the dense+sparse vector configs and **payload indexes** on `document_id`, `subject`,
`chapter`, `page` (these make filtered search fast — filtering is fused into the HNSW
traversal rather than applied after).

**Upsert** is idempotent per document: delete all points matching `document_id`, then insert.

**Hybrid search** (`hybrid_search`): two `Prefetch` branches (dense + sparse, each scoped by
the same payload filter) are fused server-side with **Reciprocal Rank Fusion (RRF)** via the
Query API, returning the top-k.

> **Score note:** under RRF the returned `score` is a fusion/rank score, **not** cosine
> similarity — don't compare it to dense-only cosine values, and `retrieval_min_score` is
> intentionally not applied to hybrid queries.

---

## 10. Running locally

```bash
# 1. Environment
python -m venv .venv && .venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. Qdrant (Docker)
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 \
  -v "${PWD}/qdrant_storage:/qdrant/storage" qdrant/qdrant
#    dashboard: http://localhost:6333/dashboard

# 3. .env (minimum)
#    OPENAI_API_KEY=sk-...
#    COLLECTION_NAME=study_chunks_hybrid

# 4. Run the API
uvicorn app.main:app --reload --port 8000
#    docs: http://localhost:8000/docs
```

**End-to-end smoke test:** upload a file → `/parse` → `/chunk` → `/embed` →
`/vector-count` (matches chunk count) → `/ask` a question about it (answer + citation).

---

## 11. Production hardening / roadmap (deferred)

These are intentionally not yet implemented:

- **Async pipeline:** parse/embed run synchronously in-request — move to a background
  worker/queue (arq/Celery/RQ); `/parse` & `/embed` return `202` + poll status.
- **Auto-chaining:** upload → parse → chunk → embed as one orchestrated flow.
- **Metadata DB:** replace `manifest.json` with Postgres for listing, status queries,
  and multi-tenant scoping.
- **Multi-tenancy:** per-student `owner_id` on payload + filter (isolation).
- **Dedup:** use the stored `sha256` to skip/replace duplicate uploads.
- **Reranking:** optional cross-encoder over top-k for precision.
- **Generation:** streaming (SSE) responses; cite only the `[n]` actually used; multi-turn chat.
- **Features:** summarization and concept-explanation endpoints (same retrieve-then-generate,
  different prompt).
- **Ops:** auth/quotas, rate limiting, `/metrics`, JSON logs in prod, retry/backoff,
  magic-byte content sniffing, concurrency for parse/embed batches, fusion tuning
  (prefetch limit, DBSF vs RRF).
```