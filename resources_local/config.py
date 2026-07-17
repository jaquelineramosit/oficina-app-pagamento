from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:

    aws_region: str = os.getenv("AWS_REGION", "us-east-1")

    endpoint_url: str = os.getenv(
        "LOCALSTACK_URL",
        "http://localhost:4566"
    )

    queue_url: str = os.getenv(
        "QUEUE_URL",
        "http://localhost:4566/000000000000/sqs-pagamento-solicitar"
    )

    aws_access_key_id: str = os.getenv(
        "AWS_ACCESS_KEY_ID",
        "test"
    )

    aws_secret_access_key: str = os.getenv(
        "AWS_SECRET_ACCESS_KEY",
        "test"
    )


settings = Settings()