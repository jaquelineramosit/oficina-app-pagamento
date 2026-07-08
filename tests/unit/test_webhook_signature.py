import hashlib
import hmac

import pytest

from src.domain.exceptions import WebhookSignatureError
from src.infrastructure.security.webhook_signature import validate_webhook_signature

SECRET = "my-secret"


def _build_signature_header(data_id, request_id, ts, secret):
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


def test_valid_signature_passes():
    header = _build_signature_header("ordtst01", "req-123", "1700000000", SECRET)
    # Não deve lançar exceção
    validate_webhook_signature(header, "req-123", "ordtst01", SECRET)


def test_invalid_signature_raises():
    header = _build_signature_header("ordtst01", "req-123", "1700000000", SECRET)
    with pytest.raises(WebhookSignatureError):
        validate_webhook_signature(header, "req-123", "other-id", SECRET)


def test_missing_header_raises():
    with pytest.raises(WebhookSignatureError):
        validate_webhook_signature(None, "req-123", "ordtst01", SECRET)


def test_malformed_header_raises():
    with pytest.raises(WebhookSignatureError):
        validate_webhook_signature("garbage-without-equals", "req-123", "ordtst01", SECRET)


def test_no_secret_configured_skips_validation():
    # Não deve lançar exceção quando o secret não está configurado
    # (comportamento pensado para ambiente de desenvolvimento).
    validate_webhook_signature(None, None, None, "")
