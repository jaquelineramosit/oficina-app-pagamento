from unittest.mock import patch

from src.domain.entities import Order
from src.domain.exceptions import OrderNotFoundError, PaymentGatewayError

SCHEDULED_EVENT = {"source": "aws.events", "detail-type": "Scheduled Event"}


def _pending_order(order_id: str) -> Order:
    return Order(id=order_id, status="action_required", status_detail="waiting_transfer")


@patch("src.infrastructure.handlers.polling_handler._use_case")
@patch("src.infrastructure.handlers.polling_handler._order_repository")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_verifies_every_pending_order(mock_repository, mock_use_case):
    from src.infrastructure.handlers import polling_handler

    mock_repository.list_pending_orders.return_value = [
        _pending_order("ORDTST01"),
        _pending_order("ORDTST02"),
    ]
    mock_use_case.execute.side_effect = [
        {"order_id": "ORDTST01", "status": "processed"},
        {"order_id": "ORDTST02", "status": "action_required"},
    ]

    result = polling_handler.lambda_handler(SCHEDULED_EVENT, context=None)

    assert mock_use_case.execute.call_count == 2
    mock_use_case.execute.assert_any_call("ORDTST01")
    mock_use_case.execute.assert_any_call("ORDTST02")
    assert result == {"orders_verificadas": 2}


@patch("src.infrastructure.handlers.polling_handler._use_case")
@patch("src.infrastructure.handlers.polling_handler._order_repository")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_no_pending_orders_returns_zero(mock_repository, mock_use_case):
    from src.infrastructure.handlers import polling_handler

    mock_repository.list_pending_orders.return_value = []

    result = polling_handler.lambda_handler(SCHEDULED_EVENT, context=None)

    mock_use_case.execute.assert_not_called()
    assert result == {"orders_verificadas": 0}


@patch("src.infrastructure.handlers.polling_handler._use_case")
@patch("src.infrastructure.handlers.polling_handler._order_repository")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_one_order_failing_does_not_stop_the_others(mock_repository, mock_use_case):
    from src.infrastructure.handlers import polling_handler

    mock_repository.list_pending_orders.return_value = [
        _pending_order("ORDTST01"),
        _pending_order("ORDTST02"),
    ]
    mock_use_case.execute.side_effect = [
        PaymentGatewayError("timeout"),
        {"order_id": "ORDTST02", "status": "processed"},
    ]

    result = polling_handler.lambda_handler(SCHEDULED_EVENT, context=None)

    assert result == {"orders_verificadas": 1}


@patch("src.infrastructure.handlers.polling_handler._use_case")
@patch("src.infrastructure.handlers.polling_handler._order_repository")
@patch.dict("os.environ", {"MP_ACCESS_TOKEN": "TEST-TOKEN"})
def test_order_not_found_is_logged_and_skipped(mock_repository, mock_use_case):
    from src.infrastructure.handlers import polling_handler

    mock_repository.list_pending_orders.return_value = [_pending_order("ORDTST01")]
    mock_use_case.execute.side_effect = OrderNotFoundError("não encontrada")

    result = polling_handler.lambda_handler(SCHEDULED_EVENT, context=None)

    assert result == {"orders_verificadas": 0}
