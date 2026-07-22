from .aws_clients import get_dynamodb, get_sqs

print("=== SQS ===")

for queue in get_sqs().list_queues().get("QueueUrls", []):
    print(queue)

print()

print("=== DynamoDB ===")

for table in get_dynamodb().list_tables()["TableNames"]:
    print(table)

print()

print("Tudo OK!")