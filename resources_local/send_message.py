import json

from .aws_clients import get_sqs
from .config import settings

sqs = get_sqs()

payload = {
    "type": "online",
    "processing_mode": "automatic",
    "external_reference": "order_test_001",
    "total_amount": "10.00",
    "description": "Order Pix - teste",
    "payer": {
        "email": "test@testuser.com"
    },
    "transactions": {
        "payments": [
            {
                "amount": "10.00",
                "payment_method": {
                    "type": "bank_transfer",
                    "id": "pix"
                }
            }
        ]
    }
}

response = sqs.send_message(
    QueueUrl=settings.queue_url,
    MessageBody=json.dumps(payload),
)

print(response)