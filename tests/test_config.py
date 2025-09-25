from pathlib import Path

from waverly.config import load_config, merge_fields, save_config, update_config


def test_load_config_creates_defaults(tmp_path):
    config_path = tmp_path / "config.json"
    config = load_config(config_path)
    assert config.fofa_fields
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

