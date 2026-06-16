from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_model: str = Field(default="qwen2.5:3b")
    fast_model: str | None = Field(default=None)
    korean_model: str | None = Field(default=None)
    reasoning_model: str | None = Field(default=None)

    @property
    def ollama_openai_base_url(self) -> str:
        return f"{self.ollama_base_url.rstrip('/')}/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
