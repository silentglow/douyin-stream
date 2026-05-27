from __future__ import annotations


def test_pipeline_default_concurrency_is_10(monkeypatch) -> None:
    from media_tools.core.config import load_pipeline_config

    monkeypatch.delenv("PIPELINE_CONCURRENCY", raising=False)
    cfg = load_pipeline_config()
    assert cfg.concurrency == 10
