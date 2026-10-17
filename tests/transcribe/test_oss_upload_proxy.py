"""OSS 上传代理绕过行为测试。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_token() -> dict:
    return {
        "sts": {
            "bucket": "test-bucket",
            "endpoint": "https://oss-cn-shanghai.aliyuncs.com",
            "fileKey": "test/key.mp4",
            "accessKeyId": "ak",
            "accessKeySecret": "sk",
            "securityToken": "token",
        }
    }


def _build_bucket(bypass: bool):
    from media_tools.transcribe.upload import oss_upload

    fake_bucket = MagicMock()
    fake_bucket.session.session.trust_env = "default"
    with (
        patch("media_tools.transcribe.upload.oss_upload.oss2") as mock_oss2,
        patch("media_tools.core.config.get_app_config") as mock_config,
    ):
        mock_config.return_value.qwen_oss_bypass_proxy = bypass
        mock_oss2.Bucket.return_value = fake_bucket
        result = oss_upload._build_oss2_bucket(_make_token())
    return result, mock_oss2


def test_bypass_proxy_disables_trust_env() -> None:
    bucket, mock_oss2 = _build_bucket(bypass=True)

    mock_oss2.Bucket.assert_called_once()
    _, kwargs = mock_oss2.Bucket.call_args
    assert kwargs["proxies"] == {}
    assert bucket.session.session.trust_env is False


def test_without_bypass_keeps_trust_env_default() -> None:
    bucket, mock_oss2 = _build_bucket(bypass=False)

    _, kwargs = mock_oss2.Bucket.call_args
    assert kwargs["proxies"] is None
    # 未绕过代理时不触碰 trust_env（保持 requests 默认行为）
    assert bucket.session.session.trust_env == "default"
