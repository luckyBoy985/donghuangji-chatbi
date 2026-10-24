from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.config import Config

from backend.app.core.config import settings


@lru_cache(maxsize=1)
def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(
            connect_timeout=0.5,
            read_timeout=1,
            retries={"max_attempts": 1},
        ),
    )


def put_bytes(key: str, content: bytes, content_type: str) -> str:
    get_s3_client().put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    return key


def get_bytes(key: str) -> bytes:
    response = get_s3_client().get_object(
        Bucket=settings.s3_bucket,
        Key=key,
    )
    return response["Body"].read()


def delete_object(key: str) -> None:
    get_s3_client().delete_object(
        Bucket=settings.s3_bucket,
        Key=key,
    )
