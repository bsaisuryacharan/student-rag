# Challenges Log

Problems identified during development and the solutions we landed on.

---

## Resolved Challenges

### C-001 · Exam "SET" label never retrieved
**Problem:** Asking "first question in Part B Set 1" confidently returned Set 2's
content. The set number printed in a circle (top-right of each exam page) was
never making it into the searchable text.

- **How identified:** User asked a Set-1 question, got Set-2 answer with high confidence.
  Inspected raw PyMuPDF output — no "SET - 1" string anywhere in extracted text.
- **Root cause:** `page.get_text("text")` follows PyMuPDF's internal column flow and
  silently drops any block outside the main text column — including the "SET - 1"
  drawn inside an oval. The label existed as a floating block but the flow reader skipped it.
- **Solution:** Replaced flow extraction with `_extract_page_text()` — a layout-aware
  extractor that (1) pulls tables via `find_tables()`, (2) collects *every* text block
  including floating ones, (3) sorts all parts by vertical position to preserve reading
  order. Generic fix: also handles multi-column layouts, sidebar notes, margin labels.
- **Commit / files:** `268821e` · `app/parsing/parsers.py`

### C-002 · Word-vs-numeral query mismatch
**Problem:** Users type "set one" / "page two" (words) but the document prints
"SET - 1" (numerals). BM25 treats these as different tokens, so word-form queries
missed the right page.

- **How identified:** Follow-on from C-001 — even after the label was extracted,
  word-form queries still ranked the wrong page.
- **Root cause:** BM25 is exact-token; "one" and "1" don't match.
- **Solution:** Every chunk is stamped with `[Page N (word)]` (e.g. `[Page 1 (one)]`)
  so both numeral and word queries hit via sparse search, regardless of where in the
  page the chunk's content sits.
- **Commit / files:** `b6e19b3` · `app/chunking/chunker.py`, `app/generation/service.py`
  (system prompt now tells the LLM to match the SET/page label and not mix sets).

### C-003 · Cross-page content bleed in chunker
**Problem:** Even after C-001/C-002, "Part B Set 1" still returned wrong content.
Set 1's tail questions were physically appearing inside the Set 2 chunk.

- **How identified:** Dumped the actual chunk text — chunk `:1` (labeled Page 2) began
  with Set 1's last Part-B questions, then continued into Set 2.
- **Root cause:** The chunker's token overlap copied the last N tokens of page 1 into
  the start of page 2's chunk. For multi-set exams, this contaminated set-specific
  retrieval — the Set 2 chunk out-ranked the Set 1 chunk for Set 1 queries.
- **Solution:** Refactored `chunk()` to group segments by page and chunk each page in
  isolation via `_chunk_page()`. Overlap is now confined within a single page — content
  never bleeds across page boundaries.
- **Commit / files:** `b2f55f5` · `app/chunking/chunker.py`

### C-004 · Reprocess silently failing on stale document_id
**Problem:** User ran `/parse`→`/chunk`→`/embed` repeatedly but answers never changed.
The reprocess commands used a document_id from a previous session.

- **How identified:** Listed `GET /v1/documents` — the live doc was `04bd61...`, but the
  user was reprocessing `efeb90...` (a stale id). Every reprocess returned "Document not
  found" silently, while `/ask` kept hitting the real doc with old embeddings.
- **Root cause:** document_id changes on every fresh upload; an old id was reused. The
  reprocess endpoints return 404 but it's easy to miss in a curl loop.
- **Solution (operational):** Always fetch the current id from `GET /v1/documents` before
  reprocessing — never reuse an id across sessions/uploads.
- **Open follow-up:** reprocess endpoints should fail loudly (see Future Problems).

### C-005 · Duplicate upload blocked re-processing
**Problem:** Re-uploading a fixed document returned HTTP 409 "already uploaded", and the
only delete was an admin-only wipe-everything endpoint.

- **How identified:** After a parser fix, re-upload was rejected by the filename/sha
  duplicate check; no way to remove a single document.
