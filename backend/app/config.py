from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLOUDPULSE_", hide_input_in_errors=True)
    database_url: str = "postgresql+psycopg://cloudpulse@localhost/cloudpulse"
    admin_token: SecretStr = Field(min_length=32)
    offline_seconds: int = Field(default=60, ge=10)
    retention_days: int = Field(default=30, ge=1)


@lru_cache
def settings() -> Settings:
    return Settings()
