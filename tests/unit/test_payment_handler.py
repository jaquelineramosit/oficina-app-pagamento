from unittest.mock import patch

from src.infrastructure.handlers import payment_handler

SQS_EVENT = {"Records": [{"messageId": "msg-1", "body": "{}"}]}
SCHEDULED_EVENT = {"source": "aws.events", "detail-type": "Scheduled Event"}


@patch("src.infrastructure.handlers.payment_handler._polling_lambda_handler")
@patch("src.infrastructure.handlers.payment_handler._sqs_lambda_handler")
def test_dispatches_sqs_events_to_sqs_handler(mock_sqs_handler, mock_polling_handler):
    mock_sqs_handler.return_value = {"batchItemFailures": []}

    result = payment_handler.lambda_handler(SQS_EVENT, context=None)

    mock_sqs_handler.assert_called_once_with(SQS_EVENT, None)
    mock_polling_handler.assert_not_called()
    assert result == {"batchItemFailures": []}


@patch("src.infrastructure.handlers.payment_handler._polling_lambda_handler")
@patch("src.infrastructure.handlers.payment_handler._sqs_lambda_handler")
def test_dispatches_non_sqs_events_to_polling_handler(mock_sqs_handler, mock_polling_handler):
    mock_polling_handler.return_value = {"orders_verificadas": 0}

    result = payment_handler.lambda_handler(SCHEDULED_EVENT, context=None)

    mock_polling_handler.assert_called_once_with(SCHEDULED_EVENT, None)
    mock_sqs_handler.assert_not_called()
    assert result == {"orders_verificadas": 0}
