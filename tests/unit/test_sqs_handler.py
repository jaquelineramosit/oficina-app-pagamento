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


@patch("src.infrastructure.handlers.sqs_handler._dead_letter_publisher")
@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_invalid_payload_is_sent_to_dlq_and_not_retried(mock_use_case, mock_dlq_publisher):
    from src.infrastructure.handlers import sqs_handler

    mock_use_case.execute.side_effect = DomainValidationError("campo faltando")

    result = sqs_handler.lambda_handler(_sqs_event({}, message_id="msg-1"), context=None)

    # Mensagem inválida não deve gerar retry (não aparece em batchItemFailures)...
    assert result["batchItemFailures"] == []
    # ...mas é preservada na DLQ para investigação manual.
    mock_dlq_publisher.publish.assert_called_once_with("msg-1", json.dumps({}), "campo faltando")


@patch("src.infrastructure.handlers.sqs_handler._dead_letter_publisher")
@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_invalid_payload_is_retried_when_dlq_publish_fails(mock_use_case, mock_dlq_publisher):
    from src.infrastructure.handlers import sqs_handler

    mock_use_case.execute.side_effect = DomainValidationError("campo faltando")
    mock_dlq_publisher.publish.side_effect = RuntimeError("SQS indisponível")

    result = sqs_handler.lambda_handler(_sqs_event({}, message_id="msg-1"), context=None)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-1"}]


@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_gateway_error_is_notified_as_recusado_and_not_retried(mock_use_case):
    from src.infrastructure.handlers import sqs_handler

    exc = PaymentGatewayError("timeout")
    mock_use_case.execute.side_effect = exc
    mock_use_case.handle_gateway_error_as_recusado.return_value = {"outcome": "recusado"}

    result = sqs_handler.lambda_handler(_sqs_event(VALID_PAYLOAD, message_id="msg-2"), context=None)

    # Tratado como resultado de negócio definitivo: não retenta, e a recusa é
    # registrada através do use case (persistida + publicada em recusado).
    assert result["batchItemFailures"] == []
    mock_use_case.handle_gateway_error_as_recusado.assert_called_once_with(VALID_PAYLOAD, exc)


@patch("src.infrastructure.handlers.sqs_handler._use_case")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_gateway_error_is_retried_when_recusado_registration_fails(mock_use_case):
    from src.infrastructure.handlers import sqs_handler

    mock_use_case.execute.side_effect = PaymentGatewayError("timeout")
    mock_use_case.handle_gateway_error_as_recusado.side_effect = RuntimeError("DynamoDB indisponível")

    result = sqs_handler.lambda_handler(_sqs_event(VALID_PAYLOAD, message_id="msg-2"), context=None)

    assert result["batchItemFailures"] == [{"itemIdentifier": "msg-2"}]
