# app/api/search.py
from fastapi import APIRouter, Request

from app.retrieval.service import RetrievalService
from app.schemas import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])

# Endpoint to handle search queries. It receives a SearchRequest containing the query string and optional filters (subject, document_id, chapter). The endpoint uses the RetrievalService to perform a similarity search in the vector database based on the query embedding. The results are returned as a SearchResponse containing the original query and a list of RetrievedChunk objects that match the search criteria.
@router.post("/search", response_model=SearchResponse)
async def search(request: Request, body: SearchRequest):
    service = RetrievalService(
        request.app.state.settings, request.app.state.openai,
        request.app.state.vector_store, request.app.state.sparse_encoder)
    results = await service.search(
        body.query, body.top_k,
        subject=body.subject, document_id=body.document_id, chapter=body.chapter)
    return SearchResponse(query=body.query, results=results)