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


    # Below is the ensure_collection method of the VectorStore class, which checks if the specified collection exists in the Qdrant vector database and has the hybrid (dense + sparse) schema. If the collection does not exist, it creates a new collection with named dense and sparse vector configurations. If the collection exists but was created with the old dense-only schema, it is dropped and recreated — existing vectors are lost and documents must be re-embedded (the source chunks are still on disk, so this is recoverable). The method also sets up payload indexes for document_id, subject, chapter, and page to optimize filtered search queries.
    async def ensure_collection(self) -> None:
        if await self.client.collection_exists(self.collection):
            info = await self.client.get_collection(self.collection)
            sparse_cfg = info.config.params.sparse_vectors or {}
            if "sparse" in sparse_cfg:
                return  # already hybrid
            logger.warning(
                "Collection '%s' has the old dense-only schema; recreating as hybrid. "
                "Existing vectors are dropped — re-embed documents via POST /documents/{id}/embed.",
                self.collection)
            await self.client.delete_collection(self.collection)

        await self.client.create_collection(
            self.collection,
            vectors_config={"dense": models.VectorParams(size=self.dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for field, schema in (
            ("document_id", models.PayloadSchemaType.KEYWORD),
            ("subject", models.PayloadSchemaType.KEYWORD),
            ("chapter", models.PayloadSchemaType.KEYWORD),
            ("page", models.PayloadSchemaType.INTEGER),
        ):
            await self.client.create_payload_index(self.collection, field_name=field, field_schema=schema)
        logger.info("Created hybrid collection '%s' (dense+sparse)", self.collection)


    # The upsert method is responsible for inserting or updating chunks of text along with their corresponding dense and sparse vector embeddings into the Qdrant collection. It first deletes any existing points in the collection that are associated with the given document_id to ensure idempotency. Then, it iterates through the provided chunks and their corresponding vectors, creating a list of PointStruct objects that contain the chunk text, metadata, and both dense and sparse vector embeddings. Finally, it upserts these points into the collection, allowing for efficient storage and retrieval of the chunks based on their embeddings and metadata.
    async def upsert(self, document_id: str, chunks, dense_vectors, sparse_vectors) -> None:
        await self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(filter=self._doc_filter(document_id)),
        )
        points = []
        for chunk, dvec, svec in zip(chunks, dense_vectors, sparse_vectors):
            payload = {
                "text": chunk.text, "document_id": document_id, "chunk_id": chunk.chunk_id,
                **chunk.metadata.model_dump(mode="json"),
            }
            pid = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk.chunk_id))
            points.append(models.PointStruct(
                id=pid,
                vector={
                    "dense": dvec,
                    "sparse": models.SparseVector(indices=svec.indices, values=svec.values),
                },
                payload=payload,
            ))
        await self.client.upsert(self.collection, points=points)

    # The hybrid_search method performs a similarity search in the Qdrant collection based on both dense and sparse vector embeddings. It takes a dense vector, a sparse vector, and various optional filters to narrow down the search results. The method constructs a query filter based on the provided parameters and then calls the query_points method of the Qdrant client with a FusionQuery that combines the dense and sparse queries using the Reciprocal Rank Fusion (RRF) method. The results are returned as a list of points that match the query criteria, allowing for more comprehensive search results that leverage both types of embeddings.
    async def hybrid_search(self, dense_vec, sparse_vec, top_k, *,
                            subject=None, document_id=None, chapter=None, prefetch_limit=20):
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
            self.collection,
            prefetch=[
                models.Prefetch(query=dense_vec, using="dense", limit=prefetch_limit, filter=qfilter),
                models.Prefetch(
                    query=models.SparseVector(indices=sparse_vec.indices, values=sparse_vec.values),
                    using="sparse", limit=prefetch_limit, filter=qfilter),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k, with_payload=True,
        )
        return res.points

    # The _doc_filter method creates a filter for querying the Qdrant collection based on the document_id. This filter is used to select points in the collection that belong to a specific document, allowing for operations such as deletion or counting of points associated with that document.
    def _doc_filter(self, document_id: str) -> models.Filter:
        return models.Filter(must=[models.FieldCondition(
            key="document_id", match=models.MatchValue(value=document_id))])


    # The count method is responsible for counting the number of chunks associated with a specific document_id in the Qdrant collection. It uses the _doc_filter method to create a filter for querying the collection and then calls the count method on the Qdrant client to get the total number of points that match the filter.
    async def count(self, document_id: str) -> int:
        res = await self.client.count(self.collection, count_filter=self._doc_filter(document_id), exact=True)
        return res.count
