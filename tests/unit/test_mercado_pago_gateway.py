from unittest.mock import MagicMock, patch

import pytest
import requests

from src.domain.entities import OrderRequest
from src.domain.exceptions import OrderNotFoundError, PaymentGatewayError
from src.infrastructure.adapters.mercado_pago_gateway import MercadoPagoGateway

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


def _order_request() -> OrderRequest:
    return OrderRequest.from_dict(VALID_PAYLOAD)


def _gateway() -> MercadoPagoGateway:
    return MercadoPagoGateway(access_token="TEST-TOKEN", base_url="https://api.mercadopago.com")


def _response(status_code: int, json_body: dict = None, text: str = ""):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {}
    response.text = text
    return response


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.post")
def test_create_order_returns_order_on_success(mock_post):
    mock_post.return_value = _response(201, {"id": "ORDTST01", "status": "action_required"})

    order = _gateway().create_order(_order_request(), idempotency_key="idem-key")

    assert order.id == "ORDTST01"
    assert order.status == "action_required"
    called_headers = mock_post.call_args.kwargs["headers"]
    assert called_headers["X-Idempotency-Key"] == "idem-key"
    assert called_headers["Authorization"] == "Bearer TEST-TOKEN"


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.post")
def test_create_order_raises_on_non_2xx_status(mock_post):
    mock_post.return_value = _response(400, text="bad request")

    with pytest.raises(PaymentGatewayError) as exc_info:
        _gateway().create_order(_order_request(), idempotency_key="idem-key")

    assert exc_info.value.status_code == 400


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.post")
def test_create_order_raises_on_network_error(mock_post):
    mock_post.side_effect = requests.ConnectionError("boom")

    with pytest.raises(PaymentGatewayError):
        _gateway().create_order(_order_request(), idempotency_key="idem-key")


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.get")
def test_get_order_returns_order_on_success(mock_get):
    mock_get.return_value = _response(200, {"id": "ORDTST01", "status": "processed"})

    order = _gateway().get_order("ORDTST01")

    assert order.id == "ORDTST01"
    assert order.status == "processed"
    mock_get.assert_called_once()


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.get")
def test_get_order_raises_not_found_on_404(mock_get):
    mock_get.return_value = _response(404)

    with pytest.raises(OrderNotFoundError):
        _gateway().get_order("INEXISTENTE")


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.get")
def test_get_order_raises_gateway_error_on_other_non_200(mock_get):
    mock_get.return_value = _response(500, text="internal error")

    with pytest.raises(PaymentGatewayError):
        _gateway().get_order("ORDTST01")


@patch("src.infrastructure.adapters.mercado_pago_gateway.requests.get")
def test_get_order_raises_on_network_error(mock_get):
    mock_get.side_effect = requests.Timeout("timed out")

    with pytest.raises(PaymentGatewayError):
        _gateway().get_order("ORDTST01")
