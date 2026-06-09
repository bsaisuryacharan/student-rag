# student-rag
Student RAG is a RAG pipeline build to enable students practise their studies with AI asisstant for Q&amp;A, summerization etc.
**Notebook LLM Clone**

_Date: 08/06/2026_

# Problem

Students face difficulty while preparing for exams. They may have PDFs, but those documents are often very long, making it difficult to revise quickly and understand concepts in a short amount of time.

The material is also scattered across many formats and files, there is no single place to ask questions across all of it, and a plain chatbot cannot answer from a student's own notes - so answers cannot be trusted or traced back to a source.

# Solution

Build a RAG (Retrieval-Augmented Generation) system where students can upload different types of study materials such as:

- PDFs
- Images
- Text files
- DOC files
- Other document formats

The AI model processes these files and provides answers / features such as:

- Summarization
- Question & Answer (Q&A)
- Concept Explanation
- Source references on every answer (document, chapter, page)
- _(Future add-on)_ Search the internet for additional information

Because every answer is **grounded in the retrieved passages** and cited, the tutor stays trustworthy and hallucinations are reduced.

# Clarifying Requirements

**1\. What does the Knowledge Base (KB) consist of?**

- PDFs
- DOC files
- Images

**2\. Does the data change over time?**

Answer: **No.**

**3\. Does the KB contain only text?**

Answer: **No** - it may contain:

- Text
- Diagrams
- Charts
- Images
- Tables
- etc.

**4\. How many pages? What is the expected growth?**

- 6 subjects
- Each subject has 2 PDFs
- Each PDF has around 100 pages
- More than 500 students

Estimated size: **6 × 2 × 100 = 1,200 pages per student**; across 500+ students that is **≈ 600,000 pages** of content total.

At roughly 1-1.5 chunks per page this is **≈ 0.6-1M vectors** at launch - design for steady growth beyond that.

**5\. Is metadata required?**

Answer: **Yes.** Metadata generated from uploaded documents should include:

- Page number
- Chapter
- etc.

**6\. Should the system support multiple languages?**

Answer: **No** - support only English for now.

**7\. Does the system need to respond in real time?**

Answer: **Not necessarily** - near-real-time is fine. A few seconds per answer is acceptable; ingestion can run in the background.

**8\. Do we need to address safety concerns, harmful outputs, or misleading outputs?**

Answer: **Not right now** - keep basic grounding/citation as the main guardrail; add stronger moderation later if the audience widens.

**9\. Where will it run? Any privacy constraints?**

Answer: **Cloud / hosted APIs are acceptable for now**. If notes must stay on-prem later, swap to open-source embedding and generation models and a self-hosted store.

# Technical Decisions

## 1\. Document Parsing

Use **AI-based document parsing**, because the documents contain complex structures such as:

- Tables
- Images
- Mixed layouts
- Other complex data

It should also OCR scanned / handwritten notes and preserve structure (headings, reading order), since cleaner parsing directly improves chunk and retrieval quality.

## 2\. Document Chunking

Chunking is very important because retrieval quality depends on it.

**Goal:** retrieve the most meaningful and relevant sections of a document.

Possible chunking methods:

- Fixed chunking
- Regular-expression-based chunking
- HTML-based chunking
- Semantic chunking **✓ (preferred)**

Semantic chunking reduces the need for manually writing parsing rules.

## 3\. Chunk Size & Overlap

Target: **~512 tokens per chunk with ~10-15% overlap.**

**Reason:** study notes need enough context to stand on their own without diluting relevance; a little overlap stops a concept being cut in half at a boundary. Tune up if answers feel fragmented, down if they feel unfocused.

## 4\. Embedding Model Choice

Recommended: **text-embedding-3-small.**

**Reason:** the content is general educational text, not a specialised legal/medical domain, so a larger, pricier model adds cost for little gain. "Small" gives the best balance of cost and performance, low storage, and fast indexing across ~1M vectors.

## 5\. Vector Store

Recommended: **Qdrant** (or **pgvector** if already using Postgres).

**Reason:** ~0.6-1M vectors and growing rule out a single-machine toy store, and we need heavy metadata filtering (student / subject / chapter / page). Qdrant is open-source, self-hosted, and scales; pgvector is the simpler pick when Postgres is already in the stack.

## 6\. Generation LLM

Recommended: **a cost-efficient model such as GPT-4o-mini.**

**Reason:** RAG already supplies the facts, so the model only needs faithful synthesis and citation, not heavy reasoning - a frontier model is overkill. With 500+ students the cost per answer dominates, and a small model is cheap, fast, and follows grounding instructions well. Keep a frontier model in reserve for occasional hard-reasoning queries.

# Suitable AI Approach

**Fine-tuning** **✗** **Not recommended**

- Responses are not highly domain-specific.
- Computationally expensive.
- Requires retraining whenever data changes.
- More maintenance overhead.
- Providing references / citations becomes difficult.
- Students cannot verify the original source easily.

**Prompt Engineering only** **✗** **Not sufficient**

- Relies only on the model's built-in knowledge.
- Cannot effectively use the uploaded documents.

**RAG (Retrieval-Augmented Generation)** **✓** **Recommended**

- Uses the uploaded study materials.
- Can provide document-grounded answers.
- Easier to maintain.
- Lower cost than fine-tuning.
- Can provide references to source documents.
- Reduces hallucination by grounding answers in real passages.
- Updates cheaply - re-index only the document that changed.

# Retrieval Strategy

**Keyword-based retrieval** **✗** **Not preferred**

**Knowledge-graph-based retrieval** **✗** **Not needed**

- No entity-relationship or hierarchical matching is required.

**Vector-based retrieval** **✓** **Recommended**

- Uses embeddings to find semantically similar content.
- Students phrase questions differently from their notes, so meaning-based matching beats exact keywords.

_(Future)_ a hybrid of vector + keyword search can be added later for better recall on exact terms.

# Reranking

Current decision: **not needed for now.**

Vector top-k is good enough at launch, and a reranker adds latency and cost. If irrelevant chunks start surfacing, add a cross-encoder later: retrieve the top-20, then rerank down to the best top-5.

# Future Enhancements

- Internet search to enrich answers beyond the uploaded notes
- Quiz and flashcard generation
- Mock interviews and personalised study plans
- Voice interaction
- Multi-language support
- Reranking and hybrid retrieval once precision/recall demand it

# Recommended Stack (Summary)

- **Approach:** RAG
- **Parsing:** AI-based, structure-preserving (with OCR)
- **Chunking:** Semantic, ~512 tokens, ~10-15% overlap
- **Embeddings:** text-embedding-3-small
- **Vector store:** Qdrant (or pgvector on Postgres)
- **Retrieval:** Vector (semantic) search
- **Generation LLM:** Cost-efficient, e.g. GPT-4o-mini
- **Reranking:** Deferred
- **Language:** English first
- **References:** On by default
