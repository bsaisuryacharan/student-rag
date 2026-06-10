# app/store/qdrant_store.py
import logging
import uuid

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings
from app.schemas import Chunk

logger = logging.getLogger("app.store")


class VectorStore:
    def __init__(self, client: AsyncQdrantClient, settings: Settings) -> None:
        self.client = client
        self.collection = settings.collection_name
        self.dim = settings.embedding_dim


    # The ensure_collection method is responsible for checking if the specified collection exists in the Qdrant vector database. If the collection does not exist, it creates a new collection with the appropriate configuration for storing vector embeddings. The method also sets up payload indexes for various fields such as document_id, subject, chapter, and page to optimize search queries based on these attributes. This ensures that the collection is properly configured to store and retrieve chunks of text along with their associated metadata efficiently.
    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            return
        await self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=self.dim, distance=models.Distance.COSINE),
        )
        for field, schema in (
            ("document_id", models.PayloadSchemaType.KEYWORD),
            ("subject", models.PayloadSchemaType.KEYWORD),
            ("chapter", models.PayloadSchemaType.KEYWORD),
            ("page", models.PayloadSchemaType.INTEGER),
        ):
            await self.client.create_payload_index(self.collection, field_name=field, field_schema=schema)
        logger.info("Created collection '%s' (dim=%d, cosine) with payload indexes", self.collection, self.dim)

    # The _doc_filter method creates a filter for querying the Qdrant collection based on the document_id. This filter is used to select points in the collection that belong to a specific document, allowing for operations such as deletion or counting of points associated with that document.
    def _doc_filter(self, document_id: str) -> models.Filter:
        return models.Filter(must=[models.FieldCondition(
            key="document_id", match=models.MatchValue(value=document_id))])
    

    # The upsert method is responsible for inserting or updating chunks of text along with their corresponding vector embeddings into the Qdrant collection. It first deletes any existing points in the collection that are associated with the given document_id to ensure idempotency. Then, it iterates through the provided chunks and their corresponding vectors, creating a list of PointStruct objects that contain the chunk text, metadata, and vector embedding. Finally, it upserts these points into the collection, allowing for efficient storage and retrieval of the chunks based on their embeddings and metadata.
    async def upsert(self, document_id: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        # idempotent re-embed: clear this document's existing points first
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=self._doc_filter(document_id)),
        )
        points = []
        for chunk, vec in zip(chunks, vectors):
            payload = {
                "text": chunk.text,
                "document_id": document_id,
                "chunk_id": chunk.chunk_id,
                **chunk.metadata.model_dump(mode="json"),   # document_name, subject, chapter, page, upload_date
            }
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id))  # deterministic -> overwrites on re-embed
            points.append(models.PointStruct(id=pid, vector=vec, payload=payload))
        await self.client.upsert(self.collection, points=points)

    # The count method is responsible for counting the number of chunks associated with a specific document_id in the Qdrant collection. It uses the _doc_filter method to create a filter for querying the collection and then calls the count method on the Qdrant client to get the total number of points that match the filter.
    async def count(self, document_id: str) -> int:
        res = await self.client.count(self.collection, count_filter=self._doc_filter(document_id), exact=True)
        return res.count
    

    # Below is the search method of the VectorStore class, which performs a similarity search in the Qdrant collection based on a given vector embedding. The method takes several optional parameters to filter the search results, such as subject, document_id, chapter, and score_threshold. It constructs a query filter based on the provided parameters and then calls the query_points method of the Qdrant client to retrieve the top_k most similar points that match the query vector and filter criteria. The method returns a list of ScoredPoint objects that contain the matching points along with their similarity scores and payloads for further processing or retrieval of relevant information.
    async def search(self, vector: list[float], top_k: int, *,
                     subject: str | None = None, document_id: str | None = None,
                     chapter: str | None = None, score_threshold: float | None = None):
        if not await self.client.collection_exists(self.collection):
            return []
        must = []
        if subject:
            must.append(models.FieldCondition(key="subject", match=models.MatchValue(value=subject)))
        if document_id:
            must.append(models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)))
        if chapter:
            must.append(models.FieldCondition(key="chapter", match=models.MatchValue(value=chapter)))
        qfilter = models.Filter(must=must) if must else None

        res = await self.client.query_points(
            self.collection, query=vector, limit=top_k,
            query_filter=qfilter, score_threshold=score_threshold, with_payload=True,
        )
        return res.points     # list[ScoredPoint] with .score and .payload