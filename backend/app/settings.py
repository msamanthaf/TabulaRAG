from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    QDRANT_URL: str

    VIEWER_BASE_URL: str = "http://localhost:5173"

    EMBED_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBED_BATCH_SIZE: int = 64

    HIGHLIGHT_TTL_MINUTES: int = 30

    CORS_ORIGINS: str = "http://localhost:5173"

    @property
    def cors_list(self) -> list[str]:
        return [s.strip() for s in self.CORS_ORIGINS.split(",") if s.strip()]

settings = Settings()
