import json
from unittest.mock import MagicMock

from src.infrastructure.adapters.sqs_dead_letter_publisher import SQSDeadLetterPublisher

DLQ_URL = "https://sqs.fake/sqs-pagamento-solicitar-dlq"


def _build_publisher(client):
    return SQSDeadLetterPublisher(queue_url=DLQ_URL, client=client)


def test_publish_sends_original_body_and_error_to_dlq():
    client = MagicMock()
    publisher = _build_publisher(client)

    publisher.publish("msg-1", '{"foo": "bar"}', "campo obrigatório ausente")

    client.send_message.assert_called_once()
    kwargs = client.send_message.call_args.kwargs
    assert kwargs["QueueUrl"] == DLQ_URL

    body = json.loads(kwargs["MessageBody"])
    assert body["original_message_id"] == "msg-1"
    assert body["raw_body"] == '{"foo": "bar"}'
    assert body["error"] == "campo obrigatório ausente"


def test_publish_skips_when_queue_url_is_not_configured():
    client = MagicMock()
    publisher = SQSDeadLetterPublisher(queue_url="", client=client)

    publisher.publish("msg-1", "{}", "erro")

    client.send_message.assert_not_called()
