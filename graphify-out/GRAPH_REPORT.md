# Graph Report - student-rag  (2026-06-17)

## Corpus Check
- 53 files · ~38,993 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 346 nodes · 757 edges · 27 communities (26 shown, 1 thin omitted)
- Extraction: 71% EXTRACTED · 29% INFERRED · 0% AMBIGUOUS · INFERRED: 218 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `461ba187`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]

## God Nodes (most connected - your core abstractions)
1. `Settings` - 59 edges
2. `IngestionService` - 28 edges
3. `ParsedDocument` - 23 edges
4. `VectorStore` - 23 edges
5. `DocumentStatus` - 22 edges
6. `IngestionService` - 19 edges
7. `Request` - 18 edges
8. `FileTooLargeError` - 18 edges
9. `QdrantStorage` - 18 edges
10. `SemanticChunker` - 16 edges

## Surprising Connections (you probably didn't know these)
- `student-rag` --semantically_similar_to--> `Student RAG PDF (Notebook LLM Clone design)`  [INFERRED] [semantically similar]
  README.md → data/raw/493d6ce36a7049248c336a8e231e508d/Student RAG.pdf
- `Notebook LLM Clone RAG System` --references--> `Student RAG PDF (Notebook LLM Clone design)`  [INFERRED]
  codeDoc.md → data/raw/493d6ce36a7049248c336a8e231e508d/Student RAG.pdf
- `Notebook LLM Clone RAG System` --conceptually_related_to--> `Computer Networks R20 Unit-1 Notes`  [INFERRED]
  codeDoc.md → data/raw/91bf135146544d70a56e8740265ac450/CN-R20-UNIT-1.pdf
- `Notebook LLM Clone RAG System` --conceptually_related_to--> `Harsha Vardhan Kondapalli Resume (ServiceNow Developer)`  [INFERRED]
  codeDoc.md → data/raw/42d6866f9cc24ec5aea3605244f3529c/harsha_servicenow_resume.pdf
- `POST /v1/ask (retrieve -> grounded answer)` --conceptually_related_to--> `Croma Tax Invoice (OnePlus Nord Buds 4 Pro)`  [INFERRED]
  codeDoc.md → data/raw/e4b95fc183104eeb99edf5ce891b9db7/Buds Invoice.pdf

## Import Cycles
- 1-file cycle: `app/main.py -> app/main.py`
- 1-file cycle: `app/chunking/chunker.py -> app/chunking/chunker.py`
- 2-file cycle: `app/chunking/chunker.py -> app/schemas.py -> app/chunking/chunker.py`

## Hyperedges (group relationships)
- **Ingestion pipeline: parse -> chunk -> embed -> upsert** — codedoc_parsing_service, codedoc_chunking_service, codedoc_embedding_service, codedoc_vector_store [EXTRACTED 0.95]
- **Query pipeline: retrieve (hybrid) -> generate grounded answer** — codedoc_retrieval_service, codedoc_hybrid_search, codedoc_generation_service, codedoc_generation_llm [EXTRACTED 0.95]
- **Uploaded RAG corpus (resume, student-rag, CN notes, invoice)** — resume_doc, studentrag_doc, cnr20_doc, budsinvoice_doc [INFERRED 0.80]

## Communities (27 total, 1 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (37): Croma Tax Invoice (OnePlus Nord Buds 4 Pro), Computer Networks R20 Unit-1 Notes, Network Types (LAN, MAN, WAN, PAN, VPN), Physical Layer & Transmission Media, OSI & TCP/IP Reference Models, Dense Embeddings (OpenAI text-embedding-3-small, 1536-dim cosine), EmbeddingService (dense+sparse -> Qdrant upsert), POST /v1/ask (retrieve -> grounded answer) (+29 more)

### Community 1 - "Community 1"
Cohesion: 0.14
Nodes (26): ParsedDocument, Settings, IngestionService, Settings, AsyncOpenAI, IngestionService, ParsedDocument, Settings (+18 more)

### Community 2 - "Community 2"
Cohesion: 0.15
Nodes (13): AsyncOpenAI, RetrievedChunk, Settings, RetrievedChunk, AsyncQdrantClient, Filter, Settings, SparseEncoder (+5 more)

