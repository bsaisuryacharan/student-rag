# app/main.py
import logging
import uuid
from contextlib import asynccontextmanager # This is for creating an async context manager for the application lifespan, which allows us to set up and tear down resources like database connections and API clients in a clean and efficient way.

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware # This is for adding CORS middleware to the FastAPI application, which allows us to specify which origins are allowed to access our API. This is important for security and for enabling cross-origin requests from the frontend application.
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.logging_config import configure_logging, request_id_ctx
from app.clients import build_qdrant_client, build_openai_client
from app.api.routes import router as system_router

# add import near the others
from app.storage import QdrantStorage
from app.api.ingestion import router as documents_router

from app.store.qdrant_store import VectorStore
from app.embedding.sparse import SparseEncoder

from app.api.search import router as search_router

from app.api.ask import router as ask_router


logger = logging.getLogger("app")

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging("INFO" if settings.is_prod else "DEBUG")
    app.state.settings = settings
    app.state.qdrant = build_qdrant_client(settings)
    app.state.openai = build_openai_client(settings)
    app.state.vector_store = VectorStore(app.state.qdrant, settings)
    # Raw files and pipeline artifacts live in Qdrant Cloud too — nothing on local disk
    app.state.storage = QdrantStorage(app.state.qdrant, settings)
    await app.state.storage.ensure_collection()
    # Loaded once at startup: the BM25 model download/initialization is too slow to do per-request
    app.state.sparse_encoder = SparseEncoder(settings.sparse_model)
    logger.info("Startup complete (env=%s)", settings.environment)
    try:
        yield
    finally:
        await app.state.qdrant.close()
        await app.state.openai.close()
        logger.info("Shutdown complete")

# Below function create_app initializes the FastAPI application, sets up CORS middleware based on the environment, adds a middleware to handle request IDs for logging, and includes the API routes. It also defines a global exception handler to catch any unhandled exceptions and return a standardized error response. The application is configured to use the lifespan context manager for startup and shutdown tasks, ensuring that resources are properly managed throughout the application's lifecycle.
def create_app() -> FastAPI:
    settings = get_settings()                       # raises here if a secret is missing
    app = FastAPI(title="Notebook LLM Clone", version="0.1.0", lifespan=lifespan)

    origins = ["https://your-frontend.example"] if settings.is_prod else ["*"]
    app.add_middleware(
        CORSMiddleware, allow_origins=origins,
        allow_methods=["*"], allow_headers=["*"],
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(rid)
        resp = await call_next(request)
        resp.headers["X-Request-ID"] = rid
        return resp
    
    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(system_router, prefix="/v1")
    app.include_router(documents_router, prefix="/v1")
    app.include_router(search_router, prefix="/v1")
    app.include_router(ask_router, prefix="/v1")
    return app

app = create_app()
