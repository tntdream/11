from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .constants import FOFA_MAX_PAGE_SIZE, FOFA_MIN_PAGE_SIZE

CONFIG_DIR = Path.home() / ".waverly"
CONFIG_FILE = CONFIG_DIR / "config.json"

ENV_FOFA_EMAIL = "WAVERLY_FOFA_EMAIL"
ENV_FOFA_KEY = "WAVERLY_FOFA_KEY"


def _ensure_directory(path: Path) -> None:
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)


def _normalize_proxy(value: Optional[str]) -> Optional[str]:
    if value:
        stripped = value.strip()
        return stripped or None
    return None


@dataclass
class ProxySettings:
    """User proxy configuration for different protocols."""

    http: Optional[str] = None
    https: Optional[str] = None
    socks5: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            "http": self.http,
            "https": self.https,
            "socks5": self.socks5,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Optional[str]]) -> "ProxySettings":
        return cls(
            http=_normalize_proxy(data.get("http")),
            https=_normalize_proxy(data.get("https")),
            socks5=_normalize_proxy(data.get("socks5")),
        )


@dataclass
class UserConfig:
    """Application persistent configuration."""

    fofa_email: str = ""
    fofa_key: str = ""
    fofa_fields: list[str] = field(
        default_factory=lambda: ["host", "ip", "port", "title", "server", "banner"]
    )
    default_query_size: int = 100
    dnslog_server: str = ""
    dnslog_token: str = ""
    nuclei_binary: str = "nuclei"
    nuclei_rate_limit: int = 50
    nuclei_concurrency: int = 25
    request_timeout: float = 30.0
    verify_ssl: bool = True
    proxy: ProxySettings = field(default_factory=ProxySettings)
    templates_dir: Path = field(default_factory=lambda: CONFIG_DIR / "templates")
    cache_dir: Path = field(default_factory=lambda: CONFIG_DIR / "cache")
    config_path: Path = field(default_factory=lambda: CONFIG_FILE)

    def __post_init__(self) -> None:
        self.default_query_size = max(
            FOFA_MIN_PAGE_SIZE, min(self.default_query_size, FOFA_MAX_PAGE_SIZE)
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Convert Path objects to string for JSON serialization
        data["templates_dir"] = str(self.templates_dir)
        data["cache_dir"] = str(self.cache_dir)
        data["config_path"] = str(self.config_path)
        data["proxy"] = self.proxy.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserConfig":
        proxy_dict = data.get("proxy", {})
        config = cls(
            fofa_email=data.get("fofa_email", ""),
            fofa_key=data.get("fofa_key", ""),
            fofa_fields=list(data.get("fofa_fields", [])) or cls().fofa_fields,
            default_query_size=int(data.get("default_query_size", 100)),
            dnslog_server=data.get("dnslog_server", ""),
            dnslog_token=data.get("dnslog_token", ""),
            nuclei_binary=data.get("nuclei_binary", "nuclei"),
            nuclei_rate_limit=int(data.get("nuclei_rate_limit", 50)),
            nuclei_concurrency=int(data.get("nuclei_concurrency", 25)),
            request_timeout=float(data.get("request_timeout", 30.0)),
            verify_ssl=bool(data.get("verify_ssl", True)),
            proxy=ProxySettings.from_dict(proxy_dict),
            templates_dir=Path(data.get("templates_dir", CONFIG_DIR / "templates")),
            cache_dir=Path(data.get("cache_dir", CONFIG_DIR / "cache")),
            config_path=Path(data.get("config_path", CONFIG_FILE)),
        )
        return config


def load_config(path: Optional[Path] = None) -> UserConfig:
    """Load configuration from disk."""

    config_path = path or CONFIG_FILE
    _ensure_directory(config_path.parent)
    if not config_path.exists():
        config = UserConfig(config_path=config_path)
        ensure_runtime_directories(config)
        return apply_env_overrides(config)

    with config_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    config = UserConfig.from_dict(data)
    if path is not None:
        config.config_path = path
    ensure_runtime_directories(config)
    return apply_env_overrides(config)


def save_config(config: UserConfig, path: Optional[Path] = None) -> None:
    """Persist configuration to disk."""

    config_path = path or config.config_path
    _ensure_directory(config_path.parent)
    ensure_runtime_directories(config)
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)


def update_config(config: UserConfig, **updates: Any) -> UserConfig:
    """Return a new config with provided attributes updated."""

    for key, value in updates.items():
        if not hasattr(config, key):
            raise AttributeError(f"Unknown configuration option: {key}")
        if key == "proxy" and isinstance(value, dict):
            value = ProxySettings.from_dict(value)
        setattr(config, key, value)
    ensure_runtime_directories(config)
    return config


def ensure_runtime_directories(config: UserConfig) -> None:
    """Ensure directories referenced in the configuration exist."""

    _ensure_directory(config.templates_dir)
    _ensure_directory(config.cache_dir)


def merge_fields(current_fields: Iterable[str], new_fields: Iterable[str]) -> list[str]:
    """Merge two field lists while preserving order and uniqueness."""

    seen = set()
    merged: list[str] = []
    for field_name in list(current_fields) + list(new_fields):
        if field_name and field_name not in seen:
            merged.append(field_name)
            seen.add(field_name)
    return merged


def apply_env_overrides(config: UserConfig) -> UserConfig:
    """Update configuration using environment variables when present."""

    email = os.getenv(ENV_FOFA_EMAIL)
    if email:
        config.fofa_email = email

    key = os.getenv(ENV_FOFA_KEY)
    if key:
        config.fofa_key = key

    return config

