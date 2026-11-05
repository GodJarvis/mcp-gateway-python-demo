from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Enterprise MCP Gateway Demo"
    database_url: str = "sqlite:///./data/gateway.db"
    admin_api_key: str = "dev-admin-key"
    mcp_api_key: str = "dev-mcp-key"
    secret_encryption_key: str = "replace-with-a-long-random-secret"
    frontend_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = ["localhost:*", "127.0.0.1:*", "testserver:*"]
    mcp_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    allow_private_targets: bool = True
    log_level: str = "INFO"

    @field_validator("frontend_origins", "mcp_allowed_hosts", "mcp_allowed_origins", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

