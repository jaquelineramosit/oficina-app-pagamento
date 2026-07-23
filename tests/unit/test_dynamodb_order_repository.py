from unittest.mock import MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.domain.entities import Order
from src.infrastructure.adapters.dynamodb_order_repository import DynamoDBOrderRepository

TABLE_NAME = "orders-test"


@pytest.fixture
def dynamodb_resource():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "order_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield resource


def _order(order_id: str, status: str) -> Order:
    return Order(id=order_id, status=status, raw={"id": order_id, "status": status})


def test_list_pending_orders_excludes_processed_and_recusado(dynamodb_resource):
    repository = DynamoDBOrderRepository(table_name=TABLE_NAME, resource=dynamodb_resource)

    repository.save_created_order(_order("ORD1", "action_required"))
    repository.save_created_order(_order("ORD2", "processed"))
    repository.save_created_order(_order("ORD3", "recusado"))

    pending_ids = {order.id for order in repository.list_pending_orders()}

    assert pending_ids == {"ORD1"}


def test_list_pending_orders_stops_returning_order_once_it_becomes_terminal(dynamodb_resource):
    repository = DynamoDBOrderRepository(table_name=TABLE_NAME, resource=dynamodb_resource)

    repository.save_created_order(_order("ORD1", "action_required"))
    assert {order.id for order in repository.list_pending_orders()} == {"ORD1"}

    repository.update_order_status(_order("ORD1", "processed"))
    assert repository.list_pending_orders() == []


def test_find_by_id_returns_none_when_item_does_not_exist(dynamodb_resource):
    repository = DynamoDBOrderRepository(table_name=TABLE_NAME, resource=dynamodb_resource)

    assert repository.find_by_id("NAO_EXISTE") is None


def test_find_by_id_returns_order_reconstructed_from_raw(dynamodb_resource):
    repository = DynamoDBOrderRepository(table_name=TABLE_NAME, resource=dynamodb_resource)
    repository.save_created_order(_order("ORD1", "action_required"))

    order = repository.find_by_id("ORD1")

    assert order is not None
    assert order.id == "ORD1"
    assert order.status == "action_required"


def test_save_created_order_logs_and_reraises_on_client_error(dynamodb_resource):
    repository = DynamoDBOrderRepository(table_name="tabela-inexistente", resource=dynamodb_resource)

    with pytest.raises(ClientError):
        repository.save_created_order(_order("ORD1", "action_required"))


def test_update_order_status_logs_and_reraises_on_client_error(dynamodb_resource):
    repository = DynamoDBOrderRepository(table_name="tabela-inexistente", resource=dynamodb_resource)

    with pytest.raises(ClientError):
        repository.update_order_status(_order("ORD1", "processed"))


def test_list_pending_orders_follows_pagination_across_multiple_pages():
    mock_table = MagicMock()
    mock_table.scan.side_effect = [
        {
            "Items": [{"raw": {"id": "ORD1", "status": "action_required"}}],
            "LastEvaluatedKey": {"order_id": "ORD1"},
        },
        {
            "Items": [{"raw": {"id": "ORD2", "status": "action_required"}}],
        },
    ]
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table

    repository = DynamoDBOrderRepository(table_name=TABLE_NAME, resource=mock_resource)

    orders = repository.list_pending_orders()

    assert {order.id for order in orders} == {"ORD1", "ORD2"}
    assert mock_table.scan.call_count == 2
    assert mock_table.scan.call_args_list[1].kwargs["ExclusiveStartKey"] == {"order_id": "ORD1"}
