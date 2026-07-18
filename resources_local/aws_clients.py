import boto3

from .config import settings


def get_sqs():

    return boto3.client(
        "sqs",
        endpoint_url=settings.endpoint_url,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )


def get_dynamodb():

    return boto3.client(
        "dynamodb",
        endpoint_url=settings.endpoint_url,
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )