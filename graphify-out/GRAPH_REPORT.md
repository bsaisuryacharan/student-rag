# Graph Report - .  (2026-06-15)

## Corpus Check
- Corpus is ~11,512 words - fits in a single context window. You may not need a graph.

## Summary
- 237 nodes · 438 edges · 12 communities detected
- Extraction: 62% EXTRACTED · 38% INFERRED · 0% AMBIGUOUS · INFERRED: 165 edges (avg confidence: 0.72)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Embeddings, Generation & Corpus|Embeddings, Generation & Corpus]]
- [[_COMMUNITY_Ask & Search API Layer|Ask & Search API Layer]]
- [[_COMMUNITY_Ingestion & Document Services|Ingestion & Document Services]]
- [[_COMMUNITY_Errors & Storage|Errors & Storage]]
- [[_COMMUNITY_Chunking & Sparse Encoding|Chunking & Sparse Encoding]]
- [[_COMMUNITY_App Config & Clients|App Config & Clients]]
- [[_COMMUNITY_Parsing & VisionOCR|Parsing & Vision/OCR]]
- [[_COMMUNITY_Logging & Vector Store|Logging & Vector Store]]
- [[_COMMUNITY_Chunking Strategy & Rationale|Chunking Strategy & Rationale]]
- [[_COMMUNITY_Health Check Routes|Health Check Routes]]
- [[_COMMUNITY_Document Lifecycle & Upload|Document Lifecycle & Upload]]
- [[_COMMUNITY_Parsing Pipeline|Parsing Pipeline]]

