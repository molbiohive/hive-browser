"""Application configuration — loads from env vars and zerg_config.yaml."""

from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    url: str = "postgresql+asyncpg://zerg:zerg@localhost:5432/zerg"

    model_config = {"env_prefix": "DATABASE_"}


class LLMConfig(BaseSettings):
    base_url: str = "http://localhost:8000/v1"
    model: str = "Qwen/Qwen2.5-14B-Instruct"

    model_config = {"env_prefix": "LLM_"}


class BlastConfig(BaseSettings):
    db_path: str = "~/.zerg/blast"
    binary: str = "blastn"

    model_config = {"env_prefix": "BLAST_"}


class ChatConfig(BaseSettings):
    storage_dir: str = "~/.zerg/chats"

    model_config = {"env_prefix": "CHAT_"}


class WatcherRule(BaseSettings):
    match: str
    action: str  # 'parse' | 'ignore' | 'log'
    parser: str | None = None
    extract: list[str] = Field(default_factory=list)
    message: str | None = None


class WatcherConfig(BaseSettings):
    root: str = "/data/sequences"
    recursive: bool = True
    poll_interval: int = 5
    rules: list[WatcherRule] = Field(default_factory=list)


class ServerConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080


class Settings(BaseSettings):
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    blast: BlastConfig = Field(default_factory=BlastConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)

    model_config = {"env_prefix": "ZERG_"}


def load_config(config_path: str | None = None) -> Settings:
    """Load settings from YAML config file, with env var overrides."""
    if config_path is None:
        import os

        config_path = os.environ.get("ZERG_CONFIG", "zerg_config.yaml")

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f)
        return Settings(**data)

    return Settings()
