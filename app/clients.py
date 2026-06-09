# app/clients.py
from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from app.config import Settings

# Below function build_qdrant_client takes the application settings as input and returns an instance of AsyncQdrantClient configured with the URL and API key from the settings. This client will be used to interact with the Qdrant vector database for storing and retrieving document chunks. The timeout is set to 30 seconds to ensure that requests do not hang indefinitely. If the API key is not provided (e.g., when running a local instance of Qdrant), it will default to None, which is acceptable for local setups that do not require authentication.
def build_qdrant_client(settings: Settings) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )


# Below function build_openai_client takes the application settings as input and returns an instance of AsyncOpenAI configured with the API key from the settings. This client will be used to interact with the OpenAI API for generating embeddings and answers based on user queries. The timeout is set to 30 seconds, and the max_retries is set to 2 to handle transient errors gracefully without overwhelming the API with too many retries.
def build_openai_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.openai_api_key, timeout=30, max_retries=2)