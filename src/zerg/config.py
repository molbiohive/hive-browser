"""Application configuration — loads from env vars and zerg_config.yaml."""

from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    url: str = "postgresql+asyncpg://zerg:zerg@localhost:5432/zerg"

    model_config = {"env_prefix": "DATABASE_"}


class LLMConfig(BaseSettings):
    provider: str = "ollama"  # ollama, anthropic, openai
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:7b"
    api_key: str | None = None  # required for cloud providers
    summary_token_limit: int = 1000  # max tokens for auto-summarize sent to LLM
    agent_max_turns: int = 5  # max tool-call turns in agentic loop

    model_config = {"env_prefix": "LLM_"}


class BlastConfig(BaseSettings):
    db_path: str = "~/.zerg/blast"
    binary: str = "blastn"

    model_config = {"env_prefix": "BLAST_"}


class SearchConfig(BaseSettings):
    columns: list[str] = ["name", "size_bp", "topology", "features"]

    model_config = {"env_prefix": "SEARCH_"}


class ChatConfig(BaseSettings):
    storage_dir: str = "~/.zerg/chats"
    max_history_pairs: int = 20
    auto_save_after: int = 2  # save chat after N user messages
    widget_data_threshold: int = 2048  # bytes — strip widget data above this size

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


class ToolsConfig(BaseSettings):
    directory: str = "~/.zerg/tools"

    model_config = {"env_prefix": "TOOLS_"}


class Settings(BaseSettings):
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    blast: BlastConfig = Field(default_factory=BlastConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    model_config = {"env_prefix": "ZERG_"}


def load_config(config_path: str | None = None) -> Settings:
    """Load settings from YAML config file, with env var overrides.

    Resolution order:
      1. Explicit ``config_path`` argument
      2. ``ZERG_CONFIG`` environment variable
      3. ``config/config.local.yaml`` (dev default)
    """
    import os

    if config_path is None:
        config_path = os.environ.get("ZERG_CONFIG", "config/config.local.yaml")

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f)
        return Settings(**data)

    return Settings()
