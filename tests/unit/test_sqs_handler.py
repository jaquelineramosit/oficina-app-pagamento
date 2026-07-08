import json
from unittest.mock import MagicMock, patch

from src.domain.entities import Order
from src.domain.exceptions import DomainValidationError, PaymentGatewayError

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


def _sqs_event(body: dict, message_id: str = "msg-1") -> dict:
    return {"Records": [{"messageId": message_id, "body": json.dumps(body)}]}


@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_valid_message_is_processed_without_failures(mock_use_case):
    from src.infrastructure.handlers import sqs_handler

    mock_use_case.execute.return_value = {"order_id": "ORDTST01", "status": "action_required"}

    result = sqs_handler.lambda_handler(_sqs_event(VALID_PAYLOAD), context=None)

    assert result["batchItemFailures"] == []
    mock_use_case.execute.assert_called_once_with(VALID_PAYLOAD)


@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_invalid_payload_is_dropped_not_retried(mock_use_case):
    from src.infrastructure.handlers import sqs_handler

    mock_use_case.execute.side_effect = DomainValidationError("campo faltando")

    result = sqs_handler.lambda_handler(_sqs_event({}), context=None)

    # Mensagem inválida não deve gerar retry (não aparece em batchItemFailures)
    assert result["batchItemFailures"] == []


@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_gateway_error_marks_message_for_retry(mock_use_case):
    from src.infrastructure.handlers import sqs_handler

    mock_use_case.execute.side_effect = PaymentGatewayError("timeout")

    result = sqs_handler.lambda_handler(_sqs_event(VALID_PAYLOAD, message_id="msg-2"), context=None)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-2"}]
