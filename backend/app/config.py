"""Application settings (pydantic-settings)."""

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All config from .env / environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== LLM =====
    openai_api_key: str = Field(..., description="OpenAI-compatible API key")
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536

    # ===== PostgreSQL =====
    postgres_user: str = "minicloud"
    postgres_password: str = "minicloud"
    postgres_db: str = "minicloud"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ===== Qdrant =====
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "minicloud_kb"

    # ===== RAG retrieval =====
    # Hybrid = dense (Qdrant) + lexical (BM25) fusion, then MMR re-ranking.
    # Turn this off to fall back to the original dense-only pipeline.
    rag_hybrid_enabled: bool = True
    rag_hybrid_fusion: str = "weighted"  # "weighted" | "rrf"
    rag_vector_weight: float = 0.7
    rag_lexical_weight: float = 0.3
    rag_mmr_enabled: bool = True
    rag_mmr_lambda: float = 0.7
    # Safety cap for the in-memory BM25 index rebuilt from Qdrant.
    rag_lexical_max_chunks: int = 20000

    # ===== Skills =====
    skills_builtin_dir: str = "/app/app/skills/builtin"
    skills_user_dir: str = "/app/data/skills"

    # ===== MCP =====
    mcp_servers_file: str = "/app/mcp.servers.json"

    # ===== App =====
    app_port: int = 8000
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @field_validator("cors_origins")
    @classmethod
    def split_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ===== Context =====
    max_context_tokens: int = 8000
    max_agent_iterations: int = 10
    summary_model: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()