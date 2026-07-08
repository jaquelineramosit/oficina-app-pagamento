import json
from unittest.mock import patch

from src.domain.exceptions import OrderNotFoundError, PaymentGatewayError


def _api_gateway_event(body: dict, headers: dict = None) -> dict:
    return {
        "headers": headers or {},
        "queryStringParameters": None,
        "body": json.dumps(body),
    }


@patch("src.infrastructure.handlers.webhook_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN", "MP_WEBHOOK_SECRET": ""})
def test_valid_order_notification_returns_200(mock_use_case):
    from src.infrastructure.handlers import webhook_handler

    mock_use_case.execute.return_value = {"order_id": "ORDTST01", "status": "closed"}

    event = _api_gateway_event({"type": "order", "data": {"id": "ORDTST01"}})
    response = webhook_handler.lambda_handler(event, context=None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["order_id"] == "ORDTST01"


@patch("src.infrastructure.handlers.webhook_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN", "MP_WEBHOOK_SECRET": ""})
def test_unsupported_topic_still_returns_200(mock_use_case):
    from src.infrastructure.handlers import webhook_handler

    mock_use_case.execute.return_value = None

    event = _api_gateway_event({"type": "payment", "data": {"id": "123"}})
    response = webhook_handler.lambda_handler(event, context=None)

    assert response["statusCode"] == 200


@patch("src.infrastructure.handlers.webhook_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN", "MP_WEBHOOK_SECRET": ""})
def test_order_not_found_returns_200_to_avoid_infinite_retries(mock_use_case):
    from src.infrastructure.handlers import webhook_handler

    mock_use_case.execute.side_effect = OrderNotFoundError("não encontrada")

    event = _api_gateway_event({"type": "order", "data": {"id": "INEXISTENTE"}})
    response = webhook_handler.lambda_handler(event, context=None)

    assert response["statusCode"] == 200


@patch("src.infrastructure.handlers.webhook_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN", "MP_WEBHOOK_SECRET": ""})
def test_gateway_error_returns_502_so_mp_retries_later(mock_use_case):
    from src.infrastructure.handlers import webhook_handler

    mock_use_case.execute.side_effect = PaymentGatewayError("timeout")

    event = _api_gateway_event({"type": "order", "data": {"id": "ORDTST01"}})
    response = webhook_handler.lambda_handler(event, context=None)

    assert response["statusCode"] == 502


@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN", "MP_WEBHOOK_SECRET": "shh"})
def test_invalid_signature_returns_401():
    from src.infrastructure.handlers import webhook_handler

    event = _api_gateway_event(
        {"type": "order", "data": {"id": "ORDTST01"}},
        headers={"x-signature": "ts=123,v1=invalidhash", "x-request-id": "req-1"},
    )
    response = webhook_handler.lambda_handler(event, context=None)

    assert response["statusCode"] == 401
