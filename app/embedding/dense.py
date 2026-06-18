# app/embedding/dense.py
import logging

from fastembed import TextEmbedding

logger = logging.getLogger("app.dense")


class DenseEncoder:
    def __init__(self, model_name: str) -> None:
        logger.info("Loading dense model '%s' (first run downloads it)...", model_name)
        self.model = TextEmbedding(model_name=model_name)

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [e.tolist() for e in self.model.embed(texts)]

    def encode_one(self, text: str) -> list[float]:
        return self.encode([text])[0]
