# app/api/ask.py
from fastapi import APIRouter, Request

from app.generation.service import GenerationService
from app.retrieval.service import RetrievalService
from app.schemas import AskRequest, AnswerResponse

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AnswerResponse)
async def ask(request: Request, body: AskRequest):
    retrieval = RetrievalService(
        request.app.state.settings, request.app.state.openai,
        request.app.state.vector_store, request.app.state.sparse_encoder)
    service = GenerationService(request.app.state.settings, request.app.state.openai, retrieval)
    return await service.ask(
        body.question, body.top_k,
        subject=body.subject, document_id=body.document_id, chapter=body.chapter)