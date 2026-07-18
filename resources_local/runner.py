import json
import logging
import time
import traceback

from .aws_clients import get_sqs
from .config import settings


class LocalLambdaRunner:

    def __init__(self, handler):

        self.handler = handler
        self.sqs = get_sqs()

    def _build_event(self, message):

        return {
            "Records": [
                {
                    "messageId": message["MessageId"],
                    "receiptHandle": message["ReceiptHandle"],
                    "body": message["Body"],
                    "attributes": message.get("Attributes", {}),
                    "messageAttributes": message.get("MessageAttributes", {}),
                    "md5OfBody": message.get("MD5OfBody", ""),
                    "eventSource": "aws:sqs",
                    "eventSourceARN": "arn:aws:sqs:us-east-1:000000000000:sqs-pagamento-solicitar",
                    "awsRegion": settings.aws_region,
                }
            ]
        }

    def run(self):

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)-8s | %(message)s",
        )

        logger = logging.getLogger("runner")

        logger.info("=" * 70)
        logger.info("Local Lambda Runner iniciado")
        logger.info("=" * 70)

        while True:

            response = self.sqs.receive_message(
                QueueUrl=settings.queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])

            if not messages:
                continue

            message = messages[0]

            event = self._build_event(message)

            start = time.perf_counter()

            try:

                logger.info("Mensagem recebida")
                logger.info("MessageId=%s", message["MessageId"])

                result = self.handler(event, None)

                failures = {
                    item["itemIdentifier"]
                    for item in result.get("batchItemFailures", [])
                }

                if message["MessageId"] not in failures:

                    self.sqs.delete_message(
                        QueueUrl=settings.queue_url,
                        ReceiptHandle=message["ReceiptHandle"],
                    )

                    logger.info("Mensagem removida.")

                else:

                    logger.warning("Mensagem permanecerá na fila.")

                elapsed = (time.perf_counter() - start) * 1000

                logger.info("Tempo %.2f ms", elapsed)

            except Exception:

                traceback.print_exc()

                logger.error("Erro durante processamento.")

                logger.warning("Mensagem NÃO removida da fila.")