from life_dashboard import config


def test_shared_connections_file_is_found(tmp_path, monkeypatch):
    shared = tmp_path / "connections.toml"
    shared.write_text('timezone = "UTC"\n[[connectors]]\ntype = "sample_tasks"\nname = "T"\n')
    monkeypatch.chdir(tmp_path / "..")
    monkeypatch.delenv("LIFE_DASHBOARD_CONFIG", raising=False)
    monkeypatch.setattr(config, "PROJECT_DIR", tmp_path / "nowhere")
    monkeypatch.setattr(config, "SHARED_CONNECTIONS", shared)
    cfg = config.load_config()
    assert cfg.source_file == shared.resolve()
    assert [c["type"] for c in cfg.connectors] == ["sample_tasks"]


def test_vault_path_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path / "vault"))
    monkeypatch.setattr(config, "find_config", lambda path=None: None)
    assert config.load_config().vault_path == tmp_path / "vault"
