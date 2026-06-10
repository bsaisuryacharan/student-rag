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
    qdrant_api_key: str | None = None                # optional for local Qdrant

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "study_chunks"

    # Models
    embedding_model: str = "text-embedding-3-small"
    generation_model: str = "gpt-4o-mini"

    # Chunking tunables
    chunk_target_tokens: int = 512
    chunk_overlap_pct: int = 12

    # Ingestion / storage
    data_dir: str = "data"
    max_upload_mb: int = 25
    allowed_extensions: set[str] = {".pdf", ".docx", ".doc", ".txt", ".png", ".jpg", ".jpeg"}

    # Parsing
    vision_model: str = "gpt-4o-mini"   # multimodal model for scans/handwriting (use gpt-4o for tougher handwriting)
    pdf_text_min_chars: int = 20        # a page below this many chars is treated as scanned -> vision OCR

     # Embeddings
    embedding_dim: int = 1536      # text-embedding-3-small native size
    embed_batch_size: int = 100

    # Retrieval
    retrieval_top_k: int = 5
    retrieval_min_score: float | None = None   # optional cosine cutoff to drop weak matches

    # Generation
    generation_temperature: float = 0.1
    max_context_chars: int = 16000      # safety cap on prompt size

    # Hybrid / sparse
    sparse_model: str = "Qdrant/bm25"
    hybrid_prefetch_limit: int = 20    # candidates fetched per branch (dense/sparse) before RRF fusion

    @property
    def is_prod(self) -> bool:
        return self.environment.lower() == "prod"
    

# The get_settings function is a helper function that creates an instance of the Settings class and caches it using the lru_cache decorator. This means that the settings will only be loaded once, and subsequent calls to get_settings will return the cached instance, improving performance and ensuring that we are using the same settings throughout the application.
@lru_cache
def get_settings() -> Settings:
    return Settings()          # parsed once, cached for the process