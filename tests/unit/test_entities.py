from decimal import Decimal

import pytest

from src.domain.entities import OrderRequest
from src.domain.exceptions import DomainValidationError

VALID_PAYLOAD = {
    "type": "online",
    "processing_mode": "automatic",
    "external_reference": "order_test_001",
    "total_amount": "10.00",
    "description": "Order Pix - teste",
    "payer": {"email": "test@testuser.com"},
    "transactions": {
        "payments": [
            {"amount": "10.00", "payment_method": {"type": "bank_transfer", "id": "pix"}}
        ]
    },
}


def test_valid_payload_builds_order_request():
    order_request = OrderRequest.from_dict(VALID_PAYLOAD)

    assert order_request.type == "online"
    assert order_request.total_amount == Decimal("10.00")
    assert order_request.payer.email == "test@testuser.com"
    assert len(order_request.payments) == 1
    assert order_request.payments[0].payment_method.id == "pix"


@pytest.mark.parametrize(
    "missing_field",
    ["external_reference", "total_amount", "description", "payer", "transactions"],
)
def test_missing_required_field_raises(missing_field):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != missing_field}

    with pytest.raises(DomainValidationError):
        OrderRequest.from_dict(payload)


def test_missing_type_defaults_to_online():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "type"}

    order_request = OrderRequest.from_dict(payload)

    assert order_request.type == "online"


def test_missing_processing_mode_defaults_to_automatic():
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "processing_mode"}

    order_request = OrderRequest.from_dict(payload)

    assert order_request.processing_mode == "automatic"


def test_missing_payer_email_raises():
    payload = {**VALID_PAYLOAD, "payer": {}}
    with pytest.raises(DomainValidationError):
        OrderRequest.from_dict(payload)


def test_empty_payments_list_raises():
    payload = {**VALID_PAYLOAD, "transactions": {"payments": []}}
    with pytest.raises(DomainValidationError):
        OrderRequest.from_dict(payload)


def test_invalid_total_amount_raises():
    payload = {**VALID_PAYLOAD, "total_amount": "abc"}
    with pytest.raises(DomainValidationError):
        OrderRequest.from_dict(payload)


def test_missing_payment_method_raises():
    payload = {
        **VALID_PAYLOAD,
        "transactions": {"payments": [{"amount": "10.00"}]},
    }
    with pytest.raises(DomainValidationError):
        OrderRequest.from_dict(payload)


def test_to_mercado_pago_payload_matches_expected_shape():
    order_request = OrderRequest.from_dict(VALID_PAYLOAD)
    mp_payload = order_request.to_mercado_pago_payload()

    assert mp_payload["total_amount"] == "10.00"
    assert mp_payload["transactions"]["payments"][0]["payment_method"]["id"] == "pix"
    assert mp_payload["payer"]["email"] == "test@testuser.com"


def test_payer_first_name_is_optional_and_absent_from_payload_when_not_informed():
    order_request = OrderRequest.from_dict(VALID_PAYLOAD)

    assert order_request.payer.first_name is None
    mp_payload = order_request.to_mercado_pago_payload()
    assert "first_name" not in mp_payload["payer"]


def test_payer_first_name_is_captured_and_sent_to_mercado_pago():
    payload = {
        **VALID_PAYLOAD,
        "payer": {"email": "test_user_br@testuser.com", "first_name": "APRO"},
    }

    order_request = OrderRequest.from_dict(payload)

    assert order_request.payer.first_name == "APRO"
    mp_payload = order_request.to_mercado_pago_payload()
    assert mp_payload["payer"]["first_name"] == "APRO"
    assert mp_payload["payer"]["email"] == "test_user_br@testuser.com"
