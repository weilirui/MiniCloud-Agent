"""Embedding client (OpenAI-compatible)."""

from __future__ import annotations

from openai import AsyncOpenAI

from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class EmbeddingClient:
    """Embedding generation via OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        dim: int | None = None,
    ):
        self.api_key = api_key or settings.embedding_api_key or settings.openai_api_key
        self.base_url = base_url or settings.embedding_base_url or settings.openai_base_url
        self.model = model or settings.embedding_model
        self.dim = dim or settings.embedding_dim
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def embed(self, text: str | list[str]) -> list[list[float]]:
        """Generate embeddings for one or more texts."""
        if isinstance(text, str):
            text = [text]
        if not text:
            return []

        try:
            resp = await self._client.embeddings.create(
                model=self.model,
                input=text,
            )
            return [d.embedding for d in resp.data]
        except Exception as e:
            logger.error("embedding_failed", error=str(e), model=self.model)
            raise

    async def embed_one(self, text: str) -> list[float]:
        """Convenience: embed a single string."""
        result = await self.embed([text])
        return result[0] if result else []


_embedding_client: EmbeddingClient | None = None


def get_embedding_client() -> EmbeddingClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client