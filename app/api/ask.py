# app/api/ask.py
from typing import Annotated
from fastapi import APIRouter, Depends, Request

from app.generation.service import GenerationService
from app.retrieval.service import RetrievalService
from app.schemas import AskRequest, AnswerResponse
from app.auth import get_current_user

router = APIRouter(tags=["ask"])

@router.post("/ask", response_model=AnswerResponse)
async def ask(request: Request, body: AskRequest,
              user: Annotated[dict, Depends(get_current_user)]):
    retrieval = RetrievalService(
        request.app.state.settings, request.app.state.dense_encoder,
        request.app.state.vector_store, request.app.state.sparse_encoder)
    service = GenerationService(request.app.state.settings, request.app.state.openai, retrieval)
    return await service.ask(
        body.question, body.top_k,
        user_id=user.get("sub"),
        subject=body.subject, document_id=body.document_id, chapter=body.chapter)