## God Nodes (most connected - your core abstractions)
1. `IngestionService` - 25 edges
2. `Settings` - 16 edges
3. `QdrantStorage` - 16 edges
4. `SemanticChunker` - 13 edges
5. `VectorStore` - 13 edges
6. `Storage` - 12 edges
7. `RetrievalService` - 12 edges
8. `ChunkingService` - 11 edges
9. `EmbeddingService` - 11 edges
10. `GenerationService` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Student RAG PDF (Notebook LLM Clone design)` --semantically_similar_to--> `Student RAG (design doc / problem statement)`  [INFERRED] [semantically similar]
  data/raw/493d6ce36a7049248c336a8e231e508d/Student RAG.pdf → README.md
- `Student RAG PDF (Notebook LLM Clone design)` --references--> `Notebook LLM Clone RAG System`  [INFERRED]
  data/raw/493d6ce36a7049248c336a8e231e508d/Student RAG.pdf → codeDoc.md
- `Harsha Vardhan Kondapalli Resume (ServiceNow Developer)` --conceptually_related_to--> `Notebook LLM Clone RAG System`  [INFERRED]
  data/raw/42d6866f9cc24ec5aea3605244f3529c/harsha_servicenow_resume.pdf → codeDoc.md
- `Computer Networks R20 Unit-1 Notes` --conceptually_related_to--> `Notebook LLM Clone RAG System`  [INFERRED]
  data/raw/91bf135146544d70a56e8740265ac450/CN-R20-UNIT-1.pdf → codeDoc.md
- `Croma Tax Invoice (OnePlus Nord Buds 4 Pro)` --conceptually_related_to--> `POST /v1/ask (retrieve -> grounded answer)`  [INFERRED]
  data/raw/e4b95fc183104eeb99edf5ce891b9db7/Buds Invoice.pdf → codeDoc.md

## Hyperedges (group relationships)
- **Ingestion pipeline: parse -> chunk -> embed -> upsert** — codedoc_parsing_service, codedoc_chunking_service, codedoc_embedding_service, codedoc_vector_store [EXTRACTED 0.95]
- **Query pipeline: retrieve (hybrid) -> generate grounded answer** — codedoc_retrieval_service, codedoc_hybrid_search, codedoc_generation_service, codedoc_generation_llm [EXTRACTED 0.95]
- **Uploaded RAG corpus (resume, student-rag, CN notes, invoice)** — resume_doc, studentrag_doc, cnr20_doc, budsinvoice_doc [INFERRED 0.80]

## Communities

### Community 0 - "Embeddings, Generation & Corpus"
Cohesion: 0.06
Nodes (37): Croma Tax Invoice (OnePlus Nord Buds 4 Pro), Computer Networks R20 Unit-1 Notes, Network Types (LAN, MAN, WAN, PAN, VPN), Physical Layer & Transmission Media, OSI & TCP/IP Reference Models, Dense Embeddings (OpenAI text-embedding-3-small, 1536-dim cosine), EmbeddingService (dense+sparse -> Qdrant upsert), POST /v1/ask (retrieve -> grounded answer) (+29 more)

### Community 1 - "Ask & Search API Layer"
Cohesion: 0.12
Nodes (19): ask(), BaseModel, Enum, AnswerResponse, AskRequest, Chunk, ChunkedDocument, ChunkMetadata (+11 more)

### Community 2 - "Ingestion & Document Services"
Cohesion: 0.13
Nodes (15): UnsupportedFileTypeError, chunk_document(), embed_document(), _file_chunks(), get_chunks(), get_document(), get_parsed(), list_documents() (+7 more)

### Community 3 - "Errors & Storage"
Cohesion: 0.11
Nodes (10): DuplicateDocumentError, FileTooLargeError, IngestionError, OcrNotAvailableError, Base for ingestion problems., Exception, Protocol, QdrantStorage (+2 more)

### Community 4 - "Chunking & Sparse Encoding"
Cohesion: 0.16
Nodes (5): _Segment, SemanticChunker, ChunkingService, SparseEncoder, SparseVec

### Community 5 - "App Config & Clients"
Cohesion: 0.17
Nodes (9): BaseSettings, build_openai_client(), build_qdrant_client(), get_settings(), is_prod(), Settings, create_app(), lifespan() (+1 more)

### Community 6 - "Parsing & Vision/OCR"
Cohesion: 0.23
Nodes (8): _normalize_image(), parse_docx(), parse_image(), parse_pdf(), parse_txt(), PageUnit, ParsingService, ocr_image()

### Community 7 - "Logging & Vector Store"
Cohesion: 0.17
Nodes (4): main(), configure_logging(), RequestIdFilter, VectorStore

### Community 8 - "Chunking Strategy & Rationale"
Cohesion: 0.33
Nodes (6): ChunkingService (parsed.json -> chunks.json), POST /v1/documents/{id}/chunk, SemanticChunker (structure-aware, token-based), tiktoken (cl100k_base tokenizer), Rationale: ~512 tokens, 10-15% overlap, Rationale: semantic chunking preferred

### Community 9 - "Health Check Routes"
Cohesion: 0.67
Nodes (2): health(), ready()

### Community 10 - "Document Lifecycle & Upload"
Cohesion: 0.5
Nodes (4): Document Lifecycle (uploaded->parsed->chunked->embedded), POST /v1/documents (upload), IngestionService (validate -> store -> manifest), manifest.json (metadata DB stand-in)

### Community 11 - "Parsing Pipeline"
Cohesion: 0.5
Nodes (4): POST /v1/documents/{id}/parse, ParsingService (route by type, persist parsed.json), PyMuPDF (fitz) PDF parsing, Vision/OCR (gpt-4o-mini multimodal)

## Knowledge Gaps
- **26 isolated node(s):** `Base for ingestion problems.`, `FastAPI + Uvicorn (async web framework)`, `Vision/OCR (gpt-4o-mini multimodal)`, `PyMuPDF (fitz) PDF parsing`, `tiktoken (cl100k_base tokenizer)` (+21 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Health Check Routes`** (4 nodes): `routes.py`, `routes.py`, `health()`, `ready()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `App Config & Clients` to `Ask & Search API Layer`, `Ingestion & Document Services`, `Errors & Storage`, `Chunking & Sparse Encoding`, `Parsing & Vision/OCR`, `Logging & Vector Store`?**
  _High betweenness centrality (0.130) - this node is a cross-community bridge._
- **Why does `IngestionService` connect `Ingestion & Document Services` to `Ask & Search API Layer`, `Errors & Storage`, `Chunking & Sparse Encoding`, `App Config & Clients`, `Parsing & Vision/OCR`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `RetrievalService` connect `Ask & Search API Layer` to `Chunking & Sparse Encoding`, `App Config & Clients`, `Logging & Vector Store`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `IngestionService` (e.g. with `ChunkingService` and `EmbeddingService`) actually correct?**
  _`IngestionService` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Settings` (e.g. with `StoredFile` and `Storage`) actually correct?**
  _`Settings` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `QdrantStorage` (e.g. with `Settings` and `FileTooLargeError`) actually correct?**
  _`QdrantStorage` has 4 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `SemanticChunker` (e.g. with `Settings` and `Chunk`) actually correct?**
  _`SemanticChunker` has 6 INFERRED edges - model-reasoned connections that need verification._