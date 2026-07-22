from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from src.application.use_cases.check_payment_status import CheckPaymentStatusUseCase
from src.domain.entities import Order
from src.domain.payment_status import PaymentStatus


def _iso(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


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
        created_date=_iso(minutes_ago=5),
    )


def _pending_order(order_id="ORDTST01", created_minutes_ago=None):
    return Order(
        id=order_id,
        type="online",
        processing_mode="automatic",
        external_reference="order_test_001",
        description="Order Pix - teste",
        total_amount="10.00",
        status="action_required",
        status_detail="waiting_transfer",
        created_date=_iso(created_minutes_ago) if created_minutes_ago is not None else None,
    )


def _build_use_case(order, order_expiration_minutes=10):
    gateway = MagicMock()
    gateway.get_order.return_value = order
    repository = MagicMock()
    notifier = MagicMock()
    use_case = CheckPaymentStatusUseCase(
        gateway, repository, notifier, order_expiration_minutes=order_expiration_minutes
    )
    return use_case, gateway, repository, notifier


def test_execute_publishes_pago_when_order_is_processed():
    use_case, gateway, repository, notifier = _build_use_case(_paid_order())

    result = use_case.execute("ORDTST01")

    gateway.get_order.assert_called_once_with("ORDTST01")
    repository.update_order_status.assert_called_once()
    notifier.notify.assert_called_once()
    notified_order, notified_status = notifier.notify.call_args.args
    assert notified_status == PaymentStatus.PAGO
    assert result["status"] == "processed"


def test_execute_does_not_publish_when_order_is_not_yet_paid_and_within_window():
    order = _pending_order(created_minutes_ago=2)
    use_case, gateway, repository, notifier = _build_use_case(order, order_expiration_minutes=10)

    result = use_case.execute("ORDTST01")

    gateway.get_order.assert_called_once_with("ORDTST01")
    repository.update_order_status.assert_called_once()
    notifier.notify.assert_not_called()
    assert result["status"] == "action_required"


def test_execute_treats_missing_created_date_as_not_expired():
    order = _pending_order(created_minutes_ago=None)
    use_case, gateway, repository, notifier = _build_use_case(order, order_expiration_minutes=10)

    result = use_case.execute("ORDTST01")

    notifier.notify.assert_not_called()
    assert result["status"] == "action_required"


def test_execute_marks_order_as_recusado_when_expiration_window_has_passed():
    order = _pending_order(created_minutes_ago=15)
    use_case, gateway, repository, notifier = _build_use_case(order, order_expiration_minutes=10)

    result = use_case.execute("ORDTST01")

    repository.update_order_status.assert_called_once()
    notifier.notify.assert_called_once()
    notified_order, notified_status = notifier.notify.call_args.args
    assert notified_status == PaymentStatus.RECUSADO
    assert notified_order.status == PaymentStatus.RECUSADO
    assert result["status"] == PaymentStatus.RECUSADO
