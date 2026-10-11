from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-insecure-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | production
    database_url: str = "sqlite:///./codehunt.db"
    cors_origins: str = "http://localhost:5173"
    trust_proxy: bool = False  # read client IP from X-Forwarded-For (set true on Render)

    # Secrets. Production refuses to start while any of these is a default.
    secret_key: str = DEV_SECRET  # signs login tokens
    answer_pepper: str = DEV_SECRET  # keys the answer hashes; changing it invalidates stored answers
    admin_username: str = "admin"
    admin_password: str = DEV_SECRET
    token_hours: int = 12

    # Chat model: none | openai_compatible | anthropic
    ai_provider: str = "none"
    ai_base_url: str = ""
    ai_api_key: str = ""
    ai_model: str = ""
    ai_max_tokens: int = 4000

    # Embeddings: hash (local, free) | openai_compatible
    embedding_provider: str = "hash"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dim: int = 384

    rag_top_k: int = 4
    rag_min_score: float = 0.12

    # Abuse and cost limits
    login_per_minute: int = 10
    register_per_minute: int = 5
    submit_per_minute: int = 8
    chat_per_minute: int = 6
    chat_daily_limit: int = 80  # per team; caps AI spend

    auto_seed: bool = True  # seed placeholder content when the database is empty

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @property
    def is_postgres(self) -> bool:
        return self.sqlalchemy_url.startswith("postgresql")

    def insecure_defaults(self) -> list[str]:
        names = ("secret_key", "answer_pepper", "admin_password")
        return [n.upper() for n in names if getattr(self, n) == DEV_SECRET]


@lru_cache
def get_settings() -> Settings:
    return Settings()
