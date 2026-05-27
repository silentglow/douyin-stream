from __future__ import annotations


def test_classify_error_treats_ssl_eof_token_get_as_network() -> None:
    from media_tools.transcribe.errors import ErrorType, classify_error

    err = RuntimeError("token-get failed: EOF occurred in violation of protocol (_ssl.c:1129)")
    assert classify_error(err) == ErrorType.NETWORK


def test_classify_error_keeps_token_invalid_as_auth() -> None:
    from media_tools.transcribe.errors import ErrorType, classify_error

    err = RuntimeError("invalid token: expired")
    assert classify_error(err) == ErrorType.AUTH