- **Root cause:** Duplicate guard by filename + no per-document delete endpoint.
- **Solution:** Added `DELETE /v1/documents/{id}` (users delete own docs, admins any) and
  `VectorStore.delete_document()` to drop just that doc's vectors. Also documented the
  in-place reprocess path (`/parse`→`/chunk`→`/embed`) for fixes that don't need re-upload.
- **Commit / files:** `7ec48bc` · `app/api/ingestion.py`, `app/store/qdrant_store.py`

### C-006 · Celery ↔ Upstash Redis (TLS) connection failures
**Problem:** Worker couldn't connect to Upstash `rediss://`, or hung at startup, or
rejected the result backend.

- **How identified:** Series of errors bringing the worker up against Upstash free tier.
- **Root cause(s) + fixes:**
  - `rediss://` needs `ssl_cert_reqs` — setting it as a URL query param is parsed
    inconsistently. Fix: set `broker_use_ssl`/`redis_backend_use_ssl` in code.
  - Upstash free tier supports only DB 0. Fix: result backend → `rpc://` +
    `task_ignore_result=True` (status lives in Qdrant anyway).
  - Worker hung at "mingle: searching for neighbors" (Upstash pub/sub limits).
    Fix: start worker with `--without-mingle --without-gossip`.
- **Commit / files:** `app/worker/celery_app.py`, `start_workers.sh`

### C-007 · Documents stuck forever at an intermediate status
**Problem:** A slow/oversized document could sit at `parsing`/`chunking` indefinitely
with no terminal state.

- **How identified:** Reviewing failure modes of the async pipeline.
- **Root cause:** No time limit + no failure marking on timeout.
- **Solution:** `task_soft_time_limit=1740s` raises `SoftTimeLimitExceeded` (caught to mark
  the doc `failed` with a message); `task_time_limit=1800s` hard-kills as a backstop.
- **Commit / files:** `app/worker/celery_app.py`, `app/worker/tasks.py`

### C-008 · Wrong embedding model in config
**Problem:** Startup crashed: `Model text-embedding-3-small is not supported`.

- **How identified:** App failed to start after env setup.
- **Root cause:** `.env` had `EMBEDDING_MODEL=text-embedding-3-small` (an OpenAI model name);
  fastembed only supports local models.
- **Solution:** `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5` (384-dim, local CPU).
- **Files:** `.env` (not committed)

---

## Future Problems

Problems we've identified and agreed are worth solving, but deferred for later.

### F-001 · Incremental indexing (partial document update)
**Problem:** Changing one page of a 100-page document currently requires re-parsing,
re-chunking, and re-embedding the entire document. There is no page-level granularity.

- **Concept:** Incremental / delta indexing — re-index only the changed pages.
- **Agreed approach (designed, not yet built):**
  1. Page-scoped chunk IDs (`{doc}:p{page}:{i}`) so Qdrant can target a single page.
  2. Store a per-page content hash on the document record.
  3. On re-upload, parse all pages, diff hashes; unchanged pages skip.
  4. For changed pages: delete those pages' vectors, re-chunk (page ± 1 for overlap),
     re-embed only those chunks.
  5. Update stored hashes.
- **Why deferred:** Larger feature; retrieval correctness was the priority first.

### F-002 · Reprocess endpoints fail loudly
**Problem:** `/parse`·`/chunk`·`/embed` return a quiet 404 on an unknown id (see C-004),
making it easy to "reprocess" nothing without noticing.
- **Idea:** Clearer error surfacing / confirmation in response; possibly a single
  `POST /v1/documents/{id}/reprocess` that validates the id first.

### F-003 · Production hardening (from roadmap)
Deferred operational items, in rough priority order:
- Multiple uvicorn workers (`--workers N` / gunicorn)
- Queue backpressure — HTTP 429 when queue depth exceeds a threshold
- Per-user rate limiting (max uploads/hour)
- `/health` endpoint — worker count + queue depth
- Retry with exponential backoff on transient OpenAI / Qdrant errors
- GPU embedding (50–100× over CPU fastembed)
- Horizontal Celery workers across machines (same Redis broker)
