# app/embedding/sparse.py
import logging
from dataclasses import dataclass

from fastembed import SparseTextEmbedding

logger = logging.getLogger("app.sparse")


@dataclass
class SparseVec:
    indices: list[int]
    values: list[float]


class SparseEncoder:
    def __init__(self, model_name: str) -> None:
        logger.info("Loading sparse model '%s' (first run downloads it)...", model_name)
        self.model = SparseTextEmbedding(model_name=model_name)

    def encode(self, texts: list[str]) -> list[SparseVec]:
        return [SparseVec(indices=e.indices.tolist(), values=e.values.tolist())
                for e in self.model.embed(texts)]

    def encode_one(self, text: str) -> SparseVec:
        return self.encode([text])[0]