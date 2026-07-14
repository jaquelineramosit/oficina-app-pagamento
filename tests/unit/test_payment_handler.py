from unittest.mock import patch

from src.infrastructure.handlers import payment_handler

SQS_EVENT = {"Records": [{"messageId": "msg-1", "body": "{}"}]}
WEBHOOK_EVENT = {"httpMethod": "POST", "body": "{}", "headers": {}}


@patch("src.infrastructure.handlers.payment_handler._webhook_lambda_handler")
@patch("src.infrastructure.handlers.payment_handler._sqs_lambda_handler")
def test_dispatches_sqs_events_to_sqs_handler(mock_sqs_handler, mock_webhook_handler):
    mock_sqs_handler.return_value = {"batchItemFailures": []}

    result = payment_handler.lambda_handler(SQS_EVENT, context=None)

    mock_sqs_handler.assert_called_once_with(SQS_EVENT, None)
    mock_webhook_handler.assert_not_called()
    assert result == {"batchItemFailures": []}


@patch("src.infrastructure.handlers.payment_handler._webhook_lambda_handler")
@patch("src.infrastructure.handlers.payment_handler._sqs_lambda_handler")
def test_dispatches_non_sqs_events_to_webhook_handler(mock_sqs_handler, mock_webhook_handler):
    mock_webhook_handler.return_value = {"statusCode": 200, "body": "{}"}

    result = payment_handler.lambda_handler(WEBHOOK_EVENT, context=None)

    mock_webhook_handler.assert_called_once_with(WEBHOOK_EVENT, None)
    mock_sqs_handler.assert_not_called()
    assert result == {"statusCode": 200, "body": "{}"}
