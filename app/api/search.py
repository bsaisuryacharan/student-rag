# app/api/search.py
from typing import Annotated
from fastapi import APIRouter, Depends, Request

from app.retrieval.service import RetrievalService
from app.schemas import SearchRequest, SearchResponse
from app.auth import get_current_user

router = APIRouter(tags=["search"])

@router.post("/search", response_model=SearchResponse)
async def search(request: Request, body: SearchRequest,
                 user: Annotated[dict, Depends(get_current_user)]):
    service = RetrievalService(
        request.app.state.settings, request.app.state.dense_encoder,
        request.app.state.vector_store, request.app.state.sparse_encoder)
    results = await service.search(
        body.query, body.top_k,
        user_id=user.get("sub"),
        subject=body.subject, document_id=body.document_id, chapter=body.chapter)
    return SearchResponse(query=body.query, results=results)
