import logging
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from src.application.ports.order_repository_port import OrderRepositoryPort
from src.domain.entities import Order
from src.infrastructure.config import settings

logger = logging.getLogger(__name__)


class DynamoDBOrderRepository(OrderRepositoryPort):
    """
    Adapter de saída que persiste o estado das orders em uma tabela
    DynamoDB (chave primária: order_id - String).
    """

    def __init__(self, table_name: str = None, resource=None):
        self._table_name = table_name or settings.ORDERS_TABLE_NAME
        self._dynamodb = resource or boto3.resource("dynamodb", region_name=settings.AWS_REGION)
        self._table = self._dynamodb.Table(self._table_name)

    def save_created_order(self, order: Order) -> None:
        try:
            self._table.put_item(
                Item={
                    "order_id": order.id,
                    "external_reference": order.external_reference,
                    "status": order.status,
                    "status_detail": order.status_detail,
                    "total_amount": order.total_amount,
                    "currency": order.currency,
                    "created_date": order.created_date,
                    "last_updated_date": order.last_updated_date,
                    "updated_at_epoch": int(time.time()),
                    "raw": order.raw,
                }
            )
        except ClientError as exc:
            logger.error(
                "Erro ao salvar order no DynamoDB | order_id=%s | erro=%s", order.id, exc
            )
            raise

    def update_order_status(self, order: Order) -> None:
        try:
            self._table.update_item(
                Key={"order_id": order.id},
                UpdateExpression=(
                    "SET #status = :status, status_detail = :status_detail, "
                    "last_updated_date = :last_updated_date, "
                    "updated_at_epoch = :updated_at_epoch, raw = :raw"
                ),
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={
                    ":status": order.status,
                    ":status_detail": order.status_detail,
                    ":last_updated_date": order.last_updated_date,
                    ":updated_at_epoch": int(time.time()),
                    ":raw": order.raw,
                },
            )
        except ClientError as exc:
            logger.error(
                "Erro ao atualizar order no DynamoDB | order_id=%s | erro=%s", order.id, exc
            )
            raise

    def find_by_id(self, order_id: str) -> Optional[Order]:
        response = self._table.get_item(Key={"order_id": order_id})
        item = response.get("Item")
        if not item:
            return None
        return Order.from_dict(item.get("raw", {}))
