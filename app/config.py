# app/config.py
from functools import lru_cache # its for caching the settings object, so that it is not created multiple times
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Base settings class that will be used to load the environment variables from the .env file
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8",
        extra="ignore", case_sensitive=False,
    )

    environment: str = Field(default="dev")          # "dev" | "prod"

    # Secrets — no defaults, so a missing value fails at startup
    openai_api_key: str
    groq_api_key: str                                # used for vision OCR (free tier)
    qdrant_api_key: str | None = None                # optional for local Qdrant

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "study_chunks"
    docs_collection_name: str = "study_docs"   # payload-only collection for raw files + pipeline artifacts

    # Models
    # all-MiniLM-L6-v2 is 6 transformer layers vs bge-small's 12, so ~2x faster on CPU.
    # Same 384-dim output, so no Qdrant schema change. Slightly lower retrieval quality
    # than bge-small on benchmarks — acceptable tradeoff for the speed here.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    generation_model: str = "gpt-4o-mini"

    # Chunking tunables
    chunk_target_tokens: int = 2000
    chunk_overlap_pct: int = 50

    # Ingestion / storage
    max_upload_mb: int = 25
    allowed_extensions: set[str] = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"}

    # Parsing
    vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"  # Groq free-tier vision model
    pdf_text_min_chars: int = 20        # a page below this many chars is treated as scanned -> vision OCR
    vision_concurrency: int = 4         # max concurrent OCR calls for scanned PDF pages (bounded for rate limits)

     # Embeddings
    embedding_dim: int = 384       # 384-dim models (bge-small / all-MiniLM-L6-v2)
    embed_batch_size: int = 100
    embed_max_retries: int = 3          # per-batch retries on transient embed/vector-store errors
    embed_retry_base_delay: float = 0.5 # seconds; exponential backoff base (0.5, 1, 2, ...)

    # Retrieval
    retrieval_top_k: int = 5
    retrieval_min_score: float | None = None   # optional cosine cutoff to drop weak matches

    # Generation
    generation_temperature: float = 0.1
    max_context_chars: int = 16000      # safety cap on prompt size

    # Hybrid / sparse
    sparse_model: str = "Qdrant/bm25"
    hybrid_prefetch_limit: int = 20    # candidates fetched per branch (dense/sparse) before RRF fusion

    # Background worker
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Supabase auth
    supabase_url: str | None = None
    admin_emails: str = ""  # comma-separated emails that get admin role

    @property
    def is_prod(self) -> bool:
        return self.environment.lower() == "prod"
    

# The get_settings function is a helper function that creates an instance of the Settings class and caches it using the lru_cache decorator. This means that the settings will only be loaded once, and subsequent calls to get_settings will return the cached instance, improving performance and ensuring that we are using the same settings throughout the application.
@lru_cache
def get_settings() -> Settings:
    return Settings()          # parsed once, cached for the process