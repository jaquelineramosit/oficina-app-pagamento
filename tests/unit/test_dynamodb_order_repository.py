import boto3
import pytest
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
