"""Application configuration — loads from env vars and hive_config.yaml."""

import os
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class DatabaseConfig(BaseSettings):
    url: str = "postgresql+asyncpg://hive:hive@localhost:5432/hive"

    model_config = {"env_prefix": "DATABASE_"}


class ModelEntry(BaseSettings):
    """A configured LLM model."""

    provider: str = "ollama"  # ollama, anthropic, openai
    model: str = "qwen2.5:7b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str | None = None  # required for cloud providers

    @property
    def id(self) -> str:
        return f"{self.provider}/{self.model}"


class LLMConfig(BaseSettings):
    models: list[ModelEntry] = Field(default_factory=lambda: [ModelEntry()])
    auto_discover: bool = False  # auto-discover Ollama models at runtime
    summary_token_limit: int = 1000  # max tokens for auto-summarize sent to LLM
    agent_max_turns: int = 5  # max tool-call turns in agentic loop
    pipe_min_length: int = 200  # auto-pipe strings longer than this between tools

    model_config = {"env_prefix": "LLM_"}


class BlastConfig(BaseSettings):
    binary: str = "blastn"


class SearchConfig(BaseSettings):
    columns: list[str] = ["name", "size_bp", "topology", "features"]


class ChatConfig(BaseSettings):
    max_history_pairs: int = 20
    auto_save_after: int = 2  # save chat after N user messages
    widget_data_threshold: int = 2048  # bytes — strip widget data above this size


class WatcherRule(BaseSettings):
    match: str
    action: str  # 'parse' | 'ignore' | 'log'
    parser: str | None = None
    extract: list[str] = Field(default_factory=list)
    message: str | None = None


class WatcherConfig(BaseSettings):
    root: str = "~/sequences"
    recursive: bool = True
    poll_interval: int = 5
    file_url_prefix: str | None = None  # e.g. "smb://labserver/sequences"
    rules: list[WatcherRule] = Field(default_factory=list)


class ServerConfig(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8080


class Settings(BaseSettings):
    data_root: str = "./data"
    server: ServerConfig = Field(default_factory=ServerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    blast: BlastConfig = Field(default_factory=BlastConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)

    model_config = {"env_prefix": "HIVE_"}

    @property
    def blast_dir(self) -> str:
        return str(Path(self.data_root).expanduser() / "blast")

    @property
    def chats_dir(self) -> str:
        return str(Path(self.data_root).expanduser() / "chats")

    @property
    def tools_dir(self) -> str:
        return str(Path(self.data_root).expanduser() / "tools")


def resolve_host_path(path: str) -> str:
    """Translate container path to host path for display in Docker.

    When HIVE_HOST_WATCHER_ROOT is set, replaces the container watcher root
    prefix with the original host path.  Outside Docker this is a no-op.
    """
    host_root = os.environ.get("HIVE_HOST_WATCHER_ROOT")
    if not host_root or not path:
        return path
    container_root = os.environ.get("HIVE_WATCHER_ROOT", "/watcher")
    if path.startswith(container_root):
        return host_root.rstrip("/") + path[len(container_root.rstrip("/")):]
    return path


def resolve_container_path(path: str) -> str:
    """Reverse-translate host path back to container path for file operations."""
    host_root = os.environ.get("HIVE_HOST_WATCHER_ROOT")
    if not host_root or not path:
        return path
    container_root = os.environ.get("HIVE_WATCHER_ROOT", "/watcher")
    host_root_stripped = host_root.rstrip("/")
    if path.startswith(host_root_stripped):
        return container_root.rstrip("/") + path[len(host_root_stripped):]
    return path


def file_open_mode() -> str:
    """Determine file-open strategy: 'local', 'link', or 'copy'."""
    if not os.environ.get("HIVE_HOST_WATCHER_ROOT"):
        return "local"
    return "link"  # fallback to 'copy' handled at runtime if no prefix


def load_config(config_path: str | None = None) -> Settings:
    """Load settings from YAML config file, with env var overrides.

    Resolution order:
      1. Explicit ``config_path`` argument
      2. ``HIVE_CONFIG`` environment variable
      3. ``config/config.local.yaml`` (dev default)
    """
    if config_path is None:
        config_path = os.environ.get("HIVE_CONFIG", "config/config.local.yaml")

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f)
        settings = Settings(**data)
    else:
        settings = Settings()

    # Docker env var overrides (container paths replace host paths)
    if db_url := os.environ.get("DATABASE_URL"):
        settings.database.url = db_url
    if data_root := os.environ.get("HIVE_DATA_ROOT"):
        settings.data_root = data_root
    if watcher_root := os.environ.get("HIVE_WATCHER_ROOT"):
        settings.watcher.root = watcher_root
    return settings
