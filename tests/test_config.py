import json

import pytest

from waverly.config import (
    ENV_FOFA_EMAIL,
    ENV_FOFA_KEY,
    load_config,
    merge_fields,
    save_config,
    update_config,
)


def test_load_config_creates_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    assert config.fofa_fields
    assert "url" in config.fofa_fields
    assert config.templates_dir.exists()
    assert config.cache_dir.exists()
    assert config.config_path == config_path


def test_save_and_reload_config(tmp_path):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    config.fofa_email = "user@example.com"
    config.dnslog_server = "https://dnslog.local"
    save_config(config)

    loaded = load_config(config_path)
    assert loaded.fofa_email == "user@example.com"
    assert loaded.dnslog_server == "https://dnslog.local"


def test_merge_fields_preserves_order():
    merged = merge_fields(["host", "ip"], ["ip", "port", "title"])
    assert merged == ["host", "ip", "port", "title"]


def test_update_config_accepts_proxy_dict(tmp_path):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    update_config(config, proxy={"http": "http://127.0.0.1:8080"})
    assert config.proxy.http == "http://127.0.0.1:8080"


def test_load_config_backfills_url_field(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "fofa_fields": ["host", "ip"],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.fofa_fields[0] == "url"
    assert "host" in config.fofa_fields


@pytest.mark.parametrize(
    "env_var,value,attr",
    [
        (ENV_FOFA_EMAIL, "env@example.com", "fofa_email"),
        (ENV_FOFA_KEY, "env-key", "fofa_key"),
    ],
)
def test_env_prefills_missing_config(monkeypatch, tmp_path, env_var, value, attr):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    setattr(config, attr, "")
    save_config(config)

    monkeypatch.setenv(env_var, value)

    loaded = load_config(config_path)
    assert getattr(loaded, attr) == value

    monkeypatch.delenv(env_var, raising=False)


@pytest.mark.parametrize(
    "env_var,value,attr",
    [
        (ENV_FOFA_EMAIL, "env@example.com", "fofa_email"),
        (ENV_FOFA_KEY, "env-key", "fofa_key"),
    ],
)
def test_env_does_not_override_existing_value(monkeypatch, tmp_path, env_var, value, attr):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    setattr(config, attr, "file-value")
    save_config(config)

    monkeypatch.setenv(env_var, value)

    loaded = load_config(config_path)
    assert getattr(loaded, attr) == "file-value"

    monkeypatch.delenv(env_var, raising=False)

