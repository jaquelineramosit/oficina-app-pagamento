from unittest.mock import MagicMock

import pytest

from src.application.use_cases.process_order_webhook import ProcessOrderWebhookUseCase
from src.domain.entities import Order
from src.domain.exceptions import DomainValidationError
from src.domain.payment_status import PaymentStatus


def _paid_order(order_id="ORDTST01"):
    return Order(
        id=order_id,
        type="online",
        processing_mode="automatic",
        external_reference="order_test_001",
        description="Order Pix - teste",
        total_amount="10.00",
        status="processed",
        status_detail="accredited",
    )


def _pending_order(order_id="ORDTST01"):
    return Order(
        id=order_id,
        type="online",
        processing_mode="automatic",
        external_reference="order_test_001",
        description="Order Pix - teste",
        total_amount="10.00",
        status="action_required",
        status_detail="waiting_transfer",
    )


def _build_use_case(order):
    gateway = MagicMock()
    gateway.get_order.return_value = order
    repository = MagicMock()
    notifier = MagicMock()
    return ProcessOrderWebhookUseCase(gateway, repository, notifier), gateway, repository, notifier


def test_execute_publishes_pago_when_order_is_processed_and_accredited():
    use_case, gateway, repository, notifier = _build_use_case(_paid_order())

    result = use_case.execute({"type": "order", "data": {"id": "ORDTST01"}})

    gateway.get_order.assert_called_once_with("ORDTST01")
    repository.update_order_status.assert_called_once()
    notifier.notify.assert_called_once()
    notified_order, notified_status = notifier.notify.call_args.args
    assert notified_status == PaymentStatus.PAGO
    assert result["status"] == "processed"


def test_execute_does_not_publish_when_order_is_not_yet_paid():
    use_case, gateway, repository, notifier = _build_use_case(_pending_order())

    result = use_case.execute({"type": "order", "data": {"id": "ORDTST01"}})

    repository.update_order_status.assert_called_once()
    notifier.notify.assert_not_called()
    assert result["status"] == "action_required"


def test_execute_ignores_unsupported_topic():
    use_case, gateway, repository, notifier = _build_use_case(_paid_order())

    result = use_case.execute({"type": "payment", "data": {"id": "123"}})

    assert result is None
    gateway.get_order.assert_not_called()
    repository.update_order_status.assert_not_called()
    notifier.notify.assert_not_called()


def test_execute_raises_when_data_id_is_missing():
    use_case, gateway, repository, notifier = _build_use_case(_paid_order())

    with pytest.raises(DomainValidationError):
        use_case.execute({"type": "order", "data": {}})

    notifier.notify.assert_not_called()