### Community 3 - "Community 3"
Cohesion: 0.12
Nodes (28): chunk_document(), embed_document(), _file_chunks(), get_chunks(), get_document(), get_parsed(), list_documents(), parse_document() (+20 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (19): ready(), search(), Request, Request, build_openai_client(), build_qdrant_client(), AsyncOpenAI, AsyncQdrantClient (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.14
Nodes (18): AnswerResponse, ask(), Request, get_settings(), Settings, AsyncOpenAI, RetrievedChunk, Settings (+10 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (15): 10. Running locally, 11. Production hardening / roadmap (deferred), 1. Architecture at a glance, 2. Tech stack, 3. Project structure, 4. Configuration (`Settings`), 5. Data model (`schemas.py`), 6. API endpoints (+7 more)

### Community 7 - "Community 7"
Cohesion: 0.12
Nodes (15): 1\. Document Parsing, 2\. Document Chunking, 3\. Chunk Size & Overlap, 4\. Embedding Model Choice, 5\. Vector Store, 6\. Generation LLM, Clarifying Requirements, Future Enhancements (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.33
Nodes (6): ChunkingService (parsed.json -> chunks.json), POST /v1/documents/{id}/chunk, SemanticChunker (structure-aware, token-based), tiktoken (cl100k_base tokenizer), Rationale: ~512 tokens, 10-15% overlap, Rationale: semantic chunking preferred

### Community 9 - "Community 9"
Cohesion: 0.24
Nodes (4): AsyncQdrantClient, Filter, Settings, QdrantStorage

### Community 10 - "Community 10"
Cohesion: 0.50
Nodes (4): Document Lifecycle (uploaded->parsed->chunked->embedded), POST /v1/documents (upload), IngestionService (validate -> store -> manifest), manifest.json (metadata DB stand-in)

### Community 11 - "Community 11"
Cohesion: 0.50
Nodes (4): POST /v1/documents/{id}/parse, ParsingService (route by type, persist parsed.json), PyMuPDF (fitz) PDF parsing, Vision/OCR (gpt-4o-mini multimodal)

### Community 12 - "Community 12"
Cohesion: 0.36
Nodes (10): AsyncOpenAI, AsyncOpenAI, PageUnit, PageUnit, _normalize_image(), parse_docx(), parse_image(), parse_pdf() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.18
Nodes (10): content_type, document_id, document_name, page_count, sha256, size_bytes, status, storage_path (+2 more)

### Community 14 - "Community 14"
Cohesion: 0.18
Nodes (10): content_type, document_id, document_name, page_count, sha256, size_bytes, status, storage_path (+2 more)

### Community 15 - "Community 15"
Cohesion: 0.18
Nodes (10): content_type, document_id, document_name, page_count, sha256, size_bytes, status, storage_path (+2 more)

### Community 16 - "Community 16"
Cohesion: 0.18
Nodes (10): content_type, document_id, document_name, page_count, sha256, size_bytes, status, storage_path (+2 more)

### Community 17 - "Community 17"
Cohesion: 0.20
Nodes (9): content_type, document_id, document_name, sha256, size_bytes, status, storage_path, subject (+1 more)

## Knowledge Gaps
- **106 isolated node(s):** `Request`, `Response`, `LogRecord`, `AsyncOpenAI`, `document_id` (+101 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Community 5` to `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 9`?**
  _High betweenness centrality (0.123) - this node is a cross-community bridge._
- **Why does `QdrantStorage` connect `Community 9` to `Community 3`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `IngestionService` connect `Community 3` to `Community 1`, `Community 5`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 45 inferred relationships involving `Settings` (e.g. with `AnswerResponse` and `ParsedDocument`) actually correct?**
  _`Settings` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 7 inferred relationships involving `IngestionService` (e.g. with `Settings` and `DuplicateDocumentError`) actually correct?**
  _`IngestionService` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ParsedDocument` (e.g. with `Request` and `ParsedDocument`) actually correct?**
  _`ParsedDocument` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `VectorStore` (e.g. with `AsyncOpenAI` and `RetrievedChunk`) actually correct?**
  _`VectorStore` has 10 INFERRED edges - model-reasoned connections that need verification._